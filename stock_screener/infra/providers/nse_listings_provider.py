"""Adapter that fetches the NSE equity master CSV.

Returns minimal :class:`Company` objects (symbol, name, ISIN, listing date).
Market-cap fields are filled later by a ranking pipeline that consumes another
data source — keeping this adapter narrow.
"""

from __future__ import annotations

import csv
import io
from typing import Final

import httpx
import structlog

from ...core.errors import (
    DataQualityError,
    ProviderError,
    RateLimitError,
    UnavailableError,
)
from ...core.result import Err, Ok, Result
from ...domain.entities.company import Company
from ...domain.value_objects.symbol import Exchange, Symbol

log = structlog.get_logger(__name__)

_LISTINGS_URL: Final = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
_USER_AGENT: Final = (
    "stock-screener/0.1 (+https://github.com/stock-screener) "
    "research-bot; contact via repo"
)


def _iso_listing_date(raw: str) -> str | None:
    """Parse the NSE ``DD-MMM-YYYY`` listing date into ISO ``YYYY-MM-DD``."""
    raw = raw.strip()
    if not raw:
        return None
    from datetime import datetime

    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class NseListingsProvider:
    """Downloads and parses the canonical NSE equity master CSV."""

    name: str = "nse_listings"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        url: str = _LISTINGS_URL,
        timeout_s: float = 15.0,
    ) -> None:
        self._url = url
        self._timeout_s = timeout_s
        if client is None:
            self._client = httpx.AsyncClient(
                timeout=timeout_s,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_listings(self) -> Result[list[Company], ProviderError]:
        try:
            response = await self._client.get(self._url)
        except httpx.HTTPError as exc:
            return Err(UnavailableError(f"NSE listings network error: {exc}"))

        status = response.status_code
        if status == 404:
            return Err(DataQualityError("NSE listings endpoint missing (404)"))
        if status == 429:
            return Err(RateLimitError("NSE listings rate-limited"))
        if status >= 500:
            return Err(UnavailableError(f"NSE listings {status}"))
        if status >= 400:
            return Err(UnavailableError(f"NSE listings client error {status}"))

        text = response.text
        if not text.strip():
            return Err(DataQualityError("empty NSE listings response"))

        try:
            companies = list(self._parse(text))
        except DataQualityError as exc:
            return Err(exc)

        if not companies:
            return Err(DataQualityError("NSE listings parsed but empty"))

        return Ok(companies)

    @staticmethod
    def _parse(text: str) -> list[Company]:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise DataQualityError("NSE listings has no header row")

        normalized: dict[str, str] = {
            (name or "").strip().upper(): (name or "") for name in reader.fieldnames
        }
        sym_col = normalized.get("SYMBOL")
        name_col = normalized.get("NAME OF COMPANY") or normalized.get("COMPANY NAME")
        if sym_col is None or name_col is None:
            raise DataQualityError(
                f"NSE listings missing expected columns; got {reader.fieldnames!r}"
            )
        isin_col = normalized.get("ISIN NUMBER") or normalized.get("ISIN")
        listing_col = normalized.get("DATE OF LISTING")

        companies: list[Company] = []
        for row in reader:
            code = (row.get(sym_col) or "").strip()
            name = (row.get(name_col) or "").strip()
            if not code or not name:
                continue
            try:
                symbol = Symbol(code=code, exchange=Exchange.NSE)
            except ValueError:
                continue
            isin = (row.get(isin_col) or "").strip() if isin_col else ""
            listing_iso = (
                _iso_listing_date(row.get(listing_col, "")) if listing_col else None
            )
            companies.append(
                Company(
                    symbol=symbol,
                    name=name,
                    isin=isin or None,
                    listing_date=listing_iso,
                )
            )
        return companies


__all__ = ["NseListingsProvider"]
