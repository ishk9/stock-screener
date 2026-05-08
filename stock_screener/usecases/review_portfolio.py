"""ReviewPortfolioUseCase — analyse every held position and recommend an action."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..core.logging import get_logger
from ..core.result import Err, Ok
from ..domain.analytics.risk import compute_risk
from ..domain.analytics.strategies.base import ScoringStrategy
from ..domain.entities.company import Company
from ..domain.entities.portfolio_review import PortfolioReview
from ..domain.entities.position import Position
from ..domain.entities.snapshot import CompanySnapshot
from ..domain.portfolio.policy import PortfolioActionPolicy
from ..domain.ports.llm_client import LLMClient
from ..domain.ports.market_data import FundamentalsProvider, PriceProvider
from ..domain.ports.portfolio_repo import PortfolioRepository
from ..domain.ports.universe_repo import UniverseRepository
from ..domain.recommendation.fusion import RecommendationFusionService
from ..domain.value_objects.horizon import Horizon
from ..infra.llm.prompts.analyse import AnalysisOutput, build_analysis_prompt
from .screen_companies import _to_analyst_output

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    horizon: Horizon = Horizon.LONG
    use_llm: bool = True
    max_concurrency: int = 6


@dataclass(frozen=True, slots=True)
class ReviewResponse:
    reviews: list[PortfolioReview]


@dataclass
class ReviewPortfolioUseCase:
    portfolio: PortfolioRepository
    universe: UniverseRepository
    fundamentals: FundamentalsProvider
    prices: PriceProvider
    llm: LLMClient | None
    scorer: ScoringStrategy
    policy: PortfolioActionPolicy = field(default_factory=PortfolioActionPolicy)
    fusion: RecommendationFusionService = field(default_factory=RecommendationFusionService)

    async def execute(self, request: ReviewRequest) -> ReviewResponse:
        positions = self.portfolio.list()
        if not positions:
            return ReviewResponse(reviews=[])

        sem = asyncio.Semaphore(request.max_concurrency)
        tasks = [self._review_one(p, request, sem) for p in positions]
        reviews = await asyncio.gather(*tasks, return_exceptions=False)
        return ReviewResponse(reviews=list(reviews))

    async def _review_one(
        self, position: Position, request: ReviewRequest, sem: asyncio.Semaphore
    ) -> PortfolioReview:
        async with sem:
            company = self.universe.get(position.symbol.code) or Company(
                symbol=position.symbol,
                name=position.symbol.code,
            )
            f_res = await self.fundamentals.get_fundamentals(position.symbol)
            p_res = await self.prices.get_prices(
                position.symbol, timedelta(days=400)
            )
            snap = CompanySnapshot(
                company=company,
                fundamentals=f_res.value if isinstance(f_res, Ok) else None,
                prices=p_res.value if isinstance(p_res, Ok) else None,
                news=(),
                fetched_at=datetime.now(timezone.utc),
            )

            current_price = (
                snap.prices.latest.close if snap.prices and snap.prices.latest else None
            )

            recommendation = None
            if snap.has_minimum_data:
                score = self.scorer.score(snap, request.horizon)
                risk = compute_risk(snap)
                llm_out = None
                if request.use_llm and self.llm is not None:
                    prompt = build_analysis_prompt(snap, request.horizon)
                    res = await self.llm.analyse(prompt, AnalysisOutput)
                    if isinstance(res, Ok):
                        llm_out = _to_analyst_output(res.value)
                    elif isinstance(res, Err):
                        log.warning(
                            "portfolio.llm.failed",
                            symbol=position.symbol.code,
                            error=str(res.error),
                        )
                recommendation = self.fusion.fuse(
                    snapshot=snap,
                    quant_score=score,
                    llm=llm_out,
                    risk=risk,
                    horizon=request.horizon,
                    scoring_profile="composite",
                )

            action, rationale = self.policy.decide(
                position=position,
                current_price=current_price,
                recommendation=recommendation,
            )

            pnl_abs = pnl_pct = None
            if current_price is not None and current_price > 0:
                pnl_abs, pnl_pct = position.unrealised_pnl(current_price)

            return PortfolioReview(
                position=position,
                current_price=current_price,
                unrealised_pnl_abs=pnl_abs,
                unrealised_pnl_pct=pnl_pct,
                recommendation=recommendation,
                action=action,
                rationale=rationale,
            )


__all__ = ["ReviewPortfolioUseCase", "ReviewRequest", "ReviewResponse"]
