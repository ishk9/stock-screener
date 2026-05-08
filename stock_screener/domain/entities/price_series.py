"""Price series entity — OHLCV with trivially derivable returns."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PricePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    on: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)


class PriceSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

    points: tuple[PricePoint, ...]

    @model_validator(mode="after")
    def _sorted_unique(self) -> "PriceSeries":
        if len(self.points) >= 2:
            for prev, nxt in zip(self.points, self.points[1:]):
                if not prev.on < nxt.on:
                    raise ValueError("PriceSeries points must be strictly ascending by date")
        return self

    @classmethod
    def from_points(cls, points: Sequence[PricePoint]) -> "PriceSeries":
        return cls(points=tuple(sorted(points, key=lambda p: p.on)))

    @property
    def latest(self) -> PricePoint | None:
        return self.points[-1] if self.points else None

    def closes(self) -> tuple[float, ...]:
        return tuple(p.close for p in self.points)

    def return_over(self, *, sessions: int) -> float | None:
        """Simple return over the last N sessions, e.g. 21 ≈ 1m, 252 ≈ 1y."""
        if len(self.points) <= sessions or sessions <= 0:
            return None
        end = self.points[-1].close
        start = self.points[-1 - sessions].close
        if start <= 0:
            return None
        return (end - start) / start


__all__ = ["PricePoint", "PriceSeries"]
