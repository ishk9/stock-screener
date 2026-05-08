"""Adapter that scrapes the public ``screener.in`` company page.

Used as a fallback ``FundamentalsProvider`` when the primary source (yfinance)
is rate-limited or returns sparse data. Parsing is intentionally lenient — any
missing field becomes ``None`` rather than failing the call. Only a structural
breakage of the page (no ratios container at all) is treated as a
``DataQualityError``.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Final

import httpx
import structlog
from bs4 import BeautifulSoup

from ...core.errors import (
    DataQualityError,
    ProviderError,
    RateLimitError,
    UnavailableError,
)
from ...core.result import Err, Ok, Result
from ...domain.entities.fundamentals import Fundamentals
from ...domain.value_objects.symbol import Symbol

log = structlog.get_logger(__name__)

_BASE_URL: Final = "https://www.screener.in/company"
_USER_AGENT: Final = (
    "stock-screener/0.1 (+https://github.com/stock-screener) "
    "research-bot; contact via repo"
)
_NUMBER_RE: Final = re.compile(r"-?[\d,]+(?:\.\d+)?")


class ScreenerInProvider:
    """Scrapes screener.in company pages for headline fundamentals."""

    name: str = "screener_in"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        base_url: str = _BASE_URL,
        timeout_s: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
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

    async def get_fundamentals(
        self, symbol: Symbol
    ) -> Result[Fundamentals, ProviderError]:
        url = f"{self._base_url}/{symbol.code}/"
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            return Err(UnavailableError(f"screener.in network error: {exc}"))

        status = response.status_code
        if status == 404:
            return Err(DataQualityError(f"not found: {symbol.code}"))
        if status == 429:
            return Err(RateLimitError("screener.in rate-limited"))
        if status >= 500:
            return Err(UnavailableError(f"screener.in {status}"))
        if status >= 400:
            return Err(UnavailableError(f"screener.in client error {status}"))

        try:
            ratios = self._parse(response.text)
        except DataQualityError as exc:
            return Err(exc)

        if not ratios:
            return Err(DataQualityError("no ratios extracted"))

        try:
            fundamentals = Fundamentals(
                as_of=date.today(),
                pe=ratios.get("pe"),
                pb=ratios.get("pb"),
                roe=ratios.get("roe"),
                roce=ratios.get("roce"),
                debt_to_equity=ratios.get("debt_to_equity"),
                dividend_yield=ratios.get("dividend_yield"),
            )
        except Exception as exc:  # noqa: BLE001
            return Err(DataQualityError(f"invalid fundamentals payload: {exc}"))

        return Ok(fundamentals)

    @staticmethod
    def _parse(html: str) -> dict[str, float | None]:
        """Extract a small subset of common ratios from a screener.in page."""
        soup = BeautifulSoup(html, "lxml")

        container = soup.find(id="top-ratios") or soup.find(class_="company-ratios")
        if container is None:
            container = soup.find("ul", class_="ratios")
        if container is None:
            raise DataQualityError("ratios container missing from page")

        pairs: dict[str, float | None] = {}
        for item in container.find_all("li"):
            name_el = item.find(class_="name")
            value_el = item.find(class_="number") or item.find(class_="value")
            if name_el is None or value_el is None:
                continue
            label = name_el.get_text(strip=True).lower()
            raw = value_el.get_text(" ", strip=True)
            value = _parse_number(raw)

            if "p/e" in label or label == "pe":
                pairs["pe"] = value
            elif "p/b" in label or label == "price to book":
                pairs["pb"] = value
            elif "roce" in label:
                pairs["roce"] = value
            elif "roe" in label:
                pairs["roe"] = value
            elif "debt" in label and "equity" in label:
                pairs["debt_to_equity"] = _non_negative(value)
            elif "dividend" in label and "yield" in label:
                pairs["dividend_yield"] = _non_negative(value)
            elif "market cap" in label:
                pairs["market_cap"] = value

        return pairs


def _parse_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text.replace("\xa0", " "))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _non_negative(value: float | None) -> float | None:
    if value is None or value < 0:
        return None
    return value


__all__ = ["ScreenerInProvider"]
