"""Tests for ``SqliteUniverseRepo``."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_screener.domain.entities.company import Company
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.cache.sqlite_universe_repo import SqliteUniverseRepo


def _company(
    code: str,
    *,
    exchange: Exchange = Exchange.NSE,
    bucket: MarketCapBucket | None = None,
    rank: int | None = None,
    sector: str | None = "IT",
) -> Company:
    return Company(
        symbol=Symbol(code=code, exchange=exchange),
        name=f"{code} Ltd",
        isin=f"IN{code}",
        sector=sector,
        industry="Software",
        market_cap_inr=1.0,
        market_cap_bucket=bucket,
        market_cap_rank=rank,
        listing_date="2020-01-01",
    )


@pytest.fixture()
def repo(tmp_path: Path) -> SqliteUniverseRepo:
    return SqliteUniverseRepo(tmp_path / "uni.db")


def test_count_starts_at_zero(repo: SqliteUniverseRepo) -> None:
    assert repo.count() == 0
    assert repo.last_refreshed_at() is None


def test_upsert_many_persists_companies_and_meta(repo: SqliteUniverseRepo) -> None:
    repo.upsert_many([_company("A", bucket=MarketCapBucket.LARGE, rank=1)])
    assert repo.count() == 1
    assert repo.last_refreshed_at() is not None
    fetched = repo.get("A")
    assert fetched is not None
    assert fetched.symbol.code == "A"
    assert fetched.market_cap_bucket is MarketCapBucket.LARGE
    assert fetched.symbol.exchange is Exchange.NSE


def test_upsert_is_idempotent(repo: SqliteUniverseRepo) -> None:
    rows = [_company("A", bucket=MarketCapBucket.LARGE, rank=1)]
    repo.upsert_many(rows)
    repo.upsert_many(rows)
    assert repo.count() == 1


def test_list_filters_by_bucket(repo: SqliteUniverseRepo) -> None:
    repo.upsert_many(
        [
            _company("LARGE1", bucket=MarketCapBucket.LARGE, rank=1),
            _company("MID1", bucket=MarketCapBucket.MID, rank=120),
            _company("SMALL1", bucket=MarketCapBucket.SMALL, rank=900),
        ]
    )
    larges = repo.list(MarketCapBucket.LARGE)
    assert {c.symbol.code for c in larges} == {"LARGE1"}
    all_ = repo.list()
    assert {c.symbol.code for c in all_} == {"LARGE1", "MID1", "SMALL1"}


def test_get_prefers_nse_when_dual_listed(repo: SqliteUniverseRepo) -> None:
    repo.upsert_many(
        [
            _company("DUAL", exchange=Exchange.BSE, rank=2),
            _company("DUAL", exchange=Exchange.NSE, rank=2),
        ]
    )
    fetched = repo.get("DUAL")
    assert fetched is not None
    assert fetched.symbol.exchange is Exchange.NSE


def test_get_returns_none_when_unknown(repo: SqliteUniverseRepo) -> None:
    assert repo.get("NOPE") is None
