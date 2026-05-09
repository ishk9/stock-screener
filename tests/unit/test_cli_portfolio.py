"""CLI tests for ``ss portfolio``."""

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
from stock_screener.domain.ports.portfolio_repo import PortfolioRepository
from stock_screener.domain.ports.universe_repo import UniverseRepository
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.cache.sqlite_portfolio_repo import SqlitePortfolioRepository
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


def _flat_prices(close: float = 2200.0) -> PriceSeries:
    points = [
        PricePoint(
            on=date(2025, 1, 1) + timedelta(days=i),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1_000_000,
        )
        for i in range(260)
    ]
    return PriceSeries.from_points(points)


class _StubLLMClient:
    name = "stub"
    model = "stub-1"

    async def analyse(
        self, request: LLMRequest, schema: type
    ) -> Result[AnalysisOutput, object]:
        return Ok(
            AnalysisOutput(
                thesis_summary="Strong fundamentals.",
                key_risks=("regulatory",),
                catalysts=("margin expansion",),
                qualitative_risk=0.4,
                confidence=0.7,
                suggested_horizon="long",
            )
        )


def _basic_container(*, db_path: Path) -> Container:
    container = Container()
    container.register_instance(
        PortfolioRepository, SqlitePortfolioRepository(path=db_path)
    )
    return container


def _review_container(
    *,
    db_path: Path,
    universe: UniverseRepository,
    fundamentals: FundamentalsProvider,
    prices: PriceProvider,
    llm: LLMClient | None,
) -> Container:
    container = _basic_container(db_path=db_path)
    container.register_instance(UniverseRepository, universe)
    container.register_instance(FundamentalsProvider, fundamentals)
    container.register_instance(PriceProvider, prices)
    if llm is not None:
        container.register_instance(LLMClient, llm)
    return container


def _patch(monkeypatch: pytest.MonkeyPatch, container: Container) -> None:
    monkeypatch.setattr(
        "stock_screener.cli.commands.portfolio.make_default_container",
        lambda _config: container,
    )


@pytest.fixture
def runner(silence_logging: None) -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)  # type: ignore[call-arg]
    except TypeError:
        return CliRunner()


# --------------------------------------------------------------------------- #
# add / show / remove / clear
# --------------------------------------------------------------------------- #
def test_portfolio_add_then_show(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    add = runner.invoke(
        app,
        ["portfolio", "add", "RELIANCE", "2000", "--qty", "10"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert add.exit_code == 0, add.stderr
    assert "RELIANCE" in add.stdout

    show = runner.invoke(app, ["portfolio", "show"], env={"SS_LLM_API_KEY": "test"})
    assert show.exit_code == 0
    assert "RELIANCE" in show.stdout


def test_portfolio_add_negative_price_exits_2(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["portfolio", "add", "RELIANCE", "-100"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 2


def test_portfolio_add_invalid_bought_on_exits_2(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["portfolio", "add", "RELIANCE", "100", "--bought-on", "not-a-date"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 2


def test_portfolio_remove_missing_exits_1(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    res = runner.invoke(
        app, ["portfolio", "remove", "TCS"], env={"SS_LLM_API_KEY": "test"}
    )
    assert res.exit_code == 1


def test_portfolio_clear_with_yes_empties(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    runner.invoke(
        app, ["portfolio", "add", "RELIANCE", "2000"], env={"SS_LLM_API_KEY": "test"}
    )
    res = runner.invoke(
        app, ["portfolio", "clear", "--yes"], env={"SS_LLM_API_KEY": "test"}
    )
    assert res.exit_code == 0
    show = runner.invoke(app, ["portfolio", "show"], env={"SS_LLM_API_KEY": "test"})
    assert "Portfolio is empty" in show.stdout


def test_portfolio_clear_without_yes_aborts(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["portfolio", "clear"],
        input="n\n",
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code != 0


def test_portfolio_show_empty(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    res = runner.invoke(app, ["portfolio", "show"], env={"SS_LLM_API_KEY": "test"})
    assert res.exit_code == 0
    assert "Portfolio is empty" in res.stdout


# --------------------------------------------------------------------------- #
# import
# --------------------------------------------------------------------------- #
def test_portfolio_import_csv(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    csv_path = tmp_path / "p.csv"
    csv_path.write_text("symbol,avg_price,qty\nRELIANCE,2000,10\nTCS,3500,5\n")

    res = runner.invoke(
        app, ["portfolio", "import", str(csv_path)], env={"SS_LLM_API_KEY": "test"}
    )
    assert res.exit_code == 0, res.stderr
    assert "Imported 2" in res.stdout

    show = runner.invoke(app, ["portfolio", "show"], env={"SS_LLM_API_KEY": "test"})
    assert "RELIANCE" in show.stdout
    assert "TCS" in show.stdout


def test_portfolio_import_missing_symbol_column_exits_2(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    csv_path = tmp_path / "p.csv"
    csv_path.write_text("name,avg_price\nReliance,2000\n")

    res = runner.invoke(
        app, ["portfolio", "import", str(csv_path)], env={"SS_LLM_API_KEY": "test"}
    )
    assert res.exit_code == 2


def test_portfolio_import_replace_clears_existing(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _basic_container(db_path=tmp_path / "x.db")
    _patch(monkeypatch, container)

    runner.invoke(
        app,
        ["portfolio", "add", "INFY", "1500", "--qty", "20"],
        env={"SS_LLM_API_KEY": "test"},
    )

    csv_path = tmp_path / "p.csv"
    csv_path.write_text("symbol,avg_price,qty\nRELIANCE,2000,10\n")

    res = runner.invoke(
        app,
        ["portfolio", "import", str(csv_path), "--replace"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 0, res.stderr

    show = runner.invoke(app, ["portfolio", "show"], env={"SS_LLM_API_KEY": "test"})
    assert "RELIANCE" in show.stdout
    assert "INFY" not in show.stdout


# --------------------------------------------------------------------------- #
# review
# --------------------------------------------------------------------------- #
def test_portfolio_review_empty(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _review_container(
        db_path=tmp_path / "x.db",
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([]),
        prices=FakePriceProvider([]),
        llm=None,
    )
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["portfolio", "review", "--no-llm"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 0, res.stderr


def test_portfolio_review_populated(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "x.db"
    repo = SqlitePortfolioRepository(path=db_path)
    from stock_screener.domain.entities.position import Position

    repo.upsert(
        Position(
            symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
            avg_buy_price=2000.0,
            quantity=5,
        )
    )
    company = Company(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        name="Reliance Industries",
        sector="Energy",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    container = _review_container(
        db_path=db_path,
        universe=InMemoryUniverse([company]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices(close=2200.0))]),
        llm=None,
    )
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["portfolio", "review", "--no-llm"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 0, res.stderr
    assert "RELIANCE" in res.stdout
    assert any(act in res.stdout for act in ("ADD", "HOLD", "TRIM", "EXIT"))


def test_portfolio_review_format_json(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "x.db"
    repo = SqlitePortfolioRepository(path=db_path)
    from stock_screener.domain.entities.position import Position

    repo.upsert(
        Position(
            symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
            avg_buy_price=2000.0,
            quantity=5,
        )
    )
    company = Company(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        name="Reliance Industries",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    container = _review_container(
        db_path=db_path,
        universe=InMemoryUniverse([company]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices(close=2200.0))]),
        llm=None,
    )
    _patch(monkeypatch, container)

    res = runner.invoke(
        app,
        ["portfolio", "review", "--no-llm", "--format", "json"],
        env={"SS_LLM_API_KEY": "test"},
    )
    assert res.exit_code == 0, res.stderr
    payload = json.loads(res.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 1
