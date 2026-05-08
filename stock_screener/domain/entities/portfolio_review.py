"""PortfolioReview entity — what `ss portfolio review` produces per holding."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from ..value_objects.action import PortfolioAction
from .position import Position
from .recommendation import Recommendation


class PortfolioReview(BaseModel):
    """One position's review combining current valuation and an action call."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    position: Position
    current_price: float | None
    unrealised_pnl_abs: float | None = None
    unrealised_pnl_pct: float | None = None
    recommendation: Recommendation | None = None
    action: PortfolioAction = PortfolioAction.HOLD
    rationale: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["PortfolioReview"]
