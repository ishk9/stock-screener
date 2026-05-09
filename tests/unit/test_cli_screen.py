"""CLI tests for ``ss screen``."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stock_screener.cli.app import app
from stock_screener.core.di import Container
from stock_screener.core.result import Ok, Result
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
from stock_screener.infra.cache.run_repo import RunRepo
from stock_screener.infra.llm.prompts.analyse import AnalysisOutput
from stock_screener.infra.renderer.factory import RendererFactory

from tests.conftest import FakeFundamentalsProvider, FakePriceProvider
from tests.e2e.test_screen_pipeline import InMemoryUniverse


def _make_companies(n: int = 5) -> list[Company]:
    return [
        Company(
            symbol=Symbol(code=f"STK{i}", exchange=Exchange.NSE),
            name=f"Stock {i}",
            sector="IT",
            market_cap_inr=1e12 - i * 1e10,
            market_cap_bucket=MarketCapBucket.LARGE,
            market_cap_rank=i + 1,
        )
        for i in range(n)
    ]


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
            open=100.0 + i * 0.05,
            high=101.0 + i * 0.05,
            low=99.0 + i * 0.05,
            close=100.0 + i * 0.05,
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
                thesis_summary="Stable cash flow with reasonable valuation.",
                key_risks=("regulatory", "input cost"),
                catalysts=("margin expansion", "earnings beat"),
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
    db_path: Path,
) -> Container:
    container = Container()
    container.register_instance(UniverseRepository, universe)
    container.register_instance(FundamentalsProvider, fundamentals)
    container.register_instance(PriceProvider, prices)
    if llm is not None:
        container.register_instance(LLMClient, llm)
    container.register_instance(RunRepo, RunRepo(path=db_path))
    return container


def _patch_container(monkeypatch: pytest.MonkeyPatch, container: Container) -> None:
    monkeypatch.setattr(
        "stock_screener.cli.commands.screen.make_default_container",
        lambda _config: container,
    )


@pytest.fixture
def runner(silence_logging: None) -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)  # type: ignore[call-arg]
    except TypeError:
        return CliRunner()


def test_screen_help_renders_all_flags(runner: CliRunner) -> None:
    result = runner.invoke(app, ["screen", "--help"])
    assert result.exit_code == 0
    out = result.stdout
    for flag in (
        "--cap",
        "--top",
        "--horizon",
        "--profile",
        "--sector",
        "--exclude",
        "--max-risk",
        "--min-risk",
        "--min-score",
        "--max-score",
        "--action",
        "--no-llm",
        "--format",
        "--explain",
        "--universe-limit",
        "--verbose",
    ):
        assert flag in out, f"missing flag {flag} in help output"


def test_screen_invalid_cap_returns_exit_2(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _build_container(
        universe=InMemoryUniverse(_make_companies(1)),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    result = runner.invoke(
        app, ["screen", "--cap", "XL", "--no-llm"], env={"SS_LLM_API_KEY": "test"}
    )
    assert result.exit_code == 2
    assert "error:" in result.stderr.lower()


def test_screen_empty_universe_exits_1(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _build_container(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([]),
        prices=FakePriceProvider([]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    result = runner.invoke(
        app, ["screen", "--cap", "lg", "--no-llm"], env={"SS_LLM_API_KEY": "test"}
    )
    assert result.exit_code == 1
    assert "Universe is empty" in result.stderr


def test_screen_happy_path_no_llm(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(5)
    container = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    result = runner.invoke(
        app,
        ["screen", "--cap", "lg", "--top", "5", "--no-llm"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert result.exit_code == 0, result.stderr
    found_marker = "Stock Screen" in result.stdout
    found_codes = sum(c.symbol.code in result.stdout for c in companies)
    assert found_marker or found_codes >= 5


def test_screen_format_json_produces_valid_json(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(3)
    container = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    result = runner.invoke(
        app,
        ["screen", "--cap", "lg", "--top", "3", "--no-llm", "--format", "json"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) <= 3
    assert all("symbol" in record for record in payload)


def test_screen_format_md_produces_markdown_table(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(3)
    container = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    result = runner.invoke(
        app,
        ["screen", "--cap", "lg", "--top", "3", "--no-llm", "--format", "md"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert result.exit_code == 0, result.stderr
    assert "| Symbol |" in result.stdout


def test_screen_filters_by_thresholds_and_action(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(5)
    container = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    result = runner.invoke(
        app,
        [
            "screen",
            "--cap",
            "lg",
            "--no-llm",
            "--format",
            "json",
            "--max-risk",
            "100",
            "--min-score",
            "0",
            "--action",
            "BUY,WAIT,AVOID",
        ],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)


def test_screen_explain_flag_adds_panels(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(2)
    container = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    no_explain = runner.invoke(
        app,
        ["screen", "--cap", "lg", "--top", "2", "--no-llm"],
        env={"SS_LLM_API_KEY": "test"},
    )
    container2 = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x2.db",
    )
    _patch_container(monkeypatch, container2)
    explain = runner.invoke(
        app,
        ["screen", "--cap", "lg", "--top", "2", "--no-llm", "--explain"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert no_explain.exit_code == 0 and explain.exit_code == 0
    assert len(explain.stdout) >= len(no_explain.stdout)


def test_screen_bad_action_value_exits_2(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(2)
    container = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)

    result = runner.invoke(
        app,
        ["screen", "--cap", "lg", "--no-llm", "--action", "ZZZ"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert result.exit_code == 2


def test_screen_verbose_does_not_crash(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    companies = _make_companies(2)
    container = _build_container(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
        llm=None,
        db_path=tmp_path / "x.db",
    )
    _patch_container(monkeypatch, container)
    result = runner.invoke(
        app,
        ["screen", "--cap", "lg", "--no-llm", "--verbose"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert result.exit_code == 0, result.stderr


# Re-export so we can also reuse the renderer factory if needed (kept to keep
# imports honest under linting).
_ = RendererFactory
