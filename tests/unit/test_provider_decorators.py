"""Unit tests for the provider decorators."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from stock_screener.core.errors import (
    DataQualityError,
    RateLimitError,
    UnavailableError,
)
from stock_screener.core.events import (
    Event,
    EventBus,
    ProviderCallCompleted,
    ProviderCallStarted,
    ProviderFailed,
)
from stock_screener.core.result import Err, Ok
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.providers.decorators import (
    CachingFundamentalsProvider,
    CachingPriceProvider,
    CircuitBreakerFundamentalsProvider,
    LoggingFundamentalsProvider,
    LoggingPriceProvider,
    RetryingFundamentalsProvider,
    RetryingPriceProvider,
)

from tests.conftest import FakeFundamentalsProvider, FakePriceProvider, InMemoryCache


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #
class TestCachingFundamentals:
    async def test_miss_calls_inner_then_caches(
        self, sample_fundamentals: Any, symbol_reliance: Any, memory_cache: InMemoryCache
    ) -> None:
        inner = FakeFundamentalsProvider([Ok(sample_fundamentals)])
        cached = CachingFundamentalsProvider(inner, memory_cache, ttl=timedelta(hours=1))

        result = await cached.get_fundamentals(symbol_reliance)

        assert result.is_ok()
        assert len(inner.calls) == 1
        assert memory_cache.set_calls == 1

    async def test_hit_skips_inner(
        self, sample_fundamentals: Any, symbol_reliance: Any, memory_cache: InMemoryCache
    ) -> None:
        inner = FakeFundamentalsProvider([Ok(sample_fundamentals)])
        cached = CachingFundamentalsProvider(inner, memory_cache, ttl=timedelta(hours=1))

        first = await cached.get_fundamentals(symbol_reliance)
        second = await cached.get_fundamentals(symbol_reliance)

        assert first.is_ok() and second.is_ok()
        assert len(inner.calls) == 1
        assert second.unwrap() == sample_fundamentals

    async def test_err_not_cached(
        self, symbol_reliance: Any, memory_cache: InMemoryCache
    ) -> None:
        inner = FakeFundamentalsProvider([Err(UnavailableError("oops"))])
        cached = CachingFundamentalsProvider(inner, memory_cache, ttl=timedelta(hours=1))

        result = await cached.get_fundamentals(symbol_reliance)

        assert result.is_err()
        assert memory_cache.set_calls == 0


class TestCachingPrice:
    async def test_miss_then_hit(
        self, sample_price_series: Any, symbol_reliance: Any, memory_cache: InMemoryCache
    ) -> None:
        inner = FakePriceProvider([Ok(sample_price_series)])
        cached = CachingPriceProvider(inner, memory_cache, ttl=timedelta(hours=1))

        first = await cached.get_prices(symbol_reliance, timedelta(days=365))
        second = await cached.get_prices(symbol_reliance, timedelta(days=365))

        assert first.is_ok() and second.is_ok()
        assert len(inner.calls) == 1


# --------------------------------------------------------------------------- #
# Retry
# --------------------------------------------------------------------------- #
class TestRetryingFundamentals:
    async def test_success_after_two_transient_failures(
        self, sample_fundamentals: Any, symbol_reliance: Any
    ) -> None:
        inner = FakeFundamentalsProvider(
            [
                Err(RateLimitError("a")),
                Err(UnavailableError("b")),
                Ok(sample_fundamentals),
            ]
        )

        async def _no_sleep(_: float) -> None:
            return None

        retried = RetryingFundamentalsProvider(
            inner, attempts=4, initial_s=0.0, max_wait_s=0.0, sleep=_no_sleep
        )

        result = await retried.get_fundamentals(symbol_reliance)

        assert result.is_ok()
        assert len(inner.calls) == 3

    async def test_exhausts_returns_last_err(self, symbol_reliance: Any) -> None:
        inner = FakeFundamentalsProvider(
            [
                Err(RateLimitError("a")),
                Err(RateLimitError("b")),
                Err(UnavailableError("final")),
            ]
        )

        async def _no_sleep(_: float) -> None:
            return None

        retried = RetryingFundamentalsProvider(
            inner, attempts=3, initial_s=0.0, max_wait_s=0.0, sleep=_no_sleep
        )

        result = await retried.get_fundamentals(symbol_reliance)

        assert result.is_err()
        assert isinstance(result, Err)
        assert isinstance(result.error, UnavailableError)
        assert "final" in str(result.error)
        assert len(inner.calls) == 3

    async def test_non_transient_short_circuits(self, symbol_reliance: Any) -> None:
        inner = FakeFundamentalsProvider([Err(DataQualityError("bad"))])

        retried = RetryingFundamentalsProvider(
            inner, attempts=4, initial_s=0.0, max_wait_s=0.0
        )

        result = await retried.get_fundamentals(symbol_reliance)

        assert result.is_err()
        assert len(inner.calls) == 1

    async def test_invalid_attempts(self) -> None:
        inner = FakeFundamentalsProvider([])
        with pytest.raises(ValueError):
            RetryingFundamentalsProvider(inner, attempts=0)


class TestRetryingPrice:
    async def test_retry_price(
        self, sample_price_series: Any, symbol_reliance: Any
    ) -> None:
        inner = FakePriceProvider(
            [Err(UnavailableError("a")), Ok(sample_price_series)]
        )

        async def _no_sleep(_: float) -> None:
            return None

        retried = RetryingPriceProvider(
            inner, attempts=3, initial_s=0.0, max_wait_s=0.0, sleep=_no_sleep
        )

        result = await retried.get_prices(symbol_reliance, timedelta(days=30))

        assert result.is_ok()
        assert len(inner.calls) == 2


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
class TestLogging:
    async def test_publishes_started_and_completed_on_ok(
        self,
        sample_fundamentals: Any,
        symbol_reliance: Any,
        event_bus: EventBus,
    ) -> None:
        events: list[Event] = []
        event_bus.subscribe_all(events.append)

        inner = FakeFundamentalsProvider([Ok(sample_fundamentals)], name="x")
        wrapped = LoggingFundamentalsProvider(inner, bus=event_bus)

        await wrapped.get_fundamentals(symbol_reliance)

        kinds = [type(e) for e in events]
        assert ProviderCallStarted in kinds
        assert ProviderCallCompleted in kinds
        assert ProviderFailed not in kinds

    async def test_publishes_failed_on_err(
        self, symbol_reliance: Any, event_bus: EventBus
    ) -> None:
        events: list[Event] = []
        event_bus.subscribe_all(events.append)

        inner = FakeFundamentalsProvider([Err(UnavailableError("nope"))], name="x")
        wrapped = LoggingFundamentalsProvider(inner, bus=event_bus)

        await wrapped.get_fundamentals(symbol_reliance)

        kinds = [type(e) for e in events]
        assert ProviderCallStarted in kinds
        assert ProviderFailed in kinds
        assert ProviderCallCompleted not in kinds

    async def test_logging_price_publishes_events(
        self,
        sample_price_series: Any,
        symbol_reliance: Any,
        event_bus: EventBus,
    ) -> None:
        events: list[Event] = []
        event_bus.subscribe_all(events.append)

        inner = FakePriceProvider([Ok(sample_price_series)], name="px")
        wrapped = LoggingPriceProvider(inner, bus=event_bus)

        await wrapped.get_prices(symbol_reliance, timedelta(days=7))

        kinds = [type(e) for e in events]
        assert ProviderCallStarted in kinds
        assert ProviderCallCompleted in kinds


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #
class _Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class TestCircuitBreaker:
    async def test_opens_after_threshold_short_circuits(
        self, symbol_reliance: Any
    ) -> None:
        clock = _Clock()
        inner = FakeFundamentalsProvider(
            [Err(UnavailableError(f"f{i}")) for i in range(3)]
        )

        cb = CircuitBreakerFundamentalsProvider(
            inner, threshold=3, cooldown_s=10.0, clock=clock
        )

        for _ in range(3):
            res = await cb.get_fundamentals(symbol_reliance)
            assert res.is_err()

        assert cb.is_open
        assert len(inner.calls) == 3

        short = await cb.get_fundamentals(symbol_reliance)
        assert short.is_err()
        assert isinstance(short, Err)
        assert isinstance(short.error, UnavailableError)
        assert "circuit open" in str(short.error)
        assert len(inner.calls) == 3

    async def test_recovers_after_cooldown(
        self, sample_fundamentals: Any, symbol_reliance: Any
    ) -> None:
        clock = _Clock()
        inner = FakeFundamentalsProvider(
            [
                Err(UnavailableError("a")),
                Err(UnavailableError("b")),
                Ok(sample_fundamentals),
            ]
        )

        cb = CircuitBreakerFundamentalsProvider(
            inner, threshold=2, cooldown_s=5.0, clock=clock
        )

        for _ in range(2):
            await cb.get_fundamentals(symbol_reliance)

        assert cb.is_open

        short = await cb.get_fundamentals(symbol_reliance)
        assert short.is_err()
        assert len(inner.calls) == 2

        clock.advance(6.0)
        recovered = await cb.get_fundamentals(symbol_reliance)
        assert recovered.is_ok()
        assert not cb.is_open

    async def test_success_resets_failures(
        self, sample_fundamentals: Any, symbol_reliance: Any
    ) -> None:
        inner = FakeFundamentalsProvider(
            [
                Err(UnavailableError("a")),
                Ok(sample_fundamentals),
                Err(UnavailableError("b")),
            ]
        )
        cb = CircuitBreakerFundamentalsProvider(inner, threshold=2, cooldown_s=10.0)

        sym = Symbol(code="X", exchange=Exchange.NSE)
        await cb.get_fundamentals(sym)
        ok = await cb.get_fundamentals(sym)
        assert ok.is_ok()
        again = await cb.get_fundamentals(sym)
        assert again.is_err()
        assert not cb.is_open

    async def test_invalid_threshold(self) -> None:
        inner = FakeFundamentalsProvider([])
        with pytest.raises(ValueError):
            CircuitBreakerFundamentalsProvider(inner, threshold=0)
