"""Unit tests for Position entity + P&L math."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from stock_screener.domain.entities.position import Position
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


@pytest.fixture
def reliance() -> Symbol:
    return Symbol(code="RELIANCE", exchange=Exchange.NSE)


def test_basic_position_cost_basis(reliance: Symbol) -> None:
    p = Position(symbol=reliance, avg_buy_price=2000.0, quantity=10)
    assert p.cost_basis == pytest.approx(20_000.0)


def test_negative_price_rejected(reliance: Symbol) -> None:
    with pytest.raises(ValidationError):
        Position(symbol=reliance, avg_buy_price=-1, quantity=10)


def test_zero_quantity_rejected(reliance: Symbol) -> None:
    with pytest.raises(ValidationError):
        Position(symbol=reliance, avg_buy_price=100, quantity=0)


def test_pnl_positive(reliance: Symbol) -> None:
    p = Position(symbol=reliance, avg_buy_price=100, quantity=10)
    abs_pnl, pct = p.unrealised_pnl(150)
    assert abs_pnl == pytest.approx(500.0)
    assert pct == pytest.approx(50.0)


def test_pnl_negative(reliance: Symbol) -> None:
    p = Position(symbol=reliance, avg_buy_price=200, quantity=5)
    abs_pnl, pct = p.unrealised_pnl(160)
    assert abs_pnl == pytest.approx(-200.0)
    assert pct == pytest.approx(-20.0)


def test_pnl_breakeven(reliance: Symbol) -> None:
    p = Position(symbol=reliance, avg_buy_price=100, quantity=10)
    abs_pnl, pct = p.unrealised_pnl(100)
    assert abs_pnl == 0.0
    assert pct == 0.0


def test_pnl_invalid_price_raises(reliance: Symbol) -> None:
    p = Position(symbol=reliance, avg_buy_price=100, quantity=10)
    with pytest.raises(ValueError):
        p.unrealised_pnl(0)


def test_position_immutable(reliance: Symbol) -> None:
    p = Position(symbol=reliance, avg_buy_price=100, quantity=1)
    with pytest.raises(ValidationError):
        p.avg_buy_price = 200  # type: ignore[misc]


def test_optional_fields(reliance: Symbol) -> None:
    p = Position(
        symbol=reliance,
        avg_buy_price=2000.0,
        quantity=5,
        bought_on=date(2024, 1, 15),
        notes="long-term hold",
    )
    assert p.bought_on == date(2024, 1, 15)
    assert p.notes == "long-term hold"
