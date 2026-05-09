"""Tests for the ``_build_rec_specs`` helper in ``cli.commands.screen``."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import typer

from stock_screener.cli.commands.screen import _build_rec_specs
from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.specifications import (
    MaxRiskSpec,
    MaxScoreSpec,
    MinRiskSpec,
    MinScoreSpec,
)
from stock_screener.domain.value_objects.action import Action
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


def _rec(
    *,
    score: float = 75.0,
    risk: float = 30.0,
    action: Action = Action.BUY,
) -> Recommendation:
    return Recommendation(
        symbol=Symbol(code="X", exchange=Exchange.NSE),
        company_name="X",
        score=Score(score),
        conviction=Conviction.from_score(score),
        risk_pct=Pct(risk),
        suggested_horizon=Horizon.LONG,
        action=action,
        data_freshness=datetime.now(timezone.utc),
    )


def test_all_none_returns_empty_list() -> None:
    assert _build_rec_specs(None, None, None, None, None) == []


def test_max_risk_only() -> None:
    specs = _build_rec_specs(50.0, None, None, None, None)
    assert len(specs) == 1
    assert isinstance(specs[0], MaxRiskSpec)


def test_min_risk_only() -> None:
    specs = _build_rec_specs(None, 10.0, None, None, None)
    assert len(specs) == 1
    assert isinstance(specs[0], MinRiskSpec)


def test_min_score_only() -> None:
    specs = _build_rec_specs(None, None, 60.0, None, None)
    assert len(specs) == 1
    assert isinstance(specs[0], MinScoreSpec)


def test_max_score_only() -> None:
    specs = _build_rec_specs(None, None, None, 90.0, None)
    assert len(specs) == 1
    assert isinstance(specs[0], MaxScoreSpec)


def test_combined_returns_all_specs() -> None:
    specs = _build_rec_specs(50.0, 10.0, 60.0, 90.0, "BUY")
    assert len(specs) == 5


def test_action_buy_wait_filter_accepts_listed() -> None:
    specs = _build_rec_specs(None, None, None, None, "BUY,WAIT")
    assert len(specs) == 1
    spec = specs[0]
    assert spec.is_satisfied_by(_rec(action=Action.BUY)) is True
    assert spec.is_satisfied_by(_rec(action=Action.WAIT)) is True
    assert spec.is_satisfied_by(_rec(action=Action.AVOID)) is False


def test_action_garbage_raises_bad_parameter() -> None:
    with pytest.raises(typer.BadParameter):
        _build_rec_specs(None, None, None, None, "GARBAGE")


def test_combined_spec_filters_real_recommendation() -> None:
    specs = _build_rec_specs(40.0, 5.0, 60.0, 95.0, "BUY")
    spec = specs[0]
    for s in specs[1:]:
        spec = spec & s

    passing = _rec(score=80.0, risk=20.0, action=Action.BUY)
    failing_score = _rec(score=50.0, risk=20.0, action=Action.BUY)
    failing_risk = _rec(score=80.0, risk=60.0, action=Action.BUY)
    failing_action = _rec(score=80.0, risk=20.0, action=Action.WAIT)

    assert spec.is_satisfied_by(passing)
    assert not spec.is_satisfied_by(failing_score)
    assert not spec.is_satisfied_by(failing_risk)
    assert not spec.is_satisfied_by(failing_action)
