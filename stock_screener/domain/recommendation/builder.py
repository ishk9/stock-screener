"""Fluent builder for ``Recommendation`` instances."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..entities.recommendation import Recommendation
from ..value_objects.action import Action
from ..value_objects.conviction import Conviction
from ..value_objects.horizon import Horizon
from ..value_objects.market_cap import MarketCapBucket
from ..value_objects.pct import Pct
from ..value_objects.score import Score
from ..value_objects.symbol import Symbol


class RecommendationBuilder:
    """Fluent builder. Each ``with_*`` returns ``self`` for chaining."""

    _MANDATORY: tuple[str, ...] = (
        "symbol",
        "company_name",
        "score",
        "conviction",
        "risk_pct",
        "suggested_horizon",
    )

    def __init__(self) -> None:
        self._fields: dict[str, Any] = {}

    def with_symbol(self, symbol: Symbol) -> "RecommendationBuilder":
        self._fields["symbol"] = symbol
        return self

    def with_company_name(self, name: str) -> "RecommendationBuilder":
        self._fields["company_name"] = name
        return self

    def with_sector(self, sector: str | None) -> "RecommendationBuilder":
        self._fields["sector"] = sector
        return self

    def with_market_cap_bucket(
        self, bucket: MarketCapBucket | None
    ) -> "RecommendationBuilder":
        self._fields["market_cap_bucket"] = bucket
        return self

    def with_score(self, score: Score) -> "RecommendationBuilder":
        self._fields["score"] = score
        return self

    def with_conviction(self, conviction: Conviction) -> "RecommendationBuilder":
        self._fields["conviction"] = conviction
        return self

    def with_risk_pct(self, risk: Pct) -> "RecommendationBuilder":
        self._fields["risk_pct"] = risk
        return self

    def with_horizon(self, horizon: Horizon) -> "RecommendationBuilder":
        self._fields["suggested_horizon"] = horizon
        return self

    def with_action(self, action: Action) -> "RecommendationBuilder":
        self._fields["action"] = action
        return self

    def with_entry_band(self, band: tuple[float, float] | None) -> "RecommendationBuilder":
        self._fields["entry_band"] = band
        return self

    def with_stop_loss(self, sl: float | None) -> "RecommendationBuilder":
        self._fields["stop_loss"] = sl
        return self

    def with_target(self, target: float | None) -> "RecommendationBuilder":
        self._fields["target"] = target
        return self

    def with_thesis(self, summary: str) -> "RecommendationBuilder":
        self._fields["thesis_summary"] = summary
        return self

    def with_key_risks(self, risks: tuple[str, ...]) -> "RecommendationBuilder":
        self._fields["key_risks"] = tuple(risks)
        return self

    def with_catalysts(self, catalysts: tuple[str, ...]) -> "RecommendationBuilder":
        self._fields["catalysts"] = tuple(catalysts)
        return self

    def with_citations(self, citations: tuple[str, ...]) -> "RecommendationBuilder":
        self._fields["citations"] = tuple(citations)
        return self

    def with_data_freshness(self, ts: datetime) -> "RecommendationBuilder":
        self._fields["data_freshness"] = ts
        return self

    def build(self) -> Recommendation:
        missing = [k for k in self._MANDATORY if k not in self._fields]
        if missing:
            raise ValueError(
                f"RecommendationBuilder.build(): missing mandatory fields: {missing}"
            )
        return Recommendation(**self._fields)


__all__ = ["RecommendationBuilder"]
