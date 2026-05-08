"""Momentum scoring — multi-window returns + 52-week-high distance."""

from __future__ import annotations

from dataclasses import dataclass

from ...entities.price_series import PriceSeries
from ...entities.snapshot import CompanySnapshot
from ...value_objects.horizon import Horizon
from ...value_objects.score import Score
from .base import NEUTRAL_SCORE


def _scale_return(value: float, *, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 100.0
    return (value - low) / (high - low) * 100.0


def _distance_from_high(prices: PriceSeries, sessions: int = 252) -> float | None:
    closes = prices.closes()
    if not closes:
        return None
    window = closes[-sessions:]
    peak = max(window)
    last = closes[-1]
    if peak <= 0:
        return None
    return (peak - last) / peak


@dataclass(frozen=True, slots=True)
class MomentumScoringStrategy:
    """Trailing returns plus distance-from-52w-high."""

    name: str = "momentum"

    def score(self, snapshot: CompanySnapshot, horizon: Horizon) -> Score:  # noqa: ARG002
        prices = snapshot.prices
        if prices is None:
            return Score(NEUTRAL_SCORE)

        signals: list[float] = []
        windows: list[tuple[int, float, float]] = [
            (21, -0.10, 0.15),
            (63, -0.15, 0.30),
            (126, -0.20, 0.50),
            (252, -0.30, 0.80),
        ]
        for sessions, lo, hi in windows:
            r = prices.return_over(sessions=sessions)
            if r is not None:
                signals.append(_scale_return(r, low=lo, high=hi))

        dist = _distance_from_high(prices, 252)
        if dist is not None:
            distance_score = max(0.0, 100.0 - min(1.0, dist / 0.5) * 100.0)
            signals.append(distance_score)

        if not signals:
            return Score(NEUTRAL_SCORE)
        return Score.clamped(sum(signals) / len(signals))


__all__ = ["MomentumScoringStrategy"]
