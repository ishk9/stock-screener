"""Investment horizon value object."""

from __future__ import annotations

from enum import Enum


class Horizon(str, Enum):
    """Suggested holding period buckets."""

    SHORT = "short"   # < 6 months
    MID = "mid"       # 6–24 months
    LONG = "long"     # 24+ months

    @property
    def months(self) -> tuple[int, int]:
        return {
            Horizon.SHORT: (0, 6),
            Horizon.MID: (6, 24),
            Horizon.LONG: (24, 120),
        }[self]

    @property
    def label(self) -> str:
        return {
            Horizon.SHORT: "Short term (< 6m)",
            Horizon.MID: "Medium term (6–24m)",
            Horizon.LONG: "Long term (2y+)",
        }[self]


__all__ = ["Horizon"]
