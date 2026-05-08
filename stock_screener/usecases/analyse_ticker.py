"""AnalyseTickerUseCase — deep dive on one company."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..core.logging import get_logger
from ..core.result import Err, Ok
from ..domain.analytics.risk import compute_risk
from ..domain.analytics.strategies.base import ScoringStrategy
from ..domain.entities.recommendation import Recommendation
from ..domain.entities.snapshot import CompanySnapshot
from ..domain.ports.llm_client import LLMClient
from ..domain.ports.market_data import FundamentalsProvider, PriceProvider
from ..domain.ports.universe_repo import UniverseRepository
from ..domain.recommendation.fusion import RecommendationFusionService
from ..domain.value_objects.horizon import Horizon
from ..domain.value_objects.symbol import Symbol
from ..infra.llm.prompts.analyse import AnalysisOutput, build_analysis_prompt
from .screen_companies import _to_analyst_output  # internal reuse

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AnalyseRequest:
    symbol: Symbol
    horizon: Horizon = Horizon.LONG
    use_llm: bool = True


@dataclass
class AnalyseTickerUseCase:
    universe: UniverseRepository
    fundamentals: FundamentalsProvider
    prices: PriceProvider
    llm: LLMClient | None
    scorer: ScoringStrategy
    fusion: RecommendationFusionService = field(default_factory=RecommendationFusionService)

    async def execute(self, request: AnalyseRequest) -> Recommendation:
        company = self.universe.get(request.symbol.code)
        if company is None:
            from ..domain.entities.company import Company

            company = Company(symbol=request.symbol, name=request.symbol.code)

        f_res = await self.fundamentals.get_fundamentals(request.symbol)
        p_res = await self.prices.get_prices(request.symbol, timedelta(days=400))
        snap = CompanySnapshot(
            company=company,
            fundamentals=f_res.value if isinstance(f_res, Ok) else None,
            prices=p_res.value if isinstance(p_res, Ok) else None,
            news=(),
            fetched_at=datetime.now(timezone.utc),
        )

        score = self.scorer.score(snap, request.horizon)
        risk = compute_risk(snap)
        llm_out = None
        if request.use_llm and self.llm is not None:
            prompt = build_analysis_prompt(snap, request.horizon)
            res = await self.llm.analyse(prompt, AnalysisOutput)
            if isinstance(res, Ok):
                llm_out = _to_analyst_output(res.value)
            elif isinstance(res, Err):
                log.warning("llm.failed", symbol=request.symbol.code, error=str(res.error))

        return self.fusion.fuse(
            snapshot=snap,
            quant_score=score,
            llm=llm_out,
            risk=risk,
            horizon=request.horizon,
            scoring_profile="composite",
        )


__all__ = ["AnalyseTickerUseCase", "AnalyseRequest"]
