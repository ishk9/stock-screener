"""Shared pytest fixtures and helpers for the unit-test suite."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

import pytest

from stock_screener.core.errors import ProviderError
from stock_screener.core.events import EventBus
from stock_screener.core.result import Err, Ok, Result
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


@pytest.fixture
def symbol_reliance() -> Symbol:
    return Symbol(code="RELIANCE", exchange=Exchange.NSE)


@pytest.fixture
def sample_fundamentals() -> Fundamentals:
    return Fundamentals(
        as_of=date(2026, 5, 1),
        pe=18.5,
        pb=2.1,
        roe=0.14,
        debt_to_equity=0.32,
    )


@pytest.fixture
def sample_price_series() -> PriceSeries:
    return PriceSeries.from_points(
        [
            PricePoint(
                on=date(2026, 4, 28),
                open=100.0,
                high=101.5,
                low=99.0,
                close=101.0,
                volume=1_000,
            ),
            PricePoint(
                on=date(2026, 4, 29),
                open=101.0,
                high=102.0,
                low=100.5,
                close=101.8,
                volume=1_200,
            ),
        ]
    )


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


class FakeFundamentalsProvider:
    """Test rig that returns pre-programmed responses in order."""

    def __init__(
        self,
        responses: Iterable[Result[Fundamentals, ProviderError] | Exception],
        *,
        name: str = "fake",
    ) -> None:
        self._responses: list[Result[Fundamentals, ProviderError] | Exception] = list(
            responses
        )
        self.calls: list[Symbol] = []
        self.name = name

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        self.calls.append(symbol)
        if not self._responses:
            raise AssertionError("FakeFundamentalsProvider exhausted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class FakePriceProvider:
    """Test rig that returns pre-programmed price responses in order."""

    def __init__(
        self,
        responses: Iterable[Result[PriceSeries, ProviderError] | Exception],
        *,
        name: str = "fake",
    ) -> None:
        self._responses: list[Result[PriceSeries, ProviderError] | Exception] = list(
            responses
        )
        self.calls: list[tuple[Symbol, timedelta]] = []
        self.name = name

    async def get_prices(
        self, symbol: Symbol, lookback: timedelta
    ) -> Result[PriceSeries, ProviderError]:
        self.calls.append((symbol, lookback))
        if not self._responses:
            raise AssertionError("FakePriceProvider exhausted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class InMemoryCache:
    """Trivial in-memory ``Cache`` implementation for tests."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self.set_calls = 0
        self.get_calls = 0

    def get(self, key: str) -> bytes | None:
        self.get_calls += 1
        return self._store.get(key)

    def set(self, key: str, value: bytes, ttl: timedelta) -> None:  # noqa: ARG002
        self.set_calls += 1
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


@pytest.fixture
def fake_provider_factory() -> Any:
    return FakeFundamentalsProvider


@pytest.fixture
def fake_price_provider_factory() -> Any:
    return FakePriceProvider


@pytest.fixture
def memory_cache() -> InMemoryCache:
    return InMemoryCache()


__all__ = [
    "FakeFundamentalsProvider",
    "FakePriceProvider",
    "InMemoryCache",
    "Ok",
    "Err",
]
