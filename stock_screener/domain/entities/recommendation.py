"""Recommendation entity — the final user-facing artefact."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

from pydantic import BaseModel, ConfigDict, Field

from ..value_objects.conviction import Conviction
from ..value_objects.horizon import Horizon
from ..value_objects.market_cap import MarketCapBucket
from ..value_objects.pct import Pct
from ..value_objects.score import Score
from ..value_objects.symbol import Symbol


class Recommendation(BaseModel):
    """One ranked investment idea."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    symbol: Symbol
    company_name: str
    sector: str | None = None
    market_cap_bucket: MarketCapBucket | None = None

    score: Score
    conviction: Conviction
    risk_pct: Pct
    suggested_horizon: Horizon

    entry_band: Tuple[float, float] | None = None
    stop_loss: float | None = None
    target: float | None = None

    thesis_summary: str = ""
    key_risks: tuple[str, ...] = Field(default_factory=tuple)
    catalysts: tuple[str, ...] = Field(default_factory=tuple)

    citations: tuple[str, ...] = Field(default_factory=tuple)
    data_freshness: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["Recommendation"]
