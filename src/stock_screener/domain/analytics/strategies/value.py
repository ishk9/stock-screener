"""Value scoring — cheaper multiples + dividend yield → higher score."""

from __future__ import annotations

from dataclasses import dataclass

from ...entities.snapshot import CompanySnapshot
from ...value_objects.horizon import Horizon
from ...value_objects.score import Score
from .base import NEUTRAL_SCORE


def _piecewise(
    value: float | None,
    *,
    best: float,
    worst: float,
    higher_is_better: bool,
) -> float | None:
    if value is None:
        return None
    v = float(value)
    lo, hi = (best, worst) if higher_is_better else (worst, best)
    if hi == lo:
        return 50.0
    if higher_is_better:
        if v >= best:
            return 100.0
        if v <= worst:
            return 0.0
    else:
        if v <= best:
            return 100.0
        if v >= worst:
            return 0.0
    pos = (v - lo) / (hi - lo)
    return pos * 100.0 if higher_is_better else (1.0 - pos) * 100.0


@dataclass(frozen=True, slots=True)
class ValueScoringStrategy:
    """Cheaper-is-better; bumped slightly by dividend yield."""

    name: str = "value"

    def score(self, snapshot: CompanySnapshot, horizon: Horizon) -> Score:  # noqa: ARG002
        f = snapshot.fundamentals
        if f is None:
            return Score(NEUTRAL_SCORE)

        signals: list[float] = []
        pe = _piecewise(f.pe, best=10.0, worst=40.0, higher_is_better=False)
        pb = _piecewise(f.pb, best=1.0, worst=8.0, higher_is_better=False)
        ev = _piecewise(f.ev_ebitda, best=6.0, worst=25.0, higher_is_better=False)
        for s in (pe, pb, ev):
            if s is not None:
                signals.append(s)

        dy = f.dividend_yield
        if not signals:
            if dy is not None and dy > 0:
                bumped = NEUTRAL_SCORE + min(15.0, float(dy) * 2.5)
                return Score.clamped(bumped)
            return Score(NEUTRAL_SCORE)

        base = sum(signals) / len(signals)
        if dy is not None:
            base += min(8.0, max(0.0, float(dy)) * 1.2)
        return Score.clamped(base)


__all__ = ["ValueScoringStrategy"]
