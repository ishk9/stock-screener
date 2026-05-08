"""Quality scoring — high ROE/ROCE/IC, low leverage, healthy FCF conversion."""

from __future__ import annotations

from dataclasses import dataclass

from ...entities.snapshot import CompanySnapshot
from ...value_objects.horizon import Horizon
from ...value_objects.score import Score
from .base import NEUTRAL_SCORE


def _scale(value: float, *, low: float, high: float, higher_is_better: bool) -> float:
    if value <= low:
        return 100.0 if not higher_is_better else 0.0
    if value >= high:
        return 0.0 if not higher_is_better else 100.0
    pos = (value - low) / (high - low)
    return pos * 100.0 if higher_is_better else (1.0 - pos) * 100.0


@dataclass(frozen=True, slots=True)
class QualityScoringStrategy:
    """Capital efficiency, solvency and FCF quality."""

    name: str = "quality"

    def score(self, snapshot: CompanySnapshot, horizon: Horizon) -> Score:  # noqa: ARG002
        f = snapshot.fundamentals
        if f is None:
            return Score(NEUTRAL_SCORE)

        signals: list[float] = []
        if f.roe is not None:
            signals.append(_scale(float(f.roe), low=5.0, high=30.0, higher_is_better=True))
        if f.roce is not None:
            signals.append(_scale(float(f.roce), low=5.0, high=25.0, higher_is_better=True))
        if f.interest_coverage is not None:
            signals.append(
                _scale(float(f.interest_coverage), low=1.0, high=15.0, higher_is_better=True)
            )
        if f.debt_to_equity is not None:
            signals.append(
                _scale(float(f.debt_to_equity), low=0.0, high=2.0, higher_is_better=False)
            )
        if f.free_cash_flow is not None and f.net_profit is not None and f.net_profit > 0:
            ratio = float(f.free_cash_flow) / float(f.net_profit)
            signals.append(_scale(ratio, low=0.0, high=1.0, higher_is_better=True))

        if not signals:
            return Score(NEUTRAL_SCORE)
        return Score.clamped(sum(signals) / len(signals))


__all__ = ["QualityScoringStrategy"]
