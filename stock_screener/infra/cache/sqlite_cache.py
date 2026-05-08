"""SQLite-backed implementation of the ``Cache`` port."""

from __future__ import annotations

import sqlite3
import time
from datetime import timedelta
from pathlib import Path

from ...core.errors import CacheError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value BLOB NOT NULL,
    expires_at REAL NOT NULL
);
"""


class SqliteCache:
    """Opaque key/value cache with TTLs, stored on disk via SQLite."""

    name = "sqlite"

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        try:
            self._conn = sqlite3.connect(
                self._path,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(_SCHEMA)
        except sqlite3.Error as exc:
            raise CacheError(f"Failed to open SQLite cache at {self._path}: {exc}") from exc

    def get(self, key: str) -> bytes | None:
        try:
            row = self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?",
                (key,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise CacheError(f"cache.get failed: {exc}") from exc

        if row is None:
            return None
        value, expires_at = row
        if expires_at <= time.time():
            self._safe_delete(key)
            return None
        return bytes(value)

    def set(self, key: str, value: bytes, ttl: timedelta) -> None:
        if not isinstance(value, (bytes, bytearray)):
            raise CacheError(f"cache.set value must be bytes; got {type(value).__name__}")
        expires_at = time.time() + max(0.0, ttl.total_seconds())
        try:
            self._conn.execute(
                "INSERT INTO cache(key, value, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "expires_at=excluded.expires_at",
                (key, bytes(value), expires_at),
            )
        except sqlite3.Error as exc:
            raise CacheError(f"cache.set failed: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        except sqlite3.Error as exc:
            raise CacheError(f"cache.delete failed: {exc}") from exc

    def clear(self) -> None:
        try:
            self._conn.execute("DELETE FROM cache")
        except sqlite3.Error as exc:
            raise CacheError(f"cache.clear failed: {exc}") from exc

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def _safe_delete(self, key: str) -> None:
        try:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        except sqlite3.Error:
            pass


__all__ = ["SqliteCache"]
