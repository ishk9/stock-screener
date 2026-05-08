"""Unit tests for ``ProviderRegistry``."""

from __future__ import annotations

import pytest

from stock_screener.core.config import ProvidersConfig
from stock_screener.infra.providers.registry import (
    ProviderRegistry,
    default_registry,
)
from stock_screener.infra.providers.screener_in_provider import ScreenerInProvider
from stock_screener.infra.providers.yfinance_provider import YFinanceProvider


def test_default_registry_has_pre_registered_names() -> None:
    cfg = ProvidersConfig()

    yf = default_registry.make_fundamentals("yfinance", cfg)
    si = default_registry.make_fundamentals("screener_in", cfg)
    yf_price = default_registry.make_price("yfinance", cfg)

    assert isinstance(yf, YFinanceProvider)
    assert isinstance(si, ScreenerInProvider)
    assert isinstance(yf_price, YFinanceProvider)
    assert "yfinance" in default_registry.fundamentals_names()
    assert "screener_in" in default_registry.fundamentals_names()
    assert "yfinance" in default_registry.price_names()


def test_unknown_fundamentals_raises() -> None:
    cfg = ProvidersConfig()
    with pytest.raises(KeyError):
        default_registry.make_fundamentals("does-not-exist", cfg)


def test_unknown_price_raises() -> None:
    cfg = ProvidersConfig()
    with pytest.raises(KeyError):
        default_registry.make_price("does-not-exist", cfg)


def test_register_and_retrieve_custom_factory() -> None:
    registry = ProviderRegistry()
    cfg = ProvidersConfig()

    sentinel = YFinanceProvider()
    registry.register_fundamentals("custom", lambda _cfg: sentinel)

    out = registry.make_fundamentals("custom", cfg)
    assert out is sentinel


def test_register_custom_price_factory() -> None:
    registry = ProviderRegistry()
    cfg = ProvidersConfig()
    sentinel = YFinanceProvider()
    registry.register_price("custom_px", lambda _cfg: sentinel)

    out = registry.make_price("custom_px", cfg)
    assert out is sentinel


async def test_screener_in_default_provider_is_closed_cleanly() -> None:
    cfg = ProvidersConfig()
    si = default_registry.make_fundamentals("screener_in", cfg)
    assert isinstance(si, ScreenerInProvider)
    await si.close()
