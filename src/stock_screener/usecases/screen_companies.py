"""ScreenCompaniesUseCase — the headline `ss screen` workflow.

Orchestrates: universe → snapshots → quant scoring → LLM analyst → fusion →
filtering → ranking → persistence. Pure orchestration — no I/O details.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Sequence

from pydantic import BaseModel

from ..core.events import (
    EventBus,
    UseCaseCompleted,
    UseCaseFailed,
    UseCaseStarted,
)
from ..core.logging import get_logger
from ..core.result import Err, Ok
from ..domain.analytics.risk import compute_risk
from ..domain.analytics.strategies.base import ScoringStrategy
from ..domain.entities.company import Company
from ..domain.entities.recommendation import Recommendation
from ..domain.entities.snapshot import CompanySnapshot
from ..domain.ports.llm_client import LLMClient
from ..domain.ports.market_data import FundamentalsProvider, NewsProvider, PriceProvider
from ..domain.ports.universe_repo import UniverseRepository
from ..domain.recommendation.fusion import (
    LLMAnalystOutput,
    RecommendationFusionService,
)
from ..domain.recommendation.policy import rank_top
from ..domain.specifications import Specification
from ..domain.value_objects.horizon import Horizon
from ..domain.value_objects.market_cap import MarketCapBucket
from ..domain.value_objects.pct import Pct
from ..domain.value_objects.score import Score
from ..infra.llm.prompts.analyse import AnalysisOutput, build_analysis_prompt

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Request / response
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ScreenRequest:
    bucket: MarketCapBucket
    top: int = 10
    horizon: Horizon = Horizon.LONG
    profile: str = "composite"
    snapshot_spec: Specification[CompanySnapshot] | None = None
    rec_spec: Specification[Recommendation] | None = None
    use_llm: bool = True
    max_concurrency: int = 8
    universe_limit: int | None = None  # cap how many tickers we fetch (debug)


@dataclass(frozen=True, slots=True)
class ScreenResponse:
    recommendations: list[Recommendation]
    universe_size: int
    candidates_scored: int
    candidates_analysed: int
    duration_s: float


# --------------------------------------------------------------------------- #
# Use case
# --------------------------------------------------------------------------- #
@dataclass
class ScreenCompaniesUseCase:
    universe: UniverseRepository
    fundamentals: FundamentalsProvider
    prices: PriceProvider
    news: NewsProvider | None
    llm: LLMClient | None
    scorer: ScoringStrategy
    fusion: RecommendationFusionService = field(default_factory=RecommendationFusionService)
    events: EventBus | None = None

    async def execute(self, request: ScreenRequest) -> ScreenResponse:
        started = perf_counter()
        if self.events:
            self.events.publish(UseCaseStarted("screen", payload={"bucket": request.bucket.value}))
        try:
            response = await self._run(request)
            if self.events:
                self.events.publish(
                    UseCaseCompleted("screen", duration_ms=(perf_counter() - started) * 1000)
                )
            return response
        except Exception as exc:
            if self.events:
                self.events.publish(UseCaseFailed("screen", error=str(exc)))
            raise

    async def _run(self, request: ScreenRequest) -> ScreenResponse:
        companies = self.universe.list(request.bucket)
        if request.universe_limit is not None:
            companies = companies[: request.universe_limit]
        log.info("universe.loaded", bucket=request.bucket.value, count=len(companies))
        if not companies:
            return ScreenResponse([], 0, 0, 0, perf_counter())

        snapshots = await self._fetch_snapshots(companies, request)
        log.info("snapshots.fetched", count=len(snapshots))
        if request.snapshot_spec is not None:
            snapshots = [s for s in snapshots if request.snapshot_spec.is_satisfied_by(s)]

        scored = self._score(snapshots, request)
        log.info("snapshots.scored", count=len(scored))

        # Take 3× the requested top for the LLM stage to give it room.
        candidates = scored[: max(request.top * 3, request.top)]
        recs = await self._analyse_and_fuse(candidates, request)

        if request.rec_spec is not None:
            recs = [r for r in recs if request.rec_spec.is_satisfied_by(r)]

        top = rank_top(recs, request.top)
        return ScreenResponse(
            recommendations=top,
            universe_size=len(companies),
            candidates_scored=len(scored),
            candidates_analysed=len(candidates),
            duration_s=perf_counter(),
        )

    # --------------------------- pipeline steps --------------------------- #
    async def _fetch_snapshots(
        self, companies: Sequence[Company], request: ScreenRequest
    ) -> list[CompanySnapshot]:
        sem = asyncio.Semaphore(request.max_concurrency)
        lookback = timedelta(days=400)

        async def _one(company: Company) -> CompanySnapshot | None:
            async with sem:
                f_res, p_res = await asyncio.gather(
                    self.fundamentals.get_fundamentals(company.symbol),
                    self.prices.get_prices(company.symbol, lookback),
                    return_exceptions=False,
                )
                fundamentals = f_res.value if isinstance(f_res, Ok) else None
                prices = p_res.value if isinstance(p_res, Ok) else None
                if fundamentals is None and prices is None:
                    return None
                return CompanySnapshot(
                    company=company,
                    fundamentals=fundamentals,
                    prices=prices,
                    news=(),
                    fetched_at=datetime.now(timezone.utc),
                )

        results = await asyncio.gather(*(_one(c) for c in companies), return_exceptions=False)
        return [s for s in results if s is not None]

    def _score(
        self, snapshots: Sequence[CompanySnapshot], request: ScreenRequest
    ) -> list[tuple[CompanySnapshot, "ScoreCarrier"]]:
        out: list[tuple[CompanySnapshot, ScoreCarrier]] = []
        for snap in snapshots:
            score = self.scorer.score(snap, request.horizon)
            out.append((snap, ScoreCarrier(score=score)))
        out.sort(key=lambda pair: pair[1].score.value, reverse=True)
        return out

    async def _analyse_and_fuse(
        self,
        scored: Sequence[tuple[CompanySnapshot, "ScoreCarrier"]],
        request: ScreenRequest,
    ) -> list[Recommendation]:
        sem = asyncio.Semaphore(min(4, request.max_concurrency))

        async def _one(pair: tuple[CompanySnapshot, ScoreCarrier]) -> Recommendation | None:
            snap, carrier = pair
            risk = compute_risk(snap)
            llm_out: LLMAnalystOutput | None = None
            if request.use_llm and self.llm is not None:
                async with sem:
                    prompt = build_analysis_prompt(snap, request.horizon)
                    res = await self.llm.analyse(prompt, AnalysisOutput)
                if isinstance(res, Ok):
                    llm_out = _to_analyst_output(res.value)
                elif isinstance(res, Err):
                    log.warning(
                        "llm.failed",
                        symbol=snap.company.symbol.code,
                        error=str(res.error),
                    )
            return self.fusion.fuse(
                snapshot=snap,
                quant_score=carrier.score,
                llm=llm_out,
                risk=risk,
                horizon=request.horizon,
                scoring_profile=request.profile,
            )

        results = await asyncio.gather(*(_one(p) for p in scored), return_exceptions=False)
        return [r for r in results if r is not None]


@dataclass(frozen=True, slots=True)
class ScoreCarrier:
    """Internal helper to carry a quant score alongside its snapshot."""

    score: Score


def _to_analyst_output(a: BaseModel) -> LLMAnalystOutput:
    """Convert the wire-format `AnalysisOutput` into the domain VO."""
    data = a.model_dump()
    horizon_str = data.get("suggested_horizon")
    horizon = Horizon(horizon_str) if horizon_str else None
    return LLMAnalystOutput(
        thesis_summary=data["thesis_summary"],
        key_risks=tuple(data.get("key_risks", ())),
        catalysts=tuple(data.get("catalysts", ())),
        qualitative_risk=Pct.from_ratio(float(data.get("qualitative_risk", 0.5))),
        confidence=float(data.get("confidence", 0.5)),
        suggested_horizon=horizon,
    )


__all__ = ["ScreenCompaniesUseCase", "ScreenRequest", "ScreenResponse"]
