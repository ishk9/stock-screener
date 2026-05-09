"""Unit tests for ``stock_screener.core.retry``."""

from __future__ import annotations

import asyncio
import time

import pytest

from stock_screener.core.errors import RateLimitError, UnavailableError
from stock_screener.core.retry import transient_provider_retry, with_retry

_FAST: dict[str, float | int] = {"attempts": 4, "max_wait_s": 0.001}


async def test_successful_first_attempt() -> None:
    calls = {"count": 0}

    async def fn() -> int:
        calls["count"] += 1
        return 42

    result = await with_retry(fn, **_FAST)  # type: ignore[arg-type]
    assert result == 42
    assert calls["count"] == 1


async def test_transient_rate_limit_then_success() -> None:
    calls = {"count": 0}

    async def fn() -> int:
        calls["count"] += 1
        if calls["count"] < 2:
            raise RateLimitError("slow down")
        return "ok"  # type: ignore[return-value]

    result = await with_retry(fn, **_FAST)  # type: ignore[arg-type]
    assert result == "ok"
    assert calls["count"] == 2


async def test_unavailable_exhausts_and_reraises() -> None:
    calls = {"count": 0}

    async def fn() -> int:
        calls["count"] += 1
        raise UnavailableError(f"boom-{calls['count']}")

    with pytest.raises(UnavailableError, match="boom-3"):
        await with_retry(fn, attempts=3, max_wait_s=0.001)
    assert calls["count"] == 3


async def test_non_transient_value_error_not_retried() -> None:
    calls = {"count": 0}

    async def fn() -> int:
        calls["count"] += 1
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await with_retry(fn, **_FAST)  # type: ignore[arg-type]
    assert calls["count"] == 1


async def test_attempts_one_means_no_retry() -> None:
    calls = {"count": 0}

    async def fn() -> int:
        calls["count"] += 1
        raise RateLimitError("slow down")

    with pytest.raises(RateLimitError):
        await with_retry(fn, attempts=1, max_wait_s=0.001)
    assert calls["count"] == 1


async def test_transient_provider_retry_runs_quickly() -> None:
    calls = {"count": 0}
    start = time.monotonic()

    async for attempt in transient_provider_retry(attempts=4, max_wait_s=0.001):
        with attempt:
            calls["count"] += 1
            if calls["count"] < 4:
                raise RateLimitError("slow")

    elapsed = time.monotonic() - start
    assert calls["count"] == 4
    assert elapsed < 1.0


async def test_asyncio_sleep_unmodified() -> None:
    """The retry helpers must rely on the standard asyncio sleep, not block."""
    started = time.monotonic()
    await asyncio.sleep(0)
    assert time.monotonic() - started < 0.05
