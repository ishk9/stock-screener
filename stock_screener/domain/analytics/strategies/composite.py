"""Composite scoring — weighted mean of part strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ...entities.snapshot import CompanySnapshot
from ...value_objects.horizon import Horizon
from ...value_objects.score import Score
from .base import NEUTRAL_SCORE, ScoringStrategy
from .growth import GrowthScoringStrategy
from .momentum import MomentumScoringStrategy
from .quality import QualityScoringStrategy
from .value import ValueScoringStrategy


@dataclass(frozen=True, slots=True)
class CompositeScoringStrategy:
    """Combines several ``ScoringStrategy`` parts via a weighted mean.

    Weights need not sum to 1 — they are renormalised at score time. Part
    strategies must all be ``ScoringStrategy``-compatible objects.
    """

    parts: tuple[tuple[ScoringStrategy, float], ...]
    name: str = "composite"

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("CompositeScoringStrategy needs at least one part")
        for strategy, weight in self.parts:
            if weight < 0:
                raise ValueError(
                    f"weights must be non-negative; got {weight!r} for {strategy.name!r}"
                )
        total = sum(w for _, w in self.parts)
        if total <= 0:
            raise ValueError("at least one weight must be positive")

    def score(self, snapshot: CompanySnapshot, horizon: Horizon) -> Score:
        total_w = sum(w for _, w in self.parts)
        if total_w <= 0:
            return Score(NEUTRAL_SCORE)
        acc = 0.0
        for strat, w in self.parts:
            if w <= 0:
                continue
            acc += strat.score(snapshot, horizon).value * (w / total_w)
        return Score.clamped(acc)

    @classmethod
    def make_default(cls, weights: dict[str, float]) -> "CompositeScoringStrategy":
        registry: dict[str, ScoringStrategy] = {
            "value": ValueScoringStrategy(),
            "growth": GrowthScoringStrategy(),
            "quality": QualityScoringStrategy(),
            "momentum": MomentumScoringStrategy(),
        }
        unknown = set(weights) - set(registry)
        if unknown:
            raise ValueError(f"unknown strategy keys: {sorted(unknown)}")
        if not weights:
            raise ValueError("weights mapping must not be empty")
        parts: list[tuple[ScoringStrategy, float]] = []
        for key, w in weights.items():
            parts.append((registry[key], float(w)))
        return cls(parts=tuple(parts))


def make_default(weights: dict[str, float]) -> CompositeScoringStrategy:
    """Module-level shortcut for ``CompositeScoringStrategy.make_default``."""

    return CompositeScoringStrategy.make_default(weights)


__all__ = ["CompositeScoringStrategy", "make_default"]
