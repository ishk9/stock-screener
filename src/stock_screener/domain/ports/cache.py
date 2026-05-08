"""Cache port — opaque key/value with TTL."""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def set(self, key: str, value: bytes, ttl: timedelta) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...


__all__ = ["Cache"]
