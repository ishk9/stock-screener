"""Tests for new MinRiskSpec / MaxScoreSpec specifications."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

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


def _rec(score: float, risk: float) -> Recommendation:
    return Recommendation(
        symbol=Symbol(code="TEST", exchange=Exchange.NSE),
        company_name="Test",
        score=Score(score),
        conviction=Conviction.from_score(score),
        risk_pct=Pct(risk),
        suggested_horizon=Horizon.LONG,
        action=Action.WAIT,
        data_freshness=datetime.now(timezone.utc),
    )


def test_min_risk_spec_pass() -> None:
    assert MinRiskSpec(Pct(30)).is_satisfied_by(_rec(80, 35)) is True


def test_min_risk_spec_fail() -> None:
    assert MinRiskSpec(Pct(50)).is_satisfied_by(_rec(80, 30)) is False


def test_max_score_spec_pass() -> None:
    assert MaxScoreSpec(80).is_satisfied_by(_rec(70, 30)) is True


def test_max_score_spec_fail() -> None:
    assert MaxScoreSpec(60).is_satisfied_by(_rec(70, 30)) is False


def test_specs_compose_with_and() -> None:
    spec = MinScoreSpec(60) & MaxRiskSpec(Pct(50))
    assert spec.is_satisfied_by(_rec(70, 40)) is True
    assert spec.is_satisfied_by(_rec(70, 60)) is False
    assert spec.is_satisfied_by(_rec(50, 40)) is False


def test_specs_compose_with_or() -> None:
    spec = MinScoreSpec(80) | MaxRiskSpec(Pct(20))
    assert spec.is_satisfied_by(_rec(85, 90)) is True   # high score
    assert spec.is_satisfied_by(_rec(50, 15)) is True   # very safe
    assert spec.is_satisfied_by(_rec(50, 50)) is False


@pytest.mark.parametrize("score,risk", [(0, 0), (100, 100), (50, 50)])
def test_boundary_values(score: float, risk: float) -> None:
    rec = _rec(score, risk)
    assert MinScoreSpec(score).is_satisfied_by(rec)
    assert MaxScoreSpec(score).is_satisfied_by(rec)
    assert MinRiskSpec(Pct(risk)).is_satisfied_by(rec)
    assert MaxRiskSpec(Pct(risk)).is_satisfied_by(rec)
