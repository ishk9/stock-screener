"""Unit tests for the Action / PortfolioAction value objects."""

from __future__ import annotations

import pytest

from stock_screener.domain.value_objects.action import Action, PortfolioAction


class TestAction:
    def test_buy_when_score_high_and_risk_low(self) -> None:
        assert Action.from_signal(score=80, risk_pct=30, conviction_high=True) is Action.BUY

    def test_avoid_when_low_score(self) -> None:
        assert Action.from_signal(score=30, risk_pct=20, conviction_high=False) is Action.AVOID

    def test_avoid_when_extreme_risk(self) -> None:
        assert Action.from_signal(score=80, risk_pct=85, conviction_high=True) is Action.AVOID

    def test_wait_when_in_between(self) -> None:
        assert Action.from_signal(score=55, risk_pct=55, conviction_high=False) is Action.WAIT

    def test_high_conviction_lowers_buy_threshold(self) -> None:
        assert Action.from_signal(score=62, risk_pct=53, conviction_high=True) is Action.BUY
        assert Action.from_signal(score=62, risk_pct=53, conviction_high=False) is Action.WAIT


class TestPortfolioAction:
    def test_exit_on_low_score(self) -> None:
        a = PortfolioAction.from_signal(
            score=30, risk_pct=40, unrealised_pnl_pct=10, stop_loss_breached=False
        )
        assert a is PortfolioAction.EXIT

    def test_exit_on_stop_loss_breach(self) -> None:
        a = PortfolioAction.from_signal(
            score=70, risk_pct=40, unrealised_pnl_pct=-30, stop_loss_breached=True
        )
        assert a is PortfolioAction.EXIT

    def test_exit_on_high_risk_with_loss(self) -> None:
        a = PortfolioAction.from_signal(
            score=55, risk_pct=85, unrealised_pnl_pct=-10, stop_loss_breached=False
        )
        assert a is PortfolioAction.EXIT

    def test_trim_on_big_gain_with_weak_signal(self) -> None:
        a = PortfolioAction.from_signal(
            score=55, risk_pct=40, unrealised_pnl_pct=60, stop_loss_breached=False
        )
        assert a is PortfolioAction.TRIM

    def test_add_on_strong_signal(self) -> None:
        a = PortfolioAction.from_signal(
            score=72, risk_pct=45, unrealised_pnl_pct=5, stop_loss_breached=False
        )
        assert a is PortfolioAction.ADD

    def test_hold_on_neutral_signal(self) -> None:
        a = PortfolioAction.from_signal(
            score=55, risk_pct=50, unrealised_pnl_pct=10, stop_loss_breached=False
        )
        assert a is PortfolioAction.HOLD


@pytest.mark.parametrize("value", ["BUY", "WAIT", "AVOID"])
def test_action_string_round_trip(value: str) -> None:
    assert Action(value).value == value


@pytest.mark.parametrize("value", ["ADD", "HOLD", "TRIM", "EXIT"])
def test_portfolio_action_string_round_trip(value: str) -> None:
    assert PortfolioAction(value).value == value
