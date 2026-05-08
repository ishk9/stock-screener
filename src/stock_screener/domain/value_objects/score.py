"""Score value object — a normalised 0..100 ranking signal."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Score:
    """A normalised score in [0, 100]; higher is better."""

    value: float

    def __post_init__(self) -> None:
        v = float(self.value)
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"Score must be within [0, 100]; got {v!r}")
        object.__setattr__(self, "value", round(v, 4))

    @classmethod
    def clamped(cls, value: float) -> "Score":
        return cls(max(0.0, min(100.0, float(value))))

    def __str__(self) -> str:
        return f"{self.value:.2f}"


__all__ = ["Score"]
