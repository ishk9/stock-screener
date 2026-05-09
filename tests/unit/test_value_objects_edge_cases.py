"""Edge-case tests for the domain value objects.

Complements the existing strategy/specification tests by drilling into the
parsing, arithmetic and boundary behaviour of every VO.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

from stock_screener.domain.value_objects.action import Action, PortfolioAction
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import (
    LARGE_CAP_TOP_N,
    MID_CAP_END_N,
    MarketCapBucket,
)
from stock_screener.domain.value_objects.money import Money
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


# --------------------------------------------------------------------------- #
# Symbol
# --------------------------------------------------------------------------- #
class TestSymbol:
    def test_parse_bare_default_to_nse(self) -> None:
        s = Symbol.parse("RELIANCE")
        assert s.code == "RELIANCE"
        assert s.exchange is Exchange.NSE

    @pytest.mark.parametrize("raw,exp_code,exp_ex", [
        ("RELIANCE.NS", "RELIANCE", Exchange.NSE),
        ("TCS.BO", "TCS", Exchange.BSE),
        ("reliance.ns", "RELIANCE", Exchange.NSE),
        ("  TCS.NS  ", "TCS", Exchange.NSE),
        ("NSE:HDFCBANK", "HDFCBANK", Exchange.NSE),
        ("BSE:500325", "500325", Exchange.BSE),
        ("nse:tcs", "TCS", Exchange.NSE),
    ])
    def test_parse_variants(self, raw: str, exp_code: str, exp_ex: Exchange) -> None:
        s = Symbol.parse(raw)
        assert s.code == exp_code
        assert s.exchange is exp_ex

    @pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
    def test_parse_empty_raises(self, raw: str) -> None:
        with pytest.raises(ValueError):
            Symbol.parse(raw)

    def test_parse_unknown_exchange_prefix_raises(self) -> None:
        with pytest.raises(ValueError):
            Symbol.parse("NYSE:AAPL")

    def test_construct_lowercases_to_upper(self) -> None:
        s = Symbol(code="reliance", exchange=Exchange.NSE)
        assert s.code == "RELIANCE"

    def test_construct_strips_whitespace(self) -> None:
        s = Symbol(code="  TCS  ", exchange=Exchange.BSE)
        assert s.code == "TCS"

    def test_construct_rejects_internal_whitespace(self) -> None:
        with pytest.raises(ValueError):
            Symbol(code="REL IANCE", exchange=Exchange.NSE)

    def test_construct_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            Symbol(code="   ", exchange=Exchange.NSE)

    def test_yahoo_format(self) -> None:
        assert Symbol(code="TCS", exchange=Exchange.NSE).yahoo() == "TCS.NS"
        assert Symbol(code="500325", exchange=Exchange.BSE).yahoo() == "500325.BO"

    def test_str_is_yahoo(self) -> None:
        s = Symbol(code="TCS", exchange=Exchange.NSE)
        assert str(s) == s.yahoo()

    def test_immutable(self) -> None:
        s = Symbol(code="RELIANCE", exchange=Exchange.NSE)
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.code = "TCS"  # type: ignore[misc]

    def test_equality_and_hashable(self) -> None:
        a = Symbol(code="TCS", exchange=Exchange.NSE)
        b = Symbol(code="tcs", exchange=Exchange.NSE)
        c = Symbol(code="TCS", exchange=Exchange.BSE)
        assert a == b
        assert a != c
        assert {a, b, c} == {a, c}  # dedup of first two


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
class TestMoney:
    def test_default_currency_inr(self) -> None:
        m = Money(100)
        assert m.currency == "INR"

    @pytest.mark.parametrize("amount,expected", [
        (10, Decimal("10")),
        (10.5, Decimal("10.5")),
        ("10.99", Decimal("10.99")),
        (Decimal("5.25"), Decimal("5.25")),
    ])
    def test_amount_coercion(self, amount, expected: Decimal) -> None:
        assert Money(amount).amount == expected

    def test_currency_uppercased(self) -> None:
        assert Money(1, "usd").currency == "USD"

    def test_addition(self) -> None:
        assert (Money(10) + Money(20)).amount == Decimal("30")

    def test_subtraction(self) -> None:
        assert (Money(50) - Money(20)).amount == Decimal("30")

    def test_currency_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="currency mismatch"):
            Money(10, "INR") + Money(10, "USD")

    def test_str_inr_uses_rupee_symbol(self) -> None:
        assert "₹" in str(Money(1234.56, "INR"))

    def test_str_other_currency_uses_code(self) -> None:
        assert str(Money(1, "USD")).startswith("USD ")

    def test_no_floating_point_drift(self) -> None:
        a = Money("0.10") + Money("0.20")
        assert a.amount == Decimal("0.30")

    def test_immutable(self) -> None:
        m = Money(10)
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.amount = Decimal("20")  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Pct
# --------------------------------------------------------------------------- #
class TestPct:
    @pytest.mark.parametrize("value", [0.0, 50.0, 100.0])
    def test_valid_boundary(self, value: float) -> None:
        assert Pct(value).value == value

    @pytest.mark.parametrize("value", [-0.001, 100.001, -10, 200])
    def test_invalid_raises(self, value: float) -> None:
        with pytest.raises(ValueError):
            Pct(value)

    def test_from_ratio_clamps_above(self) -> None:
        assert Pct.from_ratio(1.5).value == 100.0

    def test_from_ratio_clamps_below(self) -> None:
        assert Pct.from_ratio(-0.5).value == 0.0

    def test_as_ratio_round_trip(self) -> None:
        assert Pct(40).as_ratio == 0.4

    def test_str_format(self) -> None:
        assert str(Pct(12.345)) == "12.35%"

    def test_ordering(self) -> None:
        assert Pct(10) < Pct(20)
        assert sorted([Pct(50), Pct(10), Pct(30)]) == [Pct(10), Pct(30), Pct(50)]

    def test_rounding_to_4dp(self) -> None:
        assert Pct(12.345678).value == 12.3457

    @given(st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=50)
    def test_from_ratio_round_trip(self, ratio: float) -> None:
        p = Pct.from_ratio(ratio)
        assert 0.0 <= p.value <= 100.0
        assert abs(p.as_ratio - ratio) < 1e-3


# --------------------------------------------------------------------------- #
# Score
# --------------------------------------------------------------------------- #
class TestScore:
    @pytest.mark.parametrize("v", [0, 50, 100])
    def test_boundary_valid(self, v: float) -> None:
        assert Score(v).value == v

    @pytest.mark.parametrize("v", [-0.01, 100.01, -1, 200])
    def test_boundary_invalid(self, v: float) -> None:
        with pytest.raises(ValueError):
            Score(v)

    def test_clamped_above(self) -> None:
        assert Score.clamped(150).value == 100.0

    def test_clamped_below(self) -> None:
        assert Score.clamped(-10).value == 0.0

    def test_clamped_in_range(self) -> None:
        assert Score.clamped(75).value == 75.0

    def test_str_format(self) -> None:
        assert str(Score(82.456)) == "82.46"

    def test_ordering(self) -> None:
        assert Score(10) < Score(20)


# --------------------------------------------------------------------------- #
# Horizon
# --------------------------------------------------------------------------- #
class TestHorizon:
    def test_short_months_range(self) -> None:
        assert Horizon.SHORT.months == (0, 6)

    def test_mid_months_range(self) -> None:
        assert Horizon.MID.months == (6, 24)

    def test_long_months_range(self) -> None:
        assert Horizon.LONG.months == (24, 120)

    def test_label_short(self) -> None:
        assert "Short term" in Horizon.SHORT.label

    def test_string_value(self) -> None:
        assert Horizon.LONG.value == "long"

    def test_construct_from_string(self) -> None:
        assert Horizon("mid") is Horizon.MID

    def test_invalid_string(self) -> None:
        with pytest.raises(ValueError):
            Horizon("yearly")


# --------------------------------------------------------------------------- #
# MarketCapBucket
# --------------------------------------------------------------------------- #
class TestMarketCapBucket:
    @pytest.mark.parametrize("code,bucket", [
        ("lg", MarketCapBucket.LARGE),
        ("md", MarketCapBucket.MID),
        ("sm", MarketCapBucket.SMALL),
        ("LG", MarketCapBucket.LARGE),
        ("  Md  ", MarketCapBucket.MID),
    ])
    def test_from_short_code(self, code: str, bucket: MarketCapBucket) -> None:
        assert MarketCapBucket.from_short_code(code) is bucket

    @pytest.mark.parametrize("bad", ["", "large", "x", "small"])
    def test_from_short_code_invalid(self, bad: str) -> None:
        with pytest.raises(ValueError):
            MarketCapBucket.from_short_code(bad)

    @pytest.mark.parametrize("rank,expected", [
        (1, MarketCapBucket.LARGE),
        (LARGE_CAP_TOP_N, MarketCapBucket.LARGE),
        (LARGE_CAP_TOP_N + 1, MarketCapBucket.MID),
        (MID_CAP_END_N, MarketCapBucket.MID),
        (MID_CAP_END_N + 1, MarketCapBucket.SMALL),
        (5_000, MarketCapBucket.SMALL),
    ])
    def test_from_rank_boundaries(self, rank: int, expected: MarketCapBucket) -> None:
        assert MarketCapBucket.from_rank(rank) is expected

    @pytest.mark.parametrize("rank", [0, -1, -100])
    def test_from_rank_invalid(self, rank: int) -> None:
        with pytest.raises(ValueError):
            MarketCapBucket.from_rank(rank)

    def test_label_present_for_each(self) -> None:
        for b in MarketCapBucket:
            assert "cap" in b.label.lower()


# --------------------------------------------------------------------------- #
# Conviction
# --------------------------------------------------------------------------- #
class TestConviction:
    @pytest.mark.parametrize("score,expected", [
        (0, Conviction.LOW),
        (49.999, Conviction.LOW),
        (50, Conviction.MEDIUM),
        (74.999, Conviction.MEDIUM),
        (75, Conviction.HIGH),
        (100, Conviction.HIGH),
    ])
    def test_from_score(self, score: float, expected: Conviction) -> None:
        assert Conviction.from_score(score) is expected

    def test_string_value(self) -> None:
        assert Conviction.HIGH.value == "HIGH"


# --------------------------------------------------------------------------- #
# Action sanity (companion to test_action_vo.py)
# --------------------------------------------------------------------------- #
class TestActionEdgeCases:
    @pytest.mark.parametrize("score,risk,conv,expected", [
        (40, 50, False, Action.WAIT),     # exact lower-bound score, neutral
        (39.99, 50, False, Action.AVOID), # just below threshold
        (75, 50, False, Action.BUY),      # exactly at risk cap
        (75, 50.01, False, Action.WAIT),  # one tick over risk cap
        (90, 75, True, Action.AVOID),     # very high risk overrides BUY
    ])
    def test_action_thresholds(
        self, score: float, risk: float, conv: bool, expected: Action
    ) -> None:
        assert Action.from_signal(
            score=score, risk_pct=risk, conviction_high=conv
        ) is expected

    def test_portfolio_action_priority_exit_over_trim(self) -> None:
        # Big gain but score < 35 → EXIT wins.
        assert PortfolioAction.from_signal(
            score=20, risk_pct=40, unrealised_pnl_pct=80, stop_loss_breached=False
        ) is PortfolioAction.EXIT

    def test_portfolio_action_priority_exit_over_add(self) -> None:
        # High score but stop-loss breached → EXIT.
        assert PortfolioAction.from_signal(
            score=80, risk_pct=40, unrealised_pnl_pct=-30, stop_loss_breached=True
        ) is PortfolioAction.EXIT
