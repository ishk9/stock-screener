"""CLI tests for ``ss analyse``."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stock_screener.cli.app import app
from stock_screener.core.di import Container
from stock_screener.core.errors import UnavailableError
from stock_screener.core.result import Err, Ok, Result
from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.ports.llm_client import LLMClient, LLMRequest
from stock_screener.domain.ports.market_data import (
    FundamentalsProvider,
    PriceProvider,
)
from stock_screener.domain.ports.universe_repo import UniverseRepository
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.llm.prompts.analyse import AnalysisOutput

from tests.conftest import FakeFundamentalsProvider, FakePriceProvider
from tests.e2e.test_screen_pipeline import InMemoryUniverse


def _full_fundamentals() -> Fundamentals:
    return Fundamentals(
        as_of=date(2026, 5, 1),
        revenue=10_000,
        net_profit=1_500,
        eps=10.0,
        pe=15.0,
        pb=2.5,
        roe=0.18,
        roce=0.20,
        debt_to_equity=0.4,
        revenue_cagr_3y=0.12,
        eps_cagr_3y=0.15,
        operating_margin=0.18,
        net_margin=0.15,
        free_cash_flow=1_200,
    )


def _flat_prices() -> PriceSeries:
    points = [
        PricePoint(
            on=date(2025, 1, 1) + timedelta(days=i),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1_000_000,
        )
        for i in range(260)
    ]
    return PriceSeries.from_points(points)


class _StubLLMClient:
    name = "stub"
    model = "stub-1"

    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []

    async def analyse(
        self, request: LLMRequest, schema: type
    ) -> Result[AnalysisOutput, object]:
        self.calls.append(request)
        return Ok(
            AnalysisOutput(
                thesis_summary="Stable analysis from stub.",
                key_risks=("regulatory",),
                catalysts=("margin expansion",),
                qualitative_risk=0.4,
                confidence=0.7,
                suggested_horizon="long",
            )
        )


def _build_container(
    *,
    universe: UniverseRepository,
    fundamentals: FundamentalsProvider,
    prices: PriceProvider,
    llm: LLMClient | None,
) -> Container:
    container = Container()
    container.register_instance(UniverseRepository, universe)
    container.register_instance(FundamentalsProvider, fundamentals)
    container.register_instance(PriceProvider, prices)
    if llm is not None:
        container.register_instance(LLMClient, llm)
    return container


def _patch(monkeypatch: pytest.MonkeyPatch, container: Container) -> None:
    monkeypatch.setattr(
        "stock_screener.cli.commands.analyse.make_default_container",
        lambda _config: container,
    )


@pytest.fixture
def runner(silence_logging: None) -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)  # type: ignore[call-arg]
    except TypeError:
        return CliRunner()


def test_analyse_help_renders(runner: CliRunner) -> None:
    result = runner.invoke(app, ["analyse", "--help"])
    assert result.exit_code == 0
    assert "ticker" in result.stdout.lower() or "TICKER" in result.stdout


def test_analyse_invalid_ticker_returns_2(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _build_container(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([]),
        prices=FakePriceProvider([]),
        llm=None,
    )
    _patch(monkeypatch, container)
    result = runner.invoke(
        app, ["analyse", "   "], env={"SS_LLM_API_KEY": "test"}
    )
    assert result.exit_code == 2


def test_analyse_happy_path_with_stub_llm(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    company = Company(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        name="Reliance Industries",
        sector="Energy",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    container = _build_container(
        universe=InMemoryUniverse([company]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=_StubLLMClient(),
    )
    _patch(monkeypatch, container)
    result = runner.invoke(
        app, ["analyse", "RELIANCE"], env={"SS_LLM_API_KEY": "test"}
    )
    assert result.exit_code == 0, result.stderr
    assert "RELIANCE" in result.stdout


def test_analyse_no_llm_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    company = Company(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        name="Reliance Industries",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    container = _build_container(
        universe=InMemoryUniverse([company]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=None,
    )
    _patch(monkeypatch, container)
    result = runner.invoke(
        app, ["analyse", "RELIANCE", "--no-llm"], env={"SS_LLM_API_KEY": "test"}
    )
    assert result.exit_code == 0, result.stderr
    assert "RELIANCE" in result.stdout


def test_analyse_format_json_valid(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    company = Company(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        name="Reliance Industries",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    container = _build_container(
        universe=InMemoryUniverse([company]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=None,
    )
    _patch(monkeypatch, container)
    result = runner.invoke(
        app,
        ["analyse", "RELIANCE", "--no-llm", "--format", "json"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert payload["symbol"]["code"] == "RELIANCE"


def test_analyse_provider_failures_do_not_crash(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _build_container(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([Err(UnavailableError("down"))]),
        prices=FakePriceProvider([Err(UnavailableError("down"))]),
        llm=None,
    )
    _patch(monkeypatch, container)
    result = runner.invoke(
        app, ["analyse", "TCS", "--no-llm"], env={"SS_LLM_API_KEY": "test"}
    )
    assert result.exit_code == 0, result.stderr
    assert "TCS" in result.stdout
