"""Fusion of quantitative score and LLM narrative into a ``Recommendation``."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..analytics.risk import RiskBreakdown
from ..entities.recommendation import Recommendation
from ..entities.snapshot import CompanySnapshot
from ..value_objects.conviction import Conviction
from ..value_objects.horizon import Horizon
from ..value_objects.pct import Pct
from ..value_objects.score import Score
from .builder import RecommendationBuilder

LLM_RISK_WEIGHT = 0.40
QUANT_RISK_WEIGHT = 0.60

ENTRY_BAND_PCT = 0.02
HORIZON_FACTOR: dict[Horizon, float] = {
    Horizon.SHORT: 0.5,
    Horizon.MID: 0.75,
    Horizon.LONG: 1.0,
}
BASE_TARGET_PCT = 0.20
BASE_STOP_PCT = 0.08

LOW_CONFIDENCE_THRESHOLD = 0.5

_DOWNGRADE: dict[Conviction, Conviction] = {
    Conviction.HIGH: Conviction.MEDIUM,
    Conviction.MEDIUM: Conviction.LOW,
    Conviction.LOW: Conviction.LOW,
}


class LLMAnalystOutput(BaseModel):
    """Narrative output produced by the LLM analyst."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    thesis_summary: str
    key_risks: tuple[str, ...] = Field(default_factory=tuple)
    catalysts: tuple[str, ...] = Field(default_factory=tuple)
    qualitative_risk: Pct
    confidence: float
    suggested_horizon: Horizon | None = None

    @field_validator("confidence")
    @classmethod
    def _confidence_in_unit(cls, v: float) -> float:
        if not (0.0 <= float(v) <= 1.0):
            raise ValueError(f"confidence must be in [0, 1]; got {v!r}")
        return float(v)


def _downgrade(conv: Conviction) -> Conviction:
    return _DOWNGRADE[conv]


def _combined_risk(risk: RiskBreakdown, llm: LLMAnalystOutput | None) -> Pct:
    if llm is None:
        return risk.composite
    blended = (
        risk.composite.as_ratio * QUANT_RISK_WEIGHT
        + llm.qualitative_risk.as_ratio * LLM_RISK_WEIGHT
    )
    return Pct.from_ratio(blended)


def _latest_price(snapshot: CompanySnapshot) -> float | None:
    if snapshot.prices is None:
        return None
    last = snapshot.prices.latest
    return last.close if last is not None else None


def _trade_levels(
    price: float | None, horizon: Horizon
) -> tuple[tuple[float, float] | None, float | None, float | None]:
    if price is None or price <= 0:
        return None, None, None
    factor = HORIZON_FACTOR[horizon]
    entry_band = (
        round(price * (1.0 - ENTRY_BAND_PCT), 4),
        round(price * (1.0 + ENTRY_BAND_PCT), 4),
    )
    stop = round(price * (1.0 - BASE_STOP_PCT * factor), 4)
    target = round(price * (1.0 + BASE_TARGET_PCT * factor), 4)
    return entry_band, stop, target


@dataclass(frozen=True, slots=True)
class RecommendationFusionService:
    """Domain service that fuses quant + LLM into a final ``Recommendation``."""

    def fuse(
        self,
        snapshot: CompanySnapshot,
        quant_score: Score,
        llm: LLMAnalystOutput | None,
        risk: RiskBreakdown,
        horizon: Horizon,
        *,
        scoring_profile: str,
    ) -> Recommendation:
        risk_pct = _combined_risk(risk, llm)

        conviction = Conviction.from_score(quant_score.value)
        if llm is not None and llm.confidence < LOW_CONFIDENCE_THRESHOLD:
            conviction = _downgrade(conviction)

        price = _latest_price(snapshot)
        entry_band, stop, target = _trade_levels(price, horizon)

        thesis = llm.thesis_summary if llm is not None else (
            f"Quantitative {scoring_profile} score: {quant_score.value:.1f}/100."
        )
        key_risks = llm.key_risks if llm is not None else ()
        catalysts = llm.catalysts if llm is not None else ()

        builder = (
            RecommendationBuilder()
            .with_symbol(snapshot.company.symbol)
            .with_company_name(snapshot.company.name)
            .with_sector(snapshot.company.sector)
            .with_market_cap_bucket(snapshot.company.market_cap_bucket)
            .with_score(quant_score)
            .with_conviction(conviction)
            .with_risk_pct(risk_pct)
            .with_horizon(horizon)
            .with_entry_band(entry_band)
            .with_stop_loss(stop)
            .with_target(target)
            .with_thesis(thesis)
            .with_key_risks(key_risks)
            .with_catalysts(catalysts)
        )
        return builder.build()


__all__ = [
    "LLMAnalystOutput",
    "RecommendationFusionService",
    "LOW_CONFIDENCE_THRESHOLD",
]
