"""Composite providers that try a primary source, then ordered fallbacks."""

from __future__ import annotations

from datetime import timedelta

import structlog

from ...core.errors import ProviderError
from ...core.events import EventBus, ProviderCallCompleted, ProviderFailed
from ...core.result import Err, Ok, Result
from ...domain.entities.fundamentals import Fundamentals
from ...domain.entities.price_series import PriceSeries
from ...domain.ports.market_data import FundamentalsProvider, PriceProvider
from ...domain.value_objects.symbol import Symbol

log = structlog.get_logger(__name__)


class CompositeFundamentalsProvider:
    """Tries ``primary`` first, then each fallback in order."""

    def __init__(
        self,
        primary: FundamentalsProvider,
        *fallbacks: FundamentalsProvider,
        bus: EventBus | None = None,
    ) -> None:
        self._members: tuple[FundamentalsProvider, ...] = (primary, *fallbacks)
        self._bus = bus

    @property
    def name(self) -> str:
        return "composite"

    @property
    def members(self) -> tuple[FundamentalsProvider, ...]:
        return self._members

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        last_err: Err[ProviderError] | None = None
        for provider in self._members:
            result = await provider.get_fundamentals(symbol)
            if result.is_ok():
                self._publish_success(provider.name, "get_fundamentals")
                log.info(
                    "composite.fundamentals.success",
                    provider=provider.name,
                    symbol=symbol.yahoo(),
                )
                return result
            assert isinstance(result, Err)
            last_err = result
            self._publish_failure(provider.name, "get_fundamentals", result.error)
        assert last_err is not None
        return last_err

    def _publish_success(self, provider_name: str, op: str) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            ProviderCallCompleted(provider=provider_name, operation=op, duration_ms=0.0)
        )

    def _publish_failure(self, provider_name: str, op: str, err: ProviderError) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            ProviderFailed(provider=provider_name, operation=op, error=str(err))
        )


class CompositePriceProvider:
    """Tries ``primary`` first, then each fallback in order."""

    def __init__(
        self,
        primary: PriceProvider,
        *fallbacks: PriceProvider,
        bus: EventBus | None = None,
    ) -> None:
        self._members: tuple[PriceProvider, ...] = (primary, *fallbacks)
        self._bus = bus

    @property
    def name(self) -> str:
        return "composite"

    @property
    def members(self) -> tuple[PriceProvider, ...]:
        return self._members

    async def get_prices(
        self, symbol: Symbol, lookback: timedelta
    ) -> Result[PriceSeries, ProviderError]:
        last_err: Err[ProviderError] | None = None
        for provider in self._members:
            result = await provider.get_prices(symbol, lookback)
            if result.is_ok():
                if self._bus is not None:
                    self._bus.publish(
                        ProviderCallCompleted(
                            provider=provider.name,
                            operation="get_prices",
                            duration_ms=0.0,
                        )
                    )
                log.info(
                    "composite.prices.success",
                    provider=provider.name,
                    symbol=symbol.yahoo(),
                )
                return result
            assert isinstance(result, Err)
            last_err = result
            if self._bus is not None:
                self._bus.publish(
                    ProviderFailed(
                        provider=provider.name,
                        operation="get_prices",
                        error=str(result.error),
                    )
                )
        assert last_err is not None
        return last_err


__all__ = ["CompositeFundamentalsProvider", "CompositePriceProvider"]
