"""Market-data ports.

Each port is **narrow** by design (ISP). An adapter can implement only the
pieces it actually supports.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol, runtime_checkable

from ...core.errors import ProviderError
from ...core.result import Result
from ..entities.fundamentals import Fundamentals
from ..entities.news import NewsItem
from ..entities.price_series import PriceSeries
from ..value_objects.symbol import Symbol


@runtime_checkable
class FundamentalsProvider(Protocol):
    name: str

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]: ...


@runtime_checkable
class PriceProvider(Protocol):
    name: str

    async def get_prices(
        self, symbol: Symbol, lookback: timedelta
    ) -> Result[PriceSeries, ProviderError]: ...


@runtime_checkable
class NewsProvider(Protocol):
    name: str

    async def get_news(
        self, symbol: Symbol, *, limit: int = 10
    ) -> Result[tuple[NewsItem, ...], ProviderError]: ...


@runtime_checkable
class CorporateActionsProvider(Protocol):
    name: str

    async def get_actions(
        self, symbol: Symbol
    ) -> Result[tuple[dict, ...], ProviderError]: ...


__all__ = [
    "FundamentalsProvider",
    "PriceProvider",
    "NewsProvider",
    "CorporateActionsProvider",
]
