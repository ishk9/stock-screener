"""Percentage value object (0–100, with bounds enforcement)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Pct:
    """Percentage in the closed range [0, 100]."""

    value: float

    def __post_init__(self) -> None:
        v = float(self.value)
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"Pct must be within [0, 100]; got {v!r}")
        object.__setattr__(self, "value", round(v, 4))

    @classmethod
    def from_ratio(cls, ratio: float) -> "Pct":
        """Build from a 0..1 ratio (clamped)."""
        clamped = max(0.0, min(1.0, float(ratio)))
        return cls(clamped * 100.0)

    @property
    def as_ratio(self) -> float:
        return self.value / 100.0

    def __str__(self) -> str:
        return f"{self.value:.2f}%"


__all__ = ["Pct"]
