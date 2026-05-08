"""Company entity — identity + descriptive metadata."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..value_objects.market_cap import MarketCapBucket
from ..value_objects.symbol import Symbol


class Company(BaseModel):
    """A listed equity entity."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    symbol: Symbol
    name: str
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_inr: float | None = Field(default=None, ge=0)
    market_cap_bucket: MarketCapBucket | None = None
    market_cap_rank: int | None = Field(default=None, ge=1)
    listing_date: str | None = None  # ISO yyyy-mm-dd

    def short(self) -> str:
        return f"{self.symbol.code} ({self.symbol.exchange.value})"


__all__ = ["Company"]
