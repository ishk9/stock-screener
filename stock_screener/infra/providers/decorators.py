"""Cross-cutting decorators for provider adapters.

Each decorator wraps an inner provider and itself satisfies the same domain
Protocol (``FundamentalsProvider`` / ``PriceProvider``), so they can be freely
composed in :mod:`bootstrap`.

Retry strategy
--------------
``tenacity`` retries on **raised** exceptions, but our adapters return a
``Result``. Rather than convert to exceptions and back at every layer, we run
a manual loop here that mirrors ``wait_exponential_jitter`` semantics. The
loop is short, dependency-free, and easy to test (inject a no-op ``sleep``).
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import date, timedelta
from typing import Awaitable, Callable

import structlog

from ...core.errors import (
    ProviderError,
    RateLimitError,
    UnavailableError,
)
from ...core.events import (
    EventBus,
    ProviderCallCompleted,
    ProviderCallStarted,
    ProviderFailed,
)
from ...core.result import Err, Ok, Result
from ...domain.entities.fundamentals import Fundamentals
from ...domain.entities.price_series import PricePoint, PriceSeries
from ...domain.ports.cache import Cache
from ...domain.ports.market_data import FundamentalsProvider, PriceProvider
from ...domain.value_objects.symbol import Symbol

log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #
def _fundamentals_to_bytes(f: Fundamentals) -> bytes:
    return f.model_dump_json().encode("utf-8")


def _fundamentals_from_bytes(data: bytes) -> Fundamentals:
    return Fundamentals.model_validate_json(data.decode("utf-8"))


def _price_series_to_bytes(p: PriceSeries) -> bytes:
    payload = [
        {
            "on": pt.on.isoformat(),
            "open": pt.open,
            "high": pt.high,
            "low": pt.low,
            "close": pt.close,
            "volume": pt.volume,
        }
        for pt in p.points
    ]
    return json.dumps(payload).encode("utf-8")


def _price_series_from_bytes(data: bytes) -> PriceSeries:
    rows = json.loads(data.decode("utf-8"))
    points = tuple(
        PricePoint(
            on=date.fromisoformat(row["on"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in rows
    )
    return PriceSeries(points=points)


class CachingFundamentalsProvider:
    """Caches successful ``Fundamentals`` payloads in the provided ``Cache``."""

    def __init__(
        self,
        inner: FundamentalsProvider,
        cache: Cache,
        ttl: timedelta,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    @property
    def name(self) -> str:
        return f"caching({self._inner.name})"

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        key = f"fundamentals:{symbol.yahoo()}"
        cached = self._cache.get(key)
        if cached is not None:
            try:
                return Ok(_fundamentals_from_bytes(cached))
            except Exception:  # noqa: BLE001 — corrupt cache, fall through to inner
                self._cache.delete(key)

        result = await self._inner.get_fundamentals(symbol)
        if result.is_ok():
            assert isinstance(result, Ok)
            self._cache.set(key, _fundamentals_to_bytes(result.value), self._ttl)
        return result


class CachingPriceProvider:
    """Caches successful ``PriceSeries`` payloads keyed by symbol + lookback."""

    def __init__(
        self,
        inner: PriceProvider,
        cache: Cache,
        ttl: timedelta,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    @property
    def name(self) -> str:
        return f"caching({self._inner.name})"

    async def get_prices(
        self, symbol: Symbol, lookback: timedelta
    ) -> Result[PriceSeries, ProviderError]:
        key = f"prices:{symbol.yahoo()}:{lookback.total_seconds()}"
        cached = self._cache.get(key)
        if cached is not None:
            try:
                return Ok(_price_series_from_bytes(cached))
            except Exception:  # noqa: BLE001
                self._cache.delete(key)

        result = await self._inner.get_prices(symbol, lookback)
        if result.is_ok():
            assert isinstance(result, Ok)
            self._cache.set(key, _price_series_to_bytes(result.value), self._ttl)
        return result


# --------------------------------------------------------------------------- #
# Retry
# --------------------------------------------------------------------------- #
SleepFn = Callable[[float], Awaitable[None]]


def _exp_jitter_wait(attempt: int, *, initial: float, max_wait: float) -> float:
    base = min(max_wait, initial * (2 ** attempt))
    if base <= 0:
        return 0.0
    return random.uniform(0.0, base)


class RetryingFundamentalsProvider:
    """Re-issues calls on transient ``ProviderError`` subclasses."""

    def __init__(
        self,
        inner: FundamentalsProvider,
        attempts: int = 4,
        *,
        initial_s: float = 0.5,
        max_wait_s: float = 8.0,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        self._inner = inner
        self._attempts = attempts
        self._initial_s = initial_s
        self._max_wait_s = max_wait_s
        self._sleep = sleep

    @property
    def name(self) -> str:
        return f"retrying({self._inner.name})"

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        last: Err[ProviderError] | None = None
        for attempt in range(self._attempts):
            result = await self._inner.get_fundamentals(symbol)
            if result.is_ok():
                return result
            assert isinstance(result, Err)
            if not isinstance(result.error, (RateLimitError, UnavailableError)):
                return result
            last = result
            if attempt < self._attempts - 1:
                wait = _exp_jitter_wait(
                    attempt, initial=self._initial_s, max_wait=self._max_wait_s
                )
                if wait > 0:
                    await self._sleep(wait)
        assert last is not None
        return last


class RetryingPriceProvider:
    """Re-issues price calls on transient ``ProviderError`` subclasses."""

    def __init__(
        self,
        inner: PriceProvider,
        attempts: int = 4,
        *,
        initial_s: float = 0.5,
        max_wait_s: float = 8.0,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        self._inner = inner
        self._attempts = attempts
        self._initial_s = initial_s
        self._max_wait_s = max_wait_s
        self._sleep = sleep

    @property
    def name(self) -> str:
        return f"retrying({self._inner.name})"

    async def get_prices(
        self, symbol: Symbol, lookback: timedelta
    ) -> Result[PriceSeries, ProviderError]:
        last: Err[ProviderError] | None = None
        for attempt in range(self._attempts):
            result = await self._inner.get_prices(symbol, lookback)
            if result.is_ok():
                return result
            assert isinstance(result, Err)
            if not isinstance(result.error, (RateLimitError, UnavailableError)):
                return result
            last = result
            if attempt < self._attempts - 1:
                wait = _exp_jitter_wait(
                    attempt, initial=self._initial_s, max_wait=self._max_wait_s
                )
                if wait > 0:
                    await self._sleep(wait)
        assert last is not None
        return last


# --------------------------------------------------------------------------- #
# Logging / observability
# --------------------------------------------------------------------------- #
class _LoggingMixin:
    _bus: EventBus | None
    _provider_name: str

    def _emit_started(self, op: str) -> float:
        if self._bus is not None:
            self._bus.publish(
                ProviderCallStarted(provider=self._provider_name, operation=op)
            )
        log.info("provider.call.started", provider=self._provider_name, operation=op)
        return time.monotonic()

    def _emit_completed(self, op: str, started_at: float) -> None:
        duration_ms = (time.monotonic() - started_at) * 1000.0
        if self._bus is not None:
            self._bus.publish(
                ProviderCallCompleted(
                    provider=self._provider_name,
                    operation=op,
                    duration_ms=duration_ms,
                )
            )
        log.info(
            "provider.call.completed",
            provider=self._provider_name,
            operation=op,
            duration_ms=duration_ms,
        )

    def _emit_failed(self, op: str, error: ProviderError) -> None:
        if self._bus is not None:
            self._bus.publish(
                ProviderFailed(
                    provider=self._provider_name,
                    operation=op,
                    error=str(error),
                )
            )
        log.warning(
            "provider.call.failed",
            provider=self._provider_name,
            operation=op,
            error=str(error),
        )


class LoggingFundamentalsProvider(_LoggingMixin):
    def __init__(
        self,
        inner: FundamentalsProvider,
        *,
        bus: EventBus | None = None,
    ) -> None:
        self._inner = inner
        self._bus = bus
        self._provider_name = inner.name

    @property
    def name(self) -> str:
        return self._inner.name

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        started = self._emit_started("get_fundamentals")
        result = await self._inner.get_fundamentals(symbol)
        if result.is_ok():
            self._emit_completed("get_fundamentals", started)
        else:
            assert isinstance(result, Err)
            self._emit_failed("get_fundamentals", result.error)
        return result


class LoggingPriceProvider(_LoggingMixin):
    def __init__(
        self,
        inner: PriceProvider,
        *,
        bus: EventBus | None = None,
    ) -> None:
        self._inner = inner
        self._bus = bus
        self._provider_name = inner.name

    @property
    def name(self) -> str:
        return self._inner.name

    async def get_prices(
        self, symbol: Symbol, lookback: timedelta
    ) -> Result[PriceSeries, ProviderError]:
        started = self._emit_started("get_prices")
        result = await self._inner.get_prices(symbol, lookback)
        if result.is_ok():
            self._emit_completed("get_prices", started)
        else:
            assert isinstance(result, Err)
            self._emit_failed("get_prices", result.error)
        return result


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #
ClockFn = Callable[[], float]


class CircuitBreakerFundamentalsProvider:
    """Trip after N consecutive failures, short-circuit for ``cooldown_s``."""

    def __init__(
        self,
        inner: FundamentalsProvider,
        *,
        threshold: int = 5,
        cooldown_s: float = 30.0,
        clock: ClockFn = time.monotonic,
    ) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self._inner = inner
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def name(self) -> str:
        return f"circuit({self._inner.name})"

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        if self._opened_at is not None:
            now = self._clock()
            if now - self._opened_at < self._cooldown_s:
                return Err(UnavailableError("circuit open"))
            self._opened_at = None
            self._failures = 0

        result = await self._inner.get_fundamentals(symbol)
        if result.is_ok():
            self._failures = 0
            self._opened_at = None
            return result

        assert isinstance(result, Err)
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = self._clock()
        return result


__all__ = [
    "CachingFundamentalsProvider",
    "CachingPriceProvider",
    "RetryingFundamentalsProvider",
    "RetryingPriceProvider",
    "LoggingFundamentalsProvider",
    "LoggingPriceProvider",
    "CircuitBreakerFundamentalsProvider",
]
