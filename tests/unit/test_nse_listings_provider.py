"""Unit tests for ``NseListingsProvider``."""

from __future__ import annotations

import httpx
import respx

from stock_screener.core.errors import (
    DataQualityError,
    RateLimitError,
    UnavailableError,
)
from stock_screener.core.result import Err, Ok
from stock_screener.domain.value_objects.symbol import Exchange
from stock_screener.infra.providers.nse_listings_provider import NseListingsProvider

_URL = "https://test.nse.invalid/EQUITY_L.csv"

_CSV = (
    "SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT,  ISIN NUMBER, FACE VALUE\n"
    "RELIANCE, Reliance Industries Limited, EQ, 29-NOV-1995, 10, 1, INE002A01018, 10\n"
    "TCS, Tata Consultancy Services Limited, EQ, 25-AUG-2004, 1, 1, INE467B01029, 1\n"
    "INFY, Infosys Limited, EQ, 14-JUN-1995, 5, 1, INE009A01021, 5\n"
)


async def test_parses_csv_into_companies() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock() as router:
            router.get(_URL).mock(return_value=httpx.Response(200, text=_CSV))
            provider = NseListingsProvider(client=client, url=_URL)
            result = await provider.fetch_listings()

    assert result.is_ok()
    assert isinstance(result, Ok)
    companies = result.value
    assert len(companies) == 3

    codes = {c.symbol.code for c in companies}
    assert codes == {"RELIANCE", "TCS", "INFY"}

    reliance = next(c for c in companies if c.symbol.code == "RELIANCE")
    assert reliance.symbol.exchange is Exchange.NSE
    assert reliance.name == "Reliance Industries Limited"
    assert reliance.isin == "INE002A01018"
    assert reliance.listing_date == "1995-11-29"


async def test_404_is_data_quality() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock() as router:
            router.get(_URL).mock(return_value=httpx.Response(404))
            provider = NseListingsProvider(client=client, url=_URL)
            result = await provider.fetch_listings()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, DataQualityError)


async def test_429_is_rate_limit() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock() as router:
            router.get(_URL).mock(return_value=httpx.Response(429))
            provider = NseListingsProvider(client=client, url=_URL)
            result = await provider.fetch_listings()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, RateLimitError)


async def test_500_is_unavailable() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock() as router:
            router.get(_URL).mock(return_value=httpx.Response(502))
            provider = NseListingsProvider(client=client, url=_URL)
            result = await provider.fetch_listings()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, UnavailableError)


async def test_network_error_is_unavailable() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock() as router:
            router.get(_URL).mock(side_effect=httpx.ConnectError("dns"))
            provider = NseListingsProvider(client=client, url=_URL)
            result = await provider.fetch_listings()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, UnavailableError)


async def test_empty_response_is_data_quality() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock() as router:
            router.get(_URL).mock(return_value=httpx.Response(200, text="   \n"))
            provider = NseListingsProvider(client=client, url=_URL)
            result = await provider.fetch_listings()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, DataQualityError)


async def test_skips_blank_rows() -> None:
    csv_with_blanks = (
        "SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT,  ISIN NUMBER, FACE VALUE\n"
        "RELIANCE, Reliance, EQ, 29-NOV-1995, 10, 1, INE002A01018, 10\n"
        ",,,,,,,\n"
        "INFY, Infosys, EQ, 14-JUN-1995, 5, 1, INE009A01021, 5\n"
    )
    async with httpx.AsyncClient() as client:
        with respx.mock() as router:
            router.get(_URL).mock(
                return_value=httpx.Response(200, text=csv_with_blanks)
            )
            provider = NseListingsProvider(client=client, url=_URL)
            result = await provider.fetch_listings()

    assert result.is_ok()
    assert isinstance(result, Ok)
    assert len(result.value) == 2
