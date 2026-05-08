"""Unit tests for the PortfolioActionPolicy."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stock_screener.domain.entities.position import Position
from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.portfolio.policy import PortfolioActionPolicy
from stock_screener.domain.value_objects.action import Action, PortfolioAction
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


@pytest.fixture
def position() -> Position:
    return Position(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        avg_buy_price=2000.0,
        quantity=5,
    )


def _rec(score: float, risk: float) -> Recommendation:
    return Recommendation(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        company_name="Reliance",
        score=Score(score),
        conviction=Conviction.from_score(score),
        risk_pct=Pct(risk),
        suggested_horizon=Horizon.LONG,
        action=Action.WAIT,
        data_freshness=datetime.now(timezone.utc),
    )


def test_decide_with_no_price_falls_back_to_hold(position: Position) -> None:
    policy = PortfolioActionPolicy()
    action, rationale = policy.decide(
        position=position, current_price=None, recommendation=_rec(70, 40)
    )
    assert action is PortfolioAction.HOLD
    assert "unavailable" in rationale.lower()


def test_decide_no_recommendation_with_stop_breach_exits(position: Position) -> None:
    policy = PortfolioActionPolicy()
    action, _ = policy.decide(position=position, current_price=1400.0, recommendation=None)
    assert action is PortfolioAction.EXIT


def test_decide_no_recommendation_with_huge_gain_trims(position: Position) -> None:
    policy = PortfolioActionPolicy()
    action, _ = policy.decide(position=position, current_price=3500.0, recommendation=None)
    assert action is PortfolioAction.TRIM


def test_decide_strong_signal_recommends_add(position: Position) -> None:
    policy = PortfolioActionPolicy()
    action, _ = policy.decide(
        position=position, current_price=2100.0, recommendation=_rec(75, 35)
    )
    assert action is PortfolioAction.ADD


def test_decide_weak_signal_with_loss_exits(position: Position) -> None:
    policy = PortfolioActionPolicy()
    action, _ = policy.decide(
        position=position, current_price=1800.0, recommendation=_rec(25, 40)
    )
    assert action is PortfolioAction.EXIT


def test_decide_neutral_signal_holds(position: Position) -> None:
    policy = PortfolioActionPolicy()
    action, rationale = policy.decide(
        position=position, current_price=2050.0, recommendation=_rec(55, 50)
    )
    assert action is PortfolioAction.HOLD
    assert "hold" in rationale.lower()


def test_decide_huge_gain_with_weak_signal_trims(position: Position) -> None:
    policy = PortfolioActionPolicy()
    action, _ = policy.decide(
        position=position, current_price=3200.0, recommendation=_rec(55, 70)
    )
    assert action is PortfolioAction.TRIM


def test_custom_stop_loss_threshold(position: Position) -> None:
    policy = PortfolioActionPolicy(stop_loss_pct=10.0)
    action, _ = policy.decide(
        position=position, current_price=1750.0, recommendation=_rec(70, 40)
    )
    assert action is PortfolioAction.EXIT
