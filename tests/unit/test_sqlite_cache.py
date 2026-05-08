"""Tests for ``SqliteCache``."""

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path

import pytest

from stock_screener.core.errors import CacheError
from stock_screener.infra.cache.sqlite_cache import SqliteCache


@pytest.fixture()
def cache(tmp_path: Path) -> SqliteCache:
    return SqliteCache(tmp_path / "cache.db")


def test_get_returns_none_for_missing_key(cache: SqliteCache) -> None:
    assert cache.get("missing") is None


def test_set_then_get_returns_value(cache: SqliteCache) -> None:
    cache.set("k", b"hello", timedelta(seconds=10))
    assert cache.get("k") == b"hello"


def test_set_overwrites_value(cache: SqliteCache) -> None:
    cache.set("k", b"first", timedelta(seconds=10))
    cache.set("k", b"second", timedelta(seconds=10))
    assert cache.get("k") == b"second"


def test_get_returns_none_after_ttl_expires(cache: SqliteCache) -> None:
    cache.set("k", b"x", timedelta(milliseconds=10))
    time.sleep(0.05)
    assert cache.get("k") is None


def test_delete_removes_value(cache: SqliteCache) -> None:
    cache.set("k", b"x", timedelta(seconds=10))
    cache.delete("k")
    assert cache.get("k") is None


def test_delete_missing_key_is_noop(cache: SqliteCache) -> None:
    cache.delete("nope")


def test_clear_removes_all(cache: SqliteCache) -> None:
    cache.set("a", b"1", timedelta(seconds=10))
    cache.set("b", b"2", timedelta(seconds=10))
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_set_rejects_non_bytes_value(cache: SqliteCache) -> None:
    with pytest.raises(CacheError):
        cache.set("k", "not-bytes", timedelta(seconds=10))  # type: ignore[arg-type]
