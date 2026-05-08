"""Unit tests for SqlitePortfolioRepository."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_screener.domain.entities.position import Position
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.cache.sqlite_portfolio_repo import SqlitePortfolioRepository


@pytest.fixture
def repo(tmp_path: Path) -> SqlitePortfolioRepository:
    return SqlitePortfolioRepository(path=tmp_path / "portfolio.db")


def _pos(code: str, price: float = 1000.0, qty: float = 1.0) -> Position:
    return Position(
        symbol=Symbol(code=code, exchange=Exchange.NSE),
        avg_buy_price=price,
        quantity=qty,
    )


def test_starts_empty(repo: SqlitePortfolioRepository) -> None:
    assert repo.count() == 0
    assert repo.list() == []


def test_upsert_then_get(repo: SqlitePortfolioRepository) -> None:
    repo.upsert(_pos("RELIANCE", 2000, 10))
    pos = repo.get("RELIANCE")
    assert pos is not None
    assert pos.avg_buy_price == 2000.0
    assert pos.quantity == 10.0


def test_upsert_is_idempotent(repo: SqlitePortfolioRepository) -> None:
    repo.upsert(_pos("RELIANCE", 2000, 10))
    repo.upsert(_pos("RELIANCE", 2100, 12))    # update
    pos = repo.get("RELIANCE")
    assert pos.avg_buy_price == 2100.0
    assert pos.quantity == 12.0
    assert repo.count() == 1


def test_remove_existing(repo: SqlitePortfolioRepository) -> None:
    repo.upsert(_pos("RELIANCE", 2000))
    assert repo.remove("RELIANCE") is True
    assert repo.get("RELIANCE") is None
    assert repo.count() == 0


def test_remove_missing(repo: SqlitePortfolioRepository) -> None:
    assert repo.remove("MISSING") is False


def test_list_returns_all(repo: SqlitePortfolioRepository) -> None:
    repo.upsert(_pos("A", 100))
    repo.upsert(_pos("B", 200))
    repo.upsert(_pos("C", 300))
    assert {p.symbol.code for p in repo.list()} == {"A", "B", "C"}


def test_clear(repo: SqlitePortfolioRepository) -> None:
    repo.upsert(_pos("A"))
    repo.upsert(_pos("B"))
    repo.clear()
    assert repo.count() == 0


def test_optional_fields_round_trip(repo: SqlitePortfolioRepository) -> None:
    pos = Position(
        symbol=Symbol(code="TCS", exchange=Exchange.NSE),
        avg_buy_price=3500.0,
        quantity=4,
        bought_on=date(2024, 5, 1),
        notes="conviction buy",
    )
    repo.upsert(pos)
    got = repo.get("TCS")
    assert got is not None
    assert got.bought_on == date(2024, 5, 1)
    assert got.notes == "conviction buy"


def test_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    repo1 = SqlitePortfolioRepository(path=db)
    repo1.upsert(_pos("RELIANCE", 2000, 5))

    repo2 = SqlitePortfolioRepository(path=db)
    pos = repo2.get("RELIANCE")
    assert pos is not None
    assert pos.avg_buy_price == 2000.0


def test_get_uppercases(repo: SqlitePortfolioRepository) -> None:
    repo.upsert(_pos("RELIANCE"))
    assert repo.get("reliance") is not None
