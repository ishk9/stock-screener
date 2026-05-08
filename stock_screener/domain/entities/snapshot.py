"""Aggregated company snapshot — what the analytics engine consumes."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from .company import Company
from .fundamentals import Fundamentals
from .news import NewsItem
from .price_series import PriceSeries


class CompanySnapshot(BaseModel):
    """Everything we know about a company at a point in time."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    company: Company
    fundamentals: Fundamentals | None = None
    prices: PriceSeries | None = None
    news: tuple[NewsItem, ...] = Field(default_factory=tuple)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_minimum_data(self) -> bool:
        """Whether we have enough data for a meaningful score."""
        return self.fundamentals is not None and self.prices is not None


__all__ = ["CompanySnapshot"]
