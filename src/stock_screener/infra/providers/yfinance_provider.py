"""yfinance-backed adapter for ``FundamentalsProvider`` and ``PriceProvider``.

``yfinance`` performs blocking HTTP I/O, so all of its calls are off-loaded to
a worker thread via :func:`asyncio.to_thread`. The vendor module itself is
injected through the constructor to keep the adapter unit-testable.

Yahoo Finance returns INR amounts natively for ``.NS``/``.BO`` listings, so we
do **not** apply any FX conversion here.
"""

from __future__ import annotations

import asyncio
import math
from datetime import date, datetime, timedelta
from typing import Any

import structlog

from ...core.errors import DataQualityError, ProviderError, UnavailableError
from ...core.result import Err, Ok, Result
from ...domain.entities.fundamentals import Fundamentals
from ...domain.entities.price_series import PricePoint, PriceSeries
from ...domain.value_objects.symbol import Symbol

log = structlog.get_logger(__name__)


def _lookback_to_period(lookback: timedelta) -> str:
    """Map a ``timedelta`` to the smallest yfinance period covering it."""
    days = max(1, int(lookback.total_seconds() // 86_400))
    if days <= 365:
        return "1y"
    if days <= 730:
        return "2y"
    if days <= 1_825:
        return "5y"
    return "max"


def _coerce_float(value: object) -> float | None:
    """Best-effort conversion to a finite ``float``, else ``None``."""
    if value is None:
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _non_negative(value: float | None) -> float | None:
    if value is None or value < 0:
        return None
    return value


class YFinanceProvider:
    """Adapter wrapping the public ``yfinance`` package."""

    name: str = "yfinance"

    def __init__(self, yfinance: Any | None = None) -> None:
        self._yf = yfinance

    def _module(self) -> Any:
        if self._yf is not None:
            return self._yf
        import yfinance as _yf

        self._yf = _yf
        return _yf

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        try:
            info = await asyncio.to_thread(self._fetch_info, symbol)
        except ProviderError as exc:
            return Err(exc)
        except Exception as exc:  # noqa: BLE001
            return Err(UnavailableError(f"yfinance fundamentals network error: {exc}"))

        if not info:
            return Err(DataQualityError(f"empty info for {symbol.yahoo()}"))

        try:
            fundamentals = Fundamentals(
                as_of=date.today(),
                revenue=_non_negative(_coerce_float(info.get("totalRevenue"))),
                operating_profit=_coerce_float(info.get("operatingIncome")),
                net_profit=_coerce_float(
                    info.get("netIncomeToCommon") or info.get("netIncome")
                ),
                eps=_coerce_float(info.get("trailingEps")),
                total_assets=_non_negative(_coerce_float(info.get("totalAssets"))),
                total_equity=_coerce_float(info.get("totalStockholderEquity")),
                total_debt=_non_negative(_coerce_float(info.get("totalDebt"))),
                cash=_non_negative(_coerce_float(info.get("totalCash"))),
                shares_outstanding=_non_negative(
                    _coerce_float(info.get("sharesOutstanding"))
                ),
                operating_cash_flow=_coerce_float(info.get("operatingCashflow")),
                free_cash_flow=_coerce_float(info.get("freeCashflow")),
                pe=_coerce_float(info.get("trailingPE")),
                pb=_coerce_float(info.get("priceToBook")),
                ev_ebitda=_coerce_float(info.get("enterpriseToEbitda")),
                roe=_coerce_float(info.get("returnOnEquity")),
                debt_to_equity=_non_negative(
                    _coerce_float(info.get("debtToEquity"))
                ),
                current_ratio=_non_negative(_coerce_float(info.get("currentRatio"))),
                gross_margin=_coerce_float(info.get("grossMargins")),
                operating_margin=_coerce_float(info.get("operatingMargins")),
                net_margin=_coerce_float(info.get("profitMargins")),
                dividend_yield=_non_negative(
                    _coerce_float(info.get("dividendYield"))
                ),
                payout_ratio=_coerce_float(info.get("payoutRatio")),
            )
        except Exception as exc:  # noqa: BLE001 — pydantic ValidationError, etc.
            return Err(DataQualityError(f"failed to assemble Fundamentals: {exc}"))

        return Ok(fundamentals)

    def _fetch_info(self, symbol: Symbol) -> dict[str, Any]:
        ticker = self._module().Ticker(symbol.yahoo())
        info = getattr(ticker, "info", None) or {}
        if not isinstance(info, dict):
            return {}
        return info

    async def get_prices(
        self, symbol: Symbol, lookback: timedelta
    ) -> Result[PriceSeries, ProviderError]:
        period = _lookback_to_period(lookback)
        try:
            rows = await asyncio.to_thread(self._fetch_history, symbol, period)
        except ProviderError as exc:
            return Err(exc)
        except Exception as exc:  # noqa: BLE001
            return Err(UnavailableError(f"yfinance history network error: {exc}"))

        if not rows:
            return Err(
                DataQualityError(f"empty price history for {symbol.yahoo()}")
            )

        points: list[PricePoint] = []
        for row in rows:
            try:
                points.append(PricePoint(**row))
            except Exception:  # noqa: BLE001 — drop NaN/invalid rows
                continue

        if not points:
            return Err(
                DataQualityError(f"no valid price points for {symbol.yahoo()}")
            )

        return Ok(PriceSeries.from_points(points))

    def _fetch_history(self, symbol: Symbol, period: str) -> list[dict[str, Any]]:
        ticker = self._module().Ticker(symbol.yahoo())
        df = ticker.history(period=period)
        if df is None:
            return []
        if hasattr(df, "empty") and df.empty:
            return []

        rows: list[dict[str, Any]] = []
        for index, record in df.iterrows():
            on = self._row_date(index)
            if on is None:
                continue
            try:
                row = {
                    "on": on,
                    "open": float(record["Open"]),
                    "high": float(record["High"]),
                    "low": float(record["Low"]),
                    "close": float(record["Close"]),
                    "volume": int(record["Volume"]),
                }
            except (KeyError, TypeError, ValueError):
                continue
            if any(
                math.isnan(v) for v in (row["open"], row["high"], row["low"], row["close"])
            ):
                continue
            rows.append(row)
        return rows

    @staticmethod
    def _row_date(index: object) -> date | None:
        if isinstance(index, date) and not isinstance(index, datetime):
            return index
        if isinstance(index, datetime):
            return index.date()
        to_pydatetime = getattr(index, "to_pydatetime", None)
        if callable(to_pydatetime):
            try:
                return to_pydatetime().date()
            except Exception:  # noqa: BLE001
                return None
        return None


__all__ = ["YFinanceProvider"]
