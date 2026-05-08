"""Unit tests for ``ScreenerInProvider``."""

from __future__ import annotations

import httpx
import pytest
import respx

from stock_screener.core.errors import (
    DataQualityError,
    RateLimitError,
    UnavailableError,
)
from stock_screener.core.result import Err, Ok
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.providers.screener_in_provider import ScreenerInProvider

_BASE = "https://test.screener.invalid/company"

_HTML_OK = """
<html><body>
  <ul id="top-ratios">
    <li><span class="name">Stock P/E</span><span class="number">25.3</span></li>
    <li><span class="name">Price to Book</span><span class="number">3.10</span></li>
    <li><span class="name">ROCE</span><span class="number">22.4 %</span></li>
    <li><span class="name">ROE</span><span class="number">18.5 %</span></li>
    <li><span class="name">Debt to equity</span><span class="number">0.42</span></li>
    <li><span class="name">Dividend Yield</span><span class="number">1.20 %</span></li>
    <li><span class="name">Market Cap</span><span class="number">15,42,000</span></li>
  </ul>
</body></html>
"""

_HTML_BROKEN = "<html><body><h1>oops</h1></body></html>"


@pytest.fixture
def symbol() -> Symbol:
    return Symbol(code="ABC", exchange=Exchange.NSE)


async def test_parses_canned_html(symbol: Symbol) -> None:
    async with httpx.AsyncClient(base_url="https://test.screener.invalid") as client:
        with respx.mock(assert_all_called=True) as router:
            router.get(f"{_BASE}/{symbol.code}/").mock(
                return_value=httpx.Response(200, text=_HTML_OK)
            )

            provider = ScreenerInProvider(client=client, base_url=_BASE)
            result = await provider.get_fundamentals(symbol)

    assert result.is_ok()
    assert isinstance(result, Ok)
    f = result.value
    assert f.pe == pytest.approx(25.3)
    assert f.pb == pytest.approx(3.10)
    assert f.roce == pytest.approx(22.4)
    assert f.roe == pytest.approx(18.5)
    assert f.debt_to_equity == pytest.approx(0.42)
    assert f.dividend_yield == pytest.approx(1.20)


async def test_404_is_data_quality(symbol: Symbol) -> None:
    async with httpx.AsyncClient(base_url="https://test.screener.invalid") as client:
        with respx.mock() as router:
            router.get(f"{_BASE}/{symbol.code}/").mock(
                return_value=httpx.Response(404)
            )
            provider = ScreenerInProvider(client=client, base_url=_BASE)
            result = await provider.get_fundamentals(symbol)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, DataQualityError)


async def test_429_is_rate_limit(symbol: Symbol) -> None:
    async with httpx.AsyncClient(base_url="https://test.screener.invalid") as client:
        with respx.mock() as router:
            router.get(f"{_BASE}/{symbol.code}/").mock(
                return_value=httpx.Response(429)
            )
            provider = ScreenerInProvider(client=client, base_url=_BASE)
            result = await provider.get_fundamentals(symbol)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, RateLimitError)


async def test_500_is_unavailable(symbol: Symbol) -> None:
    async with httpx.AsyncClient(base_url="https://test.screener.invalid") as client:
        with respx.mock() as router:
            router.get(f"{_BASE}/{symbol.code}/").mock(
                return_value=httpx.Response(503, text="bad gateway")
            )
            provider = ScreenerInProvider(client=client, base_url=_BASE)
            result = await provider.get_fundamentals(symbol)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, UnavailableError)


async def test_network_error_is_unavailable(symbol: Symbol) -> None:
    async with httpx.AsyncClient(base_url="https://test.screener.invalid") as client:
        with respx.mock() as router:
            router.get(f"{_BASE}/{symbol.code}/").mock(
                side_effect=httpx.ConnectError("dns failure")
            )
            provider = ScreenerInProvider(client=client, base_url=_BASE)
            result = await provider.get_fundamentals(symbol)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, UnavailableError)


async def test_broken_html_is_data_quality(symbol: Symbol) -> None:
    async with httpx.AsyncClient(base_url="https://test.screener.invalid") as client:
        with respx.mock() as router:
            router.get(f"{_BASE}/{symbol.code}/").mock(
                return_value=httpx.Response(200, text=_HTML_BROKEN)
            )
            provider = ScreenerInProvider(client=client, base_url=_BASE)
            result = await provider.get_fundamentals(symbol)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, DataQualityError)


async def test_close_is_noop_when_client_injected() -> None:
    async with httpx.AsyncClient() as client:
        provider = ScreenerInProvider(client=client, base_url=_BASE)
        await provider.close()
        assert not client.is_closed


async def test_default_client_is_owned_and_closeable() -> None:
    provider = ScreenerInProvider(base_url=_BASE)
    await provider.close()
