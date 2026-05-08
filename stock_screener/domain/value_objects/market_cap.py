"""Market-capitalisation bucket (SEBI-aligned).

Top 100 listed companies by m-cap → Large.
Next 150 (rank 101–250)            → Mid.
Rank 251 and beyond                → Small.

Refreshed semi-annually upstream; the bucket is materialised onto every
``Company`` entity at universe-refresh time.
"""

from __future__ import annotations

from enum import Enum

LARGE_CAP_TOP_N = 100
MID_CAP_END_N = 250  # ranks 101..250


class MarketCapBucket(str, Enum):
    LARGE = "lg"
    MID = "md"
    SMALL = "sm"

    @classmethod
    def from_short_code(cls, code: str) -> "MarketCapBucket":
        c = code.strip().lower()
        try:
            return cls(c)
        except ValueError as exc:
            raise ValueError(
                f"Unknown market-cap code {code!r}; expected one of: lg | md | sm"
            ) from exc

    @classmethod
    def from_rank(cls, rank: int) -> "MarketCapBucket":
        if rank < 1:
            raise ValueError(f"Rank must be >= 1; got {rank!r}")
        if rank <= LARGE_CAP_TOP_N:
            return cls.LARGE
        if rank <= MID_CAP_END_N:
            return cls.MID
        return cls.SMALL

    @property
    def label(self) -> str:
        return {
            MarketCapBucket.LARGE: "Large cap",
            MarketCapBucket.MID: "Mid cap",
            MarketCapBucket.SMALL: "Small cap",
        }[self]


__all__ = ["MarketCapBucket", "LARGE_CAP_TOP_N", "MID_CAP_END_N"]
