"""Tests for analytics.normalize + analytics.strategies."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from stock_screener.domain.analytics.normalize import min_max, rank_pct, winsorize
from stock_screener.domain.analytics.strategies import (
    CompositeScoringStrategy,
    GrowthScoringStrategy,
    MomentumScoringStrategy,
    QualityScoringStrategy,
    ScoringStrategy,
    ValueScoringStrategy,
)
from stock_screener.domain.analytics.strategies.composite import make_default
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.score import Score

from .conftest import (
    make_fundamentals,
    make_price_series,
    make_snapshot,
    make_trend_prices,
)


# --------------------------------------------------------------------------- #
# normalize.min_max
# --------------------------------------------------------------------------- #
class TestMinMax:
    def test_basic_scaling(self) -> None:
        out = min_max([0.0, 5.0, 10.0])
        assert out == [0.0, 0.5, 1.0]

    def test_none_passthrough(self) -> None:
        out = min_max([None, 1.0, 2.0, None, 3.0])
        assert out[0] is None and out[3] is None
        assert out[1] == 0.0
        assert out[4] == 1.0

    def test_all_equal_returns_neutral(self) -> None:
        assert min_max([3.0, 3.0, 3.0]) == [0.5, 0.5, 0.5]

    def test_all_none(self) -> None:
        assert min_max([None, None]) == [None, None]

    def test_single_value(self) -> None:
        assert min_max([7.0]) == [0.5]

    @settings(max_examples=80, deadline=None)
    @given(
        st.lists(
            st.one_of(st.none(), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
            min_size=0,
            max_size=20,
        )
    )
    def test_property_bounded_in_unit_interval(self, values: list[float | None]) -> None:
        out = min_max(values)
        for v in out:
            if v is None:
                continue
            assert 0.0 <= v <= 1.0


# --------------------------------------------------------------------------- #
# normalize.rank_pct + winsorize
# --------------------------------------------------------------------------- #
class TestRankPctAndWinsorize:
    def test_rank_pct_higher_is_better(self) -> None:
        out = rank_pct([1.0, 2.0, 3.0, 4.0])
        assert out == [0.0, pytest.approx(1 / 3), pytest.approx(2 / 3), 1.0]

    def test_rank_pct_lower_is_better(self) -> None:
        out = rank_pct([1.0, 2.0, 3.0, 4.0], higher_is_better=False)
        assert out == [1.0, pytest.approx(2 / 3), pytest.approx(1 / 3), 0.0]

    def test_rank_pct_handles_ties(self) -> None:
        out = rank_pct([2.0, 2.0, 4.0])
        assert out[0] == out[1]
        assert out[2] == 1.0

    def test_rank_pct_none_passthrough(self) -> None:
        out = rank_pct([None, 1.0, 2.0])
        assert out[0] is None
        assert out[1] == 0.0
        assert out[2] == 1.0

    def test_winsorize_clips_extremes(self) -> None:
        values = [-50.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 100.0]
        out = winsorize(values, lower=0.05, upper=0.95)
        assert out[0] is not None and out[0] > -50.0
        assert out[-1] is not None and out[-1] < 100.0

    def test_winsorize_passes_none_through(self) -> None:
        out = winsorize([None, 1.0, 2.0, None, 3.0])
        assert out[0] is None
        assert out[3] is None

    def test_winsorize_invalid_bounds(self) -> None:
        with pytest.raises(ValueError):
            winsorize([1.0, 2.0], lower=0.9, upper=0.1)


# --------------------------------------------------------------------------- #
# Strategy contracts
# --------------------------------------------------------------------------- #
class TestStrategyContract:
    @pytest.mark.parametrize(
        "strategy",
        [
            ValueScoringStrategy(),
            GrowthScoringStrategy(),
            QualityScoringStrategy(),
            MomentumScoringStrategy(),
        ],
    )
    def test_satisfies_protocol(self, strategy: ScoringStrategy) -> None:
        assert isinstance(strategy, ScoringStrategy)
        assert isinstance(strategy.name, str) and strategy.name

    @pytest.mark.parametrize(
        "strategy",
        [
            ValueScoringStrategy(),
            GrowthScoringStrategy(),
            QualityScoringStrategy(),
            MomentumScoringStrategy(),
        ],
    )
    def test_returns_score_in_range(self, strategy: ScoringStrategy) -> None:
        snap = make_snapshot()
        s = strategy.score(snap, Horizon.MID)
        assert isinstance(s, Score)
        assert 0.0 <= s.value <= 100.0

    @pytest.mark.parametrize(
        "strategy",
        [
            ValueScoringStrategy(),
            GrowthScoringStrategy(),
            QualityScoringStrategy(),
            MomentumScoringStrategy(),
        ],
    )
    def test_neutral_on_missing_data(self, strategy: ScoringStrategy) -> None:
        snap = make_snapshot(omit_fundamentals=True, omit_prices=True)
        s = strategy.score(snap, Horizon.MID)
        assert s.value == pytest.approx(50.0)


# --------------------------------------------------------------------------- #
# Value strategy
# --------------------------------------------------------------------------- #
class TestValueStrategy:
    def test_low_pe_scores_high(self) -> None:
        cheap = make_snapshot(fundamentals=make_fundamentals(pe=8.0, pb=1.0, ev_ebitda=5.0))
        expensive = make_snapshot(fundamentals=make_fundamentals(pe=50.0, pb=10.0, ev_ebitda=30.0))
        s = ValueScoringStrategy()
        assert s.score(cheap, Horizon.MID).value > s.score(expensive, Horizon.MID).value

    def test_dividend_yield_bumps_when_no_other_signal(self) -> None:
        snap = make_snapshot(
            fundamentals=make_fundamentals(
                pe=None, pb=None, ev_ebitda=None, dividend_yield=4.0
            )
        )
        out = ValueScoringStrategy().score(snap, Horizon.MID)
        assert out.value > 50.0

    def test_dividend_yield_bumps_existing_signal(self) -> None:
        no_div = make_snapshot(
            fundamentals=make_fundamentals(pe=15.0, pb=2.0, dividend_yield=0.0)
        )
        with_div = make_snapshot(
            fundamentals=make_fundamentals(pe=15.0, pb=2.0, dividend_yield=4.0)
        )
        s = ValueScoringStrategy()
        assert s.score(with_div, Horizon.MID).value >= s.score(no_div, Horizon.MID).value


# --------------------------------------------------------------------------- #
# Growth strategy
# --------------------------------------------------------------------------- #
class TestGrowthStrategy:
    def test_high_growth_scores_high(self) -> None:
        boom = make_snapshot(
            fundamentals=make_fundamentals(
                revenue_cagr_3y=40.0, eps_cagr_3y=45.0, profit_growth_yoy=50.0
            )
        )
        flat = make_snapshot(
            fundamentals=make_fundamentals(
                revenue_cagr_3y=0.0, eps_cagr_3y=0.0, profit_growth_yoy=-5.0
            )
        )
        s = GrowthScoringStrategy()
        assert s.score(boom, Horizon.MID).value > s.score(flat, Horizon.MID).value

    def test_negative_growth_pulls_score_low(self) -> None:
        bad = make_snapshot(
            fundamentals=make_fundamentals(
                revenue_cagr_3y=-10.0, eps_cagr_3y=-15.0, profit_growth_yoy=-30.0
            )
        )
        s = GrowthScoringStrategy()
        out = s.score(bad, Horizon.MID)
        assert out.value <= 25.0


# --------------------------------------------------------------------------- #
# Quality strategy
# --------------------------------------------------------------------------- #
class TestQualityStrategy:
    def test_high_roe_low_de_scores_high(self) -> None:
        good = make_snapshot(
            fundamentals=make_fundamentals(
                roe=28.0, roce=24.0, debt_to_equity=0.1, interest_coverage=14.0,
                free_cash_flow=14_000.0,
            )
        )
        weak = make_snapshot(
            fundamentals=make_fundamentals(
                roe=4.0, roce=3.0, debt_to_equity=2.5, interest_coverage=0.5,
                free_cash_flow=-2_000.0,
            )
        )
        s = QualityScoringStrategy()
        assert s.score(good, Horizon.MID).value > s.score(weak, Horizon.MID).value

    def test_partial_data_still_scores(self) -> None:
        snap = make_snapshot(fundamentals=make_fundamentals(roe=20.0))
        out = QualityScoringStrategy().score(snap, Horizon.MID)
        assert 0.0 <= out.value <= 100.0


# --------------------------------------------------------------------------- #
# Momentum strategy
# --------------------------------------------------------------------------- #
class TestMomentumStrategy:
    def test_uptrend_scores_higher_than_downtrend(self) -> None:
        up = make_snapshot(prices=make_trend_prices(n=260, drift=0.002))
        down = make_snapshot(prices=make_trend_prices(n=260, drift=-0.002))
        s = MomentumScoringStrategy()
        assert s.score(up, Horizon.MID).value > s.score(down, Horizon.MID).value

    def test_no_prices_neutral(self) -> None:
        snap = make_snapshot(omit_prices=True)
        out = MomentumScoringStrategy().score(snap, Horizon.MID)
        assert out.value == pytest.approx(50.0)

    def test_short_history_uses_only_short_windows(self) -> None:
        snap = make_snapshot(prices=make_price_series([100.0 + i for i in range(40)]))
        out = MomentumScoringStrategy().score(snap, Horizon.MID)
        assert 0.0 <= out.value <= 100.0


# --------------------------------------------------------------------------- #
# Composite strategy
# --------------------------------------------------------------------------- #
class TestCompositeStrategy:
    def test_make_default_known_keys(self) -> None:
        comp = CompositeScoringStrategy.make_default(
            {"value": 0.3, "growth": 0.3, "quality": 0.3, "momentum": 0.1}
        )
        assert isinstance(comp, CompositeScoringStrategy)
        assert comp.name == "composite"

    def test_make_default_rejects_unknown(self) -> None:
        with pytest.raises(ValueError):
            CompositeScoringStrategy.make_default({"alpha": 0.5})

    def test_make_default_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            CompositeScoringStrategy.make_default({})

    def test_module_level_make_default(self) -> None:
        comp = make_default({"value": 1.0})
        assert isinstance(comp, CompositeScoringStrategy)

    def test_weights_renormalised(self) -> None:
        snap = make_snapshot()
        a = CompositeScoringStrategy.make_default({"value": 1.0, "growth": 1.0})
        b = CompositeScoringStrategy.make_default({"value": 5.0, "growth": 5.0})
        assert a.score(snap, Horizon.MID).value == pytest.approx(
            b.score(snap, Horizon.MID).value
        )

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError):
            CompositeScoringStrategy(parts=((ValueScoringStrategy(), -1.0),))

    def test_all_zero_weights_rejected(self) -> None:
        with pytest.raises(ValueError):
            CompositeScoringStrategy(
                parts=((ValueScoringStrategy(), 0.0), (GrowthScoringStrategy(), 0.0))
            )

    def test_empty_parts_rejected(self) -> None:
        with pytest.raises(ValueError):
            CompositeScoringStrategy(parts=())

    @settings(max_examples=30, deadline=None)
    @given(
        wv=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
        wg=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
        wq=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
        wm=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    )
    def test_property_score_always_valid(
        self, wv: float, wg: float, wq: float, wm: float
    ) -> None:
        if wv + wg + wq + wm <= 0:
            return
        comp = CompositeScoringStrategy.make_default(
            {"value": wv, "growth": wg, "quality": wq, "momentum": wm}
        )
        snap = make_snapshot()
        s = comp.score(snap, Horizon.MID)
        assert isinstance(s, Score)
        assert 0.0 <= s.value <= 100.0
