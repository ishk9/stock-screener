"""Unit tests for CompositeFundamentalsProvider / CompositePriceProvider."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from stock_screener.core.errors import DataQualityError, UnavailableError
from stock_screener.core.events import (
    Event,
    EventBus,
    ProviderCallCompleted,
    ProviderFailed,
)
from stock_screener.core.result import Err, Ok
from stock_screener.infra.providers.composite_provider import (
    CompositeFundamentalsProvider,
    CompositePriceProvider,
)

from tests.conftest import FakeFundamentalsProvider, FakePriceProvider


class TestCompositeFundamentals:
    async def test_primary_ok_skips_fallbacks(
        self, sample_fundamentals: Any, symbol_reliance: Any
    ) -> None:
        primary = FakeFundamentalsProvider([Ok(sample_fundamentals)], name="p")
        fb = FakeFundamentalsProvider([Ok(sample_fundamentals)], name="fb")

        composite = CompositeFundamentalsProvider(primary, fb)
        result = await composite.get_fundamentals(symbol_reliance)

        assert result.is_ok()
        assert len(primary.calls) == 1
        assert len(fb.calls) == 0
        assert composite.name == "composite"

    async def test_primary_fails_fallback_used(
        self, sample_fundamentals: Any, symbol_reliance: Any, event_bus: EventBus
    ) -> None:
        events: list[Event] = []
        event_bus.subscribe_all(events.append)

        primary = FakeFundamentalsProvider([Err(UnavailableError("oops"))], name="p")
        fb = FakeFundamentalsProvider([Ok(sample_fundamentals)], name="fb")

        composite = CompositeFundamentalsProvider(primary, fb, bus=event_bus)
        result = await composite.get_fundamentals(symbol_reliance)

        assert result.is_ok()
        assert len(primary.calls) == 1
        assert len(fb.calls) == 1

        kinds = [type(e) for e in events]
        assert ProviderFailed in kinds
        assert ProviderCallCompleted in kinds

    async def test_all_fail_returns_last_err(self, symbol_reliance: Any) -> None:
        primary = FakeFundamentalsProvider([Err(UnavailableError("first"))], name="p")
        fb1 = FakeFundamentalsProvider([Err(DataQualityError("middle"))], name="fb1")
        fb2 = FakeFundamentalsProvider([Err(UnavailableError("last"))], name="fb2")

        composite = CompositeFundamentalsProvider(primary, fb1, fb2)
        result = await composite.get_fundamentals(symbol_reliance)

        assert result.is_err()
        assert isinstance(result, Err)
        assert "last" in str(result.error)

    async def test_members_property(self) -> None:
        primary = FakeFundamentalsProvider([], name="p")
        fb = FakeFundamentalsProvider([], name="fb")
        composite = CompositeFundamentalsProvider(primary, fb)
        assert composite.members == (primary, fb)


class TestCompositePrice:
    async def test_primary_ok(
        self, sample_price_series: Any, symbol_reliance: Any
    ) -> None:
        primary = FakePriceProvider([Ok(sample_price_series)], name="p")
        fb = FakePriceProvider([Ok(sample_price_series)], name="fb")

        composite = CompositePriceProvider(primary, fb)
        result = await composite.get_prices(symbol_reliance, timedelta(days=30))

        assert result.is_ok()
        assert len(primary.calls) == 1
        assert len(fb.calls) == 0

    async def test_falls_back(
        self, sample_price_series: Any, symbol_reliance: Any
    ) -> None:
        primary = FakePriceProvider([Err(UnavailableError("nope"))], name="p")
        fb = FakePriceProvider([Ok(sample_price_series)], name="fb")

        composite = CompositePriceProvider(primary, fb)
        result = await composite.get_prices(symbol_reliance, timedelta(days=30))

        assert result.is_ok()
        assert len(primary.calls) == 1
        assert len(fb.calls) == 1

    async def test_all_fail(self, symbol_reliance: Any) -> None:
        primary = FakePriceProvider([Err(UnavailableError("a"))], name="p")
        fb = FakePriceProvider([Err(UnavailableError("b"))], name="fb")

        composite = CompositePriceProvider(primary, fb)
        result = await composite.get_prices(symbol_reliance, timedelta(days=7))

        assert result.is_err()
        assert isinstance(result, Err)
        assert "b" in str(result.error)
