"""Unit tests for ``RefreshUniverseUseCase``."""

from __future__ import annotations

from datetime import date

import pytest

from stock_screener.core.errors import ProviderError, UnavailableError
from stock_screener.core.events import EventBus, UniverseRefreshed
from stock_screener.core.result import Err, Ok, Result
from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.usecases.refresh_universe import (
    RefreshRequest,
    RefreshUniverseUseCase,
)

from tests.conftest import FakeFundamentalsProvider


class _MemUniverseRepo:
    def __init__(self) -> None:
        self.upserted: list[Company] = []

    def upsert_many(self, companies: list[Company]) -> None:
        self.upserted = list(companies)

    def list(self, bucket: MarketCapBucket | None = None) -> list[Company]:
        if bucket is None:
            return list(self.upserted)
        return [c for c in self.upserted if c.market_cap_bucket == bucket]

    def get(self, code: str) -> Company | None:
        return next((c for c in self.upserted if c.symbol.code == code), None)

    def count(self) -> int:
        return len(self.upserted)

    def last_refreshed_at(self) -> str | None:
        return None


class _StubListings:
    name = "stub_listings"

    def __init__(self, payload: Result[list[Company], ProviderError]) -> None:
        self._payload = payload
        self.calls = 0

    async def fetch_listings(self) -> Result[list[Company], ProviderError]:
        self.calls += 1
        return self._payload


def _company(code: str, *, sector: str | None = None) -> Company:
    return Company(
        symbol=Symbol(code=code, exchange=Exchange.NSE),
        name=f"{code} Co",
        sector=sector,
    )


def _fundamentals_with_cap(eps: float, pe: float, shares: float) -> Fundamentals:
    return Fundamentals(
        as_of=date(2026, 5, 1),
        eps=eps,
        pe=pe,
        shares_outstanding=shares,
    )


@pytest.mark.asyncio
async def test_calls_listings_and_fundamentals_when_enriched() -> None:
    companies = [
        _company("A", sector="IT"),
        _company("B", sector="Banks"),
        _company("C", sector="Pharma"),
    ]
    listings = _StubListings(Ok(companies))
    fundamentals = FakeFundamentalsProvider(
        [
            Ok(_fundamentals_with_cap(eps=10, pe=10, shares=1_000_000)),
            Ok(_fundamentals_with_cap(eps=5, pe=20, shares=500_000)),
            Ok(_fundamentals_with_cap(eps=2, pe=30, shares=200_000)),
        ]
    )
    repo = _MemUniverseRepo()
    bus = EventBus()
    received: list[object] = []
    bus.subscribe_all(received.append)

    use_case = RefreshUniverseUseCase(
        listings=listings,  # type: ignore[arg-type]
        fundamentals=fundamentals,
        repo=repo,
        events=bus,
    )
    response = await use_case.execute(
        RefreshRequest(enrich_market_cap=True, max_concurrency=2)
    )

    assert listings.calls == 1
    assert len(fundamentals.calls) == 3
    assert response.count == 3
    assert len(repo.upserted) == 3
    for c in repo.upserted:
        assert c.market_cap_bucket is not None


@pytest.mark.asyncio
async def test_no_enrichment_does_not_call_fundamentals() -> None:
    companies = [_company("A"), _company("B")]
    listings = _StubListings(Ok(companies))
    fundamentals = FakeFundamentalsProvider([])
    repo = _MemUniverseRepo()

    use_case = RefreshUniverseUseCase(
        listings=listings,  # type: ignore[arg-type]
        fundamentals=fundamentals,
        repo=repo,
    )
    response = await use_case.execute(
        RefreshRequest(enrich_market_cap=False)
    )
    assert response.count == 2
    assert fundamentals.calls == []


@pytest.mark.asyncio
async def test_limit_truncates_to_first_n() -> None:
    companies = [_company(f"C{i}") for i in range(5)]
    listings = _StubListings(Ok(companies))
    fundamentals = FakeFundamentalsProvider([])
    repo = _MemUniverseRepo()

    use_case = RefreshUniverseUseCase(
        listings=listings,  # type: ignore[arg-type]
        fundamentals=fundamentals,
        repo=repo,
    )
    response = await use_case.execute(
        RefreshRequest(enrich_market_cap=False, limit=2)
    )
    assert response.count == 2
    codes = [c.symbol.code for c in repo.upserted]
    assert codes == ["C0", "C1"]


@pytest.mark.asyncio
async def test_companies_without_computable_mcap_default_to_small() -> None:
    companies = [_company("X")]
    listings = _StubListings(Ok(companies))
    fundamentals = FakeFundamentalsProvider(
        [Ok(Fundamentals(as_of=date(2026, 5, 1)))]
    )
    repo = _MemUniverseRepo()

    use_case = RefreshUniverseUseCase(
        listings=listings,  # type: ignore[arg-type]
        fundamentals=fundamentals,
        repo=repo,
    )
    await use_case.execute(RefreshRequest(enrich_market_cap=True))
    assert repo.upserted[0].market_cap_bucket == MarketCapBucket.SMALL


@pytest.mark.asyncio
async def test_listings_error_raises_wrapped_error() -> None:
    listings = _StubListings(Err(UnavailableError("network is down")))
    use_case = RefreshUniverseUseCase(
        listings=listings,  # type: ignore[arg-type]
        fundamentals=FakeFundamentalsProvider([]),
        repo=_MemUniverseRepo(),
    )
    with pytest.raises(UnavailableError):
        await use_case.execute(RefreshRequest(enrich_market_cap=False))


@pytest.mark.asyncio
async def test_event_bus_receives_universe_refreshed() -> None:
    companies = [_company("A"), _company("B")]
    listings = _StubListings(Ok(companies))
    bus = EventBus()
    events: list[object] = []
    bus.subscribe(UniverseRefreshed, events.append)

    use_case = RefreshUniverseUseCase(
        listings=listings,  # type: ignore[arg-type]
        fundamentals=FakeFundamentalsProvider([]),
        repo=_MemUniverseRepo(),
        events=bus,
    )
    await use_case.execute(RefreshRequest(enrich_market_cap=False))

    assert len(events) == 1
    evt = events[0]
    assert isinstance(evt, UniverseRefreshed)
    assert evt.count == 2
