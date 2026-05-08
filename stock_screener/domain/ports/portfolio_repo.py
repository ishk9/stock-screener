"""Portfolio repository port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..entities.position import Position


@runtime_checkable
class PortfolioRepository(Protocol):
    """Persistent storage of the user's held positions."""

    def upsert(self, position: Position) -> None: ...
    def remove(self, code: str) -> bool: ...
    def get(self, code: str) -> Position | None: ...
    def list(self) -> list[Position]: ...
    def clear(self) -> None: ...
    def count(self) -> int: ...


__all__ = ["PortfolioRepository"]
