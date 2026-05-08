"""Filtering and ranking policy for recommendation lists."""

from __future__ import annotations

from typing import Sequence, TypeVar

from ..entities.recommendation import Recommendation
from ..specifications import Specification

T = TypeVar("T")


def apply_specifications(items: Sequence[T], spec: Specification[T]) -> list[T]:
    """Return items that satisfy ``spec`` (order preserved)."""

    return [item for item in items if spec.is_satisfied_by(item)]


def rank_top(recs: Sequence[Recommendation], k: int) -> list[Recommendation]:
    """Top-``k`` recommendations by score desc, tie-breaking by lower risk."""

    if k <= 0:
        return []
    ordered = sorted(recs, key=lambda r: (-r.score.value, r.risk_pct.value))
    return ordered[:k]


__all__ = ["apply_specifications", "rank_top"]
