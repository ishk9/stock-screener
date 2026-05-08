"""Tests for ``RunRepo``."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.cache.run_repo import RunRepo


def _rec(code: str, score: float = 80.0) -> Recommendation:
    return Recommendation(
        symbol=Symbol(code=code, exchange=Exchange.NSE),
        company_name=f"{code} Ltd",
        sector="IT",
        score=Score(score),
        conviction=Conviction.HIGH,
        risk_pct=Pct(20.0),
        suggested_horizon=Horizon.LONG,
        thesis_summary="Solid fundamentals",
        key_risks=("regulation",),
        catalysts=("orders",),
    )


@pytest.fixture()
def repo(tmp_path: Path) -> RunRepo:
    return RunRepo(tmp_path / "runs.db")


def test_last_run_when_empty(repo: RunRepo) -> None:
    assert repo.last_run() is None


def test_save_and_retrieve_single_run(repo: RunRepo) -> None:
    recs = [_rec("A"), _rec("B", 70.0)]
    repo.save_run("run-1", "ss screen", {"top": 5}, recs)

    last = repo.last_run()
    assert last is not None
    assert last["id"] == "run-1"
    assert last["command"] == "ss screen"
    assert last["payload"] == {"top": 5}
    fetched = last["recommendations"]
    assert [r.symbol.code for r in fetched] == ["A", "B"]
    assert fetched[0].thesis_summary == "Solid fundamentals"
    assert fetched[0].conviction is Conviction.HIGH
    assert fetched[0].suggested_horizon is Horizon.LONG


def test_save_run_overwrites_recommendations_for_same_id(repo: RunRepo) -> None:
    repo.save_run("r", "cmd", {}, [_rec("A")])
    repo.save_run("r", "cmd", {}, [_rec("Z")])
    last = repo.last_run()
    assert last is not None
    assert [r.symbol.code for r in last["recommendations"]] == ["Z"]


def test_last_run_returns_most_recent(repo: RunRepo) -> None:
    import time

    repo.save_run("first", "cmd", {}, [_rec("A")])
    time.sleep(0.01)
    repo.save_run("second", "cmd", {}, [_rec("B")])
    last = repo.last_run()
    assert last is not None
    assert last["id"] == "second"
