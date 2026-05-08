"""Universe repository port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..entities.company import Company
from ..value_objects.market_cap import MarketCapBucket


@runtime_checkable
class UniverseRepository(Protocol):
    """Persistent storage of the tradable Indian-equity universe."""

    def upsert_many(self, companies: list[Company]) -> None: ...
    def list(self, bucket: MarketCapBucket | None = None) -> list[Company]: ...
    def get(self, code: str) -> Company | None: ...
    def count(self) -> int: ...
    def last_refreshed_at(self) -> str | None: ...


__all__ = ["UniverseRepository"]
