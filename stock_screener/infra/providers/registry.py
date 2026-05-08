"""Plug-and-play provider registry (Factory pattern).

A central place where short names like ``"yfinance"`` resolve to a concrete
``FundamentalsProvider`` / ``PriceProvider`` instance. Bootstrap code calls
into ``default_registry`` to wire the user's preferred providers based on
``ProvidersConfig``.
"""

from __future__ import annotations

from typing import Callable

from ...core.config import ProvidersConfig
from ...domain.ports.market_data import FundamentalsProvider, PriceProvider
from .screener_in_provider import ScreenerInProvider
from .yfinance_provider import YFinanceProvider

FundamentalsFactory = Callable[[ProvidersConfig], FundamentalsProvider]
PriceFactory = Callable[[ProvidersConfig], PriceProvider]


class ProviderRegistry:
    """Plug-and-play registry: lookup providers by short name."""

    def __init__(self) -> None:
        self._fundamentals: dict[str, FundamentalsFactory] = {}
        self._price: dict[str, PriceFactory] = {}

    def register_fundamentals(
        self, name: str, factory: FundamentalsFactory
    ) -> None:
        self._fundamentals[name] = factory

    def register_price(self, name: str, factory: PriceFactory) -> None:
        self._price[name] = factory

    def make_fundamentals(
        self, name: str, cfg: ProvidersConfig
    ) -> FundamentalsProvider:
        try:
            factory = self._fundamentals[name]
        except KeyError as exc:
            available = sorted(self._fundamentals)
            raise KeyError(
                f"unknown fundamentals provider {name!r}; registered: {available}"
            ) from exc
        return factory(cfg)

    def make_price(self, name: str, cfg: ProvidersConfig) -> PriceProvider:
        try:
            factory = self._price[name]
        except KeyError as exc:
            available = sorted(self._price)
            raise KeyError(
                f"unknown price provider {name!r}; registered: {available}"
            ) from exc
        return factory(cfg)

    def fundamentals_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._fundamentals))

    def price_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._price))


def _build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_fundamentals("yfinance", lambda _cfg: YFinanceProvider())
    registry.register_fundamentals("screener_in", lambda _cfg: ScreenerInProvider())
    registry.register_price("yfinance", lambda _cfg: YFinanceProvider())
    return registry


default_registry: ProviderRegistry = _build_default_registry()


__all__ = ["ProviderRegistry", "default_registry"]
