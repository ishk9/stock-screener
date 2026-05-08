"""Growth scoring — higher CAGR/yoy → higher score."""

from __future__ import annotations

from dataclasses import dataclass

from ...entities.snapshot import CompanySnapshot
from ...value_objects.horizon import Horizon
from ...value_objects.score import Score
from .base import NEUTRAL_SCORE


def _bucket_growth(value: float | None, *, low: float, high: float) -> float | None:
    if value is None:
        return None
    v = float(value)
    if v <= low:
        return 0.0
    if v >= high:
        return 100.0
    return (v - low) / (high - low) * 100.0


@dataclass(frozen=True, slots=True)
class GrowthScoringStrategy:
    """Reads revenue / earnings CAGR + recent yoy profit growth."""

    name: str = "growth"

    def score(self, snapshot: CompanySnapshot, horizon: Horizon) -> Score:  # noqa: ARG002
        f = snapshot.fundamentals
        if f is None:
            return Score(NEUTRAL_SCORE)

        signals: list[float] = []
        rev = _bucket_growth(f.revenue_cagr_3y, low=0.0, high=30.0)
        eps = _bucket_growth(f.eps_cagr_3y, low=0.0, high=35.0)
        yoy = _bucket_growth(f.profit_growth_yoy, low=-10.0, high=40.0)
        for s in (rev, eps, yoy):
            if s is not None:
                signals.append(s)

        if not signals:
            return Score(NEUTRAL_SCORE)
        return Score.clamped(sum(signals) / len(signals))


__all__ = ["GrowthScoringStrategy"]
