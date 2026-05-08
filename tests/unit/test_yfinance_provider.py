"""Unit tests for ``YFinanceProvider``."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from stock_screener.core.errors import DataQualityError, UnavailableError
from stock_screener.core.result import Err, Ok
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.providers.yfinance_provider import (
    YFinanceProvider,
    _lookback_to_period,
)


# --------------------------------------------------------------------------- #
# Fakes that mimic the tiny slice of yfinance we use
# --------------------------------------------------------------------------- #
class _FakeRecord:
    def __init__(self, payload: dict[str, float | int]) -> None:
        self._payload = payload

    def __getitem__(self, key: str) -> float | int:
        return self._payload[key]


class _FakeIndex:
    def __init__(self, on: date) -> None:
        self._on = on

    def to_pydatetime(self) -> Any:
        from datetime import datetime as _dt

        return _dt(self._on.year, self._on.month, self._on.day)


class _FakeDataFrame:
    def __init__(self, rows: list[tuple[date, dict[str, float | int]]]) -> None:
        self._rows = rows
        self.empty = len(rows) == 0

    def iterrows(self) -> Any:
        for on, payload in self._rows:
            yield _FakeIndex(on), _FakeRecord(payload)


class _FakeTicker:
    def __init__(
        self,
        info: dict[str, Any],
        history: _FakeDataFrame | None = None,
        history_exc: Exception | None = None,
    ) -> None:
        self.info = info
        self._history = history
        self._history_exc = history_exc

    def history(self, period: str) -> _FakeDataFrame:  # noqa: ARG002
        if self._history_exc is not None:
            raise self._history_exc
        return self._history or _FakeDataFrame([])


class _FakeYFinance:
    def __init__(self, ticker: _FakeTicker) -> None:
        self._ticker = ticker

    def Ticker(self, _yahoo: str) -> _FakeTicker:  # noqa: N802
        return self._ticker


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "days,expected",
    [
        (1, "1y"),
        (200, "1y"),
        (400, "2y"),
        (1000, "5y"),
        (4000, "max"),
    ],
)
def test_lookback_to_period(days: int, expected: str) -> None:
    assert _lookback_to_period(timedelta(days=days)) == expected


class TestFundamentalsHappy:
    async def test_maps_info_dict(self) -> None:
        info = {
            "totalRevenue": 1_000_000.0,
            "netIncomeToCommon": 200_000.0,
            "trailingEps": 12.5,
            "totalAssets": 5_000_000.0,
            "totalStockholderEquity": 2_000_000.0,
            "totalDebt": 1_500_000.0,
            "totalCash": 800_000.0,
            "sharesOutstanding": 50_000.0,
            "trailingPE": 18.4,
            "priceToBook": 2.5,
            "enterpriseToEbitda": 14.0,
            "dividendYield": 0.012,
            "returnOnEquity": 0.18,
            "debtToEquity": 0.75,
            "currentRatio": 1.6,
            "grossMargins": 0.3,
            "operatingMargins": 0.2,
            "profitMargins": 0.1,
            "payoutRatio": 0.25,
            "operatingCashflow": 300_000.0,
            "freeCashflow": 250_000.0,
        }
        fake = _FakeYFinance(_FakeTicker(info=info))
        provider = YFinanceProvider(yfinance=fake)

        result = await provider.get_fundamentals(
            Symbol(code="RELIANCE", exchange=Exchange.NSE)
        )

        assert result.is_ok()
        assert isinstance(result, Ok)
        f = result.value
        assert f.revenue == 1_000_000.0
        assert f.net_profit == 200_000.0
        assert f.eps == 12.5
        assert f.pe == 18.4
        assert f.pb == 2.5
        assert f.dividend_yield == pytest.approx(0.012)
        assert f.debt_to_equity == 0.75

    async def test_empty_info_is_data_quality(self) -> None:
        fake = _FakeYFinance(_FakeTicker(info={}))
        provider = YFinanceProvider(yfinance=fake)

        result = await provider.get_fundamentals(
            Symbol(code="X", exchange=Exchange.NSE)
        )

        assert result.is_err()
        assert isinstance(result, Err)
        assert isinstance(result.error, DataQualityError)


class TestFundamentalsFailures:
    async def test_network_error_is_unavailable(self) -> None:
        class _Boom:
            def Ticker(self, _: str) -> _FakeTicker:  # noqa: N802
                raise ConnectionError("dns failed")

        provider = YFinanceProvider(yfinance=_Boom())

        result = await provider.get_fundamentals(
            Symbol(code="X", exchange=Exchange.NSE)
        )

        assert result.is_err()
        assert isinstance(result, Err)
        assert isinstance(result.error, UnavailableError)


class TestPrices:
    async def test_maps_history_to_price_series(self) -> None:
        rows = [
            (
                date(2026, 4, 27),
                {"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0, "Volume": 1000},
            ),
            (
                date(2026, 4, 28),
                {"Open": 101.0, "High": 103.0, "Low": 100.5, "Close": 102.5, "Volume": 1100},
            ),
        ]
        df = _FakeDataFrame(rows)
        fake = _FakeYFinance(_FakeTicker(info={"x": 1}, history=df))

        provider = YFinanceProvider(yfinance=fake)
        result = await provider.get_prices(
            Symbol(code="X", exchange=Exchange.NSE), timedelta(days=30)
        )

        assert result.is_ok()
        assert isinstance(result, Ok)
        series = result.value
        assert len(series.points) == 2
        assert series.points[0].close == 101.0
        assert series.points[-1].close == 102.5

    async def test_empty_history_is_data_quality(self) -> None:
        fake = _FakeYFinance(_FakeTicker(info={"x": 1}, history=_FakeDataFrame([])))
        provider = YFinanceProvider(yfinance=fake)

        result = await provider.get_prices(
            Symbol(code="X", exchange=Exchange.NSE), timedelta(days=30)
        )

        assert result.is_err()
        assert isinstance(result, Err)
        assert isinstance(result.error, DataQualityError)

    async def test_history_skips_nan_rows(self) -> None:
        nan = float("nan")
        rows = [
            (
                date(2026, 4, 27),
                {"Open": nan, "High": nan, "Low": nan, "Close": nan, "Volume": 0},
            ),
            (
                date(2026, 4, 28),
                {"Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.5, "Volume": 100},
            ),
        ]
        fake = _FakeYFinance(_FakeTicker(info={"x": 1}, history=_FakeDataFrame(rows)))
        provider = YFinanceProvider(yfinance=fake)

        result = await provider.get_prices(
            Symbol(code="X", exchange=Exchange.NSE), timedelta(days=30)
        )

        assert result.is_ok()
        assert isinstance(result, Ok)
        assert len(result.value.points) == 1

    async def test_price_network_error(self) -> None:
        fake = _FakeYFinance(
            _FakeTicker(info={"x": 1}, history_exc=ConnectionError("net down"))
        )
        provider = YFinanceProvider(yfinance=fake)

        result = await provider.get_prices(
            Symbol(code="X", exchange=Exchange.NSE), timedelta(days=30)
        )

        assert result.is_err()
        assert isinstance(result, Err)
        assert isinstance(result.error, UnavailableError)
