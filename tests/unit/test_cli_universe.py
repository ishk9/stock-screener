"""CLI tests for ``ss universe``."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stock_screener.cli.app import app
from stock_screener.core.di import Container
from stock_screener.core.errors import ProviderError
from stock_screener.core.result import Ok, Result
from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.ports.market_data import FundamentalsProvider
from stock_screener.domain.ports.universe_repo import UniverseRepository
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.providers.nse_listings_provider import NseListingsProvider

from tests.conftest import FakeFundamentalsProvider
from tests.e2e.test_screen_pipeline import InMemoryUniverse


class _StubListingsProvider:
    name = "nse_listings_stub"

    def __init__(self, companies: list[Company]) -> None:
        self._companies = companies
        self.calls = 0

    async def fetch_listings(self) -> Result[list[Company], ProviderError]:
        self.calls += 1
        return Ok(list(self._companies))


def _make_companies(n: int = 3) -> list[Company]:
    return [
        Company(
            symbol=Symbol(code=f"COMP{i}", exchange=Exchange.NSE),
            name=f"Company {i}",
        )
        for i in range(n)
    ]


def _strong_fundamentals() -> Fundamentals:
    return Fundamentals(
        as_of=date(2026, 5, 1),
        eps=10.0,
        pe=15.0,
        shares_outstanding=1_000_000.0,
    )


def _build_container(
    *,
    universe: UniverseRepository,
    listings: NseListingsProvider,
    fundamentals: FundamentalsProvider,
) -> Container:
    container = Container()
    container.register_instance(UniverseRepository, universe)
    container.register_instance(NseListingsProvider, listings)  # type: ignore[type-abstract]
    container.register_instance(FundamentalsProvider, fundamentals)
    return container


def _patch(monkeypatch: pytest.MonkeyPatch, container: Container) -> None:
    monkeypatch.setattr(
        "stock_screener.cli.commands.universe.make_default_container",
        lambda _config: container,
    )


@pytest.fixture
def runner(silence_logging: None) -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)  # type: ignore[call-arg]
    except TypeError:
        return CliRunner()


def test_universe_show_empty(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _build_container(
        universe=InMemoryUniverse([]),
        listings=_StubListingsProvider([]),  # type: ignore[arg-type]
        fundamentals=FakeFundamentalsProvider([]),
    )
    _patch(monkeypatch, container)

    res = runner.invoke(app, ["universe", "show"], env={"SS_LLM_API_KEY": "test"})
    assert res.exit_code == 0, res.stderr
    assert "Total: 0" in res.stdout


def test_universe_show_filtered_by_bucket(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    large = Company(
        symbol=Symbol(code="LRG", exchange=Exchange.NSE),
        name="Large Co",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    small = Company(
        symbol=Symbol(code="SML", exchange=Exchange.NSE),
        name="Small Co",
        market_cap_bucket=MarketCapBucket.SMALL,
    )
    container = _build_container(
        universe=InMemoryUniverse([large, small]),
        listings=_StubListingsProvider([]),  # type: ignore[arg-type]
        fundamentals=FakeFundamentalsProvider([]),
    )
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["universe", "show", "--cap", "lg", "--limit", "5"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 0, res.stderr
    assert "LRG" in res.stdout
    assert "SML" not in res.stdout


def test_universe_refresh_no_enrich(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(5)
    listings = _StubListingsProvider(companies)
    universe = InMemoryUniverse([])
    container = _build_container(
        universe=universe,
        listings=listings,  # type: ignore[arg-type]
        fundamentals=FakeFundamentalsProvider([]),
    )
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["universe", "refresh", "--no-enrich", "--limit", "3"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 0, res.stderr
    assert "Refreshed: 3 companies persisted." in res.stdout
    assert universe.count() == 3


def test_universe_refresh_with_enrichment_calls_fundamentals(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(2)
    listings = _StubListingsProvider(companies)
    fundamentals = FakeFundamentalsProvider(
        [Ok(_strong_fundamentals()), Ok(_strong_fundamentals())]
    )
    universe = InMemoryUniverse([])
    container = _build_container(
        universe=universe,
        listings=listings,  # type: ignore[arg-type]
        fundamentals=fundamentals,
    )
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["universe", "refresh", "--limit", "2"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 0, res.stderr
    assert len(fundamentals.calls) == 2
    assert universe.count() == 2
