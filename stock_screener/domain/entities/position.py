"""Position entity — one held stock in the user's portfolio."""

from __future__ import annotations

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..value_objects.symbol import Symbol


class Position(BaseModel):
    """A user-held position in a single ticker."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    symbol: Symbol
    avg_buy_price: float = Field(gt=0)
    quantity: float = Field(default=1.0, gt=0)
    bought_on: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")
        return self

    @property
    def cost_basis(self) -> float:
        return self.avg_buy_price * self.quantity

    def unrealised_pnl(self, current_price: float) -> tuple[float, float]:
        """Return ``(absolute, pct)`` unrealised P&L at ``current_price``."""
        if current_price <= 0:
            raise ValueError("current_price must be positive")
        delta_per_share = current_price - self.avg_buy_price
        absolute = delta_per_share * self.quantity
        pct = (delta_per_share / self.avg_buy_price) * 100.0
        return absolute, pct


__all__ = ["Position"]
