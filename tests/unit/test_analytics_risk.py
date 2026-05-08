"""Tests for analytics.risk."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from stock_screener.domain.analytics.risk import (
    DEFAULT_WEIGHTS,
    RiskBreakdown,
    compute_risk,
)
from stock_screener.domain.value_objects.pct import Pct

from .conftest import (
    make_fundamentals,
    make_price_series,
    make_snapshot,
    make_trend_prices,
)


class TestComputeRisk:
    def test_returns_risk_breakdown(self) -> None:
        snap = make_snapshot()
        risk = compute_risk(snap)
        assert isinstance(risk, RiskBreakdown)
        assert isinstance(risk.composite, Pct)

    def test_composite_always_valid_pct(self) -> None:
        risk = compute_risk(make_snapshot())
        assert 0.0 <= risk.composite.value <= 100.0

    def test_no_data_yields_neutral_composite(self) -> None:
        snap = make_snapshot(omit_fundamentals=True, omit_prices=True)
        risk = compute_risk(snap)
        assert risk.volatility is None
        assert risk.leverage is None
        assert risk.drawdown is None
        assert risk.quality_concern is None
        assert risk.composite.value == pytest.approx(50.0)

    def test_high_leverage_increases_composite(self) -> None:
        low = make_snapshot(
            fundamentals=make_fundamentals(debt_to_equity=0.2),
            omit_prices=True,
        )
        high = make_snapshot(
            fundamentals=make_fundamentals(debt_to_equity=2.5),
            omit_prices=True,
        )
        assert compute_risk(high).composite.value > compute_risk(low).composite.value

    def test_volatile_prices_increase_composite(self) -> None:
        calm = make_snapshot(prices=make_trend_prices(n=300, drift=0.0001))
        volatile_closes: list[float] = []
        p = 100.0
        for i in range(300):
            p = p * (1.0 + 0.05 * ((-1) ** i))
            volatile_closes.append(round(p, 4))
        chaotic = make_snapshot(prices=make_price_series(volatile_closes))
        assert compute_risk(chaotic).volatility is not None
        assert compute_risk(calm).volatility is not None
        assert compute_risk(chaotic).volatility.value >= compute_risk(calm).volatility.value  # type: ignore[union-attr]

    def test_beta_optional_when_no_market_returns(self) -> None:
        snap = make_snapshot()
        risk = compute_risk(snap, market_returns=None)
        assert risk.beta is None

    def test_beta_present_when_market_returns_supplied(self) -> None:
        snap = make_snapshot(prices=make_trend_prices(n=260))
        market = [0.001 * ((i % 11) - 5) for i in range(260)]
        risk = compute_risk(snap, market_returns=market)
        assert risk.beta is not None
        assert isinstance(risk.beta, Pct)

    def test_drawdown_detected(self) -> None:
        closes = [100.0] * 50 + [50.0] * 50
        snap = make_snapshot(prices=make_price_series(closes))
        risk = compute_risk(snap)
        assert risk.drawdown is not None
        assert risk.drawdown.value > 0

    def test_does_not_raise_on_partial_data(self) -> None:
        for kwargs in (
            {"omit_fundamentals": True},
            {"omit_prices": True},
            {"fundamentals": make_fundamentals(debt_to_equity=None)},
        ):
            risk = compute_risk(make_snapshot(**kwargs))  # type: ignore[arg-type]
            assert isinstance(risk.composite, Pct)

    def test_quality_concern_high_for_stressed_company(self) -> None:
        bad = make_snapshot(
            fundamentals=make_fundamentals(
                interest_coverage=0.3,
                free_cash_flow=-5_000.0,
                current_ratio=0.5,
            ),
            omit_prices=True,
        )
        good = make_snapshot(
            fundamentals=make_fundamentals(
                interest_coverage=20.0,
                free_cash_flow=20_000.0,
                current_ratio=2.5,
            ),
            omit_prices=True,
        )
        bad_q = compute_risk(bad).quality_concern
        good_q = compute_risk(good).quality_concern
        assert bad_q is not None
        assert good_q is not None
        assert bad_q.value > good_q.value

    def test_default_weights_sum_to_one(self) -> None:
        assert math.isclose(sum(DEFAULT_WEIGHTS.values()), 1.0, abs_tol=1e-9)

    @settings(max_examples=40, deadline=None)
    @given(
        de=st.one_of(st.none(), st.floats(min_value=0.0, max_value=20.0, allow_nan=False)),
        fcf=st.one_of(st.none(), st.floats(min_value=-50_000, max_value=50_000, allow_nan=False)),
        ic=st.one_of(st.none(), st.floats(min_value=-5.0, max_value=50.0, allow_nan=False)),
    )
    def test_property_composite_always_valid(
        self,
        de: float | None,
        fcf: float | None,
        ic: float | None,
    ) -> None:
        snap = make_snapshot(
            fundamentals=make_fundamentals(
                debt_to_equity=de,
                free_cash_flow=fcf,
                interest_coverage=ic,
            ),
        )
        risk = compute_risk(snap)
        assert isinstance(risk.composite, Pct)
        assert 0.0 <= risk.composite.value <= 100.0
