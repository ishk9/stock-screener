"""Conviction value object — bucketed confidence."""

from __future__ import annotations

from enum import Enum


class Conviction(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @classmethod
    def from_score(cls, score: float) -> "Conviction":
        if score >= 75:
            return cls.HIGH
        if score >= 50:
            return cls.MEDIUM
        return cls.LOW


__all__ = ["Conviction"]
