"""Strategy protocol for monotone single-snapshot scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ...entities.snapshot import CompanySnapshot
from ...value_objects.horizon import Horizon
from ...value_objects.score import Score

NEUTRAL_SCORE = 50.0


@dataclass(frozen=True, slots=True)
class ScoreContext:
    """Reserved hook for cross-snapshot context (peer data, sector medians).

    Currently empty — concrete strategies score a single snapshot in
    isolation. Kept here so the signature can grow without a breaking
    change.
    """


@runtime_checkable
class ScoringStrategy(Protocol):
    """A monotone-in-signal, single-snapshot scoring rule."""

    name: str

    def score(self, snapshot: CompanySnapshot, horizon: Horizon) -> Score: ...


__all__ = ["ScoringStrategy", "ScoreContext", "NEUTRAL_SCORE"]
