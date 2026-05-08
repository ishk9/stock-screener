"""Tests for analytics.ratios."""

from __future__ import annotations

from datetime import date

import pytest

from stock_screener.domain.analytics.ratios import compute_derived_ratios, safe_div
from stock_screener.domain.entities.fundamentals import Fundamentals


# --------------------------------------------------------------------------- #
# safe_div
# --------------------------------------------------------------------------- #
class TestSafeDiv:
    def test_normal(self) -> None:
        assert safe_div(10.0, 2.0) == 5.0

    def test_zero_denominator(self) -> None:
        assert safe_div(10.0, 0.0) is None

    def test_negative_denominator(self) -> None:
        assert safe_div(10.0, -2.0) is None

    def test_none_numerator(self) -> None:
        assert safe_div(None, 5.0) is None

    def test_none_denominator(self) -> None:
        assert safe_div(5.0, None) is None

    def test_both_none(self) -> None:
        assert safe_div(None, None) is None

    def test_zero_numerator(self) -> None:
        assert safe_div(0.0, 5.0) == 0.0


# --------------------------------------------------------------------------- #
# compute_derived_ratios
# --------------------------------------------------------------------------- #
class TestComputeDerivedRatios:
    def _make(self, **overrides: object) -> Fundamentals:
        base: dict[str, object] = dict(
            as_of=date(2026, 1, 1),
            revenue=100_000.0,
            operating_profit=20_000.0,
            net_profit=15_000.0,
            eps=25.0,
            total_assets=200_000.0,
            total_equity=80_000.0,
            total_debt=40_000.0,
            cash=10_000.0,
            shares_outstanding=1_000.0,
            free_cash_flow=12_000.0,
        )
        base.update(overrides)
        return Fundamentals(**base)  # type: ignore[arg-type]

    def test_happy_path_fills_pe_pb_de_margins(self) -> None:
        f = self._make()
        out = compute_derived_ratios(f, latest_price=500.0)

        assert out.pe == pytest.approx(20.0)
        assert out.pb == pytest.approx(500.0 * 1000.0 / 80_000.0)
        assert out.debt_to_equity == pytest.approx(0.5)
        assert out.roe == pytest.approx(15_000.0 / 80_000.0 * 100.0)
        assert out.gross_margin == pytest.approx(20.0)
        assert out.operating_margin == pytest.approx(20.0)
        assert out.net_margin == pytest.approx(15.0)

    def test_returns_new_instance(self) -> None:
        f = self._make()
        out = compute_derived_ratios(f, latest_price=500.0)
        assert out is not f

    def test_does_not_overwrite_existing_values(self) -> None:
        f = self._make(pe=99.0, debt_to_equity=2.5, gross_margin=42.0)
        out = compute_derived_ratios(f, latest_price=500.0)
        assert out.pe == 99.0
        assert out.debt_to_equity == 2.5
        assert out.gross_margin == 42.0
        assert out.net_margin == pytest.approx(15.0)

    def test_missing_price_skips_pe_pb(self) -> None:
        f = self._make()
        out = compute_derived_ratios(f, latest_price=None)
        assert out.pe is None
        assert out.pb is None
        assert out.roe is not None
        assert out.debt_to_equity is not None

    def test_zero_eps_yields_none_pe(self) -> None:
        f = self._make(eps=0.0)
        out = compute_derived_ratios(f, latest_price=500.0)
        assert out.pe is None

    def test_zero_equity_yields_none_de_and_pb(self) -> None:
        f = self._make(total_equity=0.0)
        out = compute_derived_ratios(f, latest_price=500.0)
        assert out.debt_to_equity is None
        assert out.pb is None
        assert out.roe is None

    def test_no_fundamentals_means_all_none(self) -> None:
        f = Fundamentals(as_of=date(2026, 1, 1))
        out = compute_derived_ratios(f, latest_price=None)
        assert out.pe is None
        assert out.pb is None
        assert out.debt_to_equity is None
        assert out.roe is None
        assert out.roce is None
        assert out.gross_margin is None
        assert out.operating_margin is None
        assert out.net_margin is None
        assert out.interest_coverage is None

    def test_interest_coverage_when_op_eq_net_returns_none(self) -> None:
        f = self._make(net_profit=20_000.0)
        out = compute_derived_ratios(f, latest_price=None)
        assert out.interest_coverage is None

    def test_interest_coverage_positive_implied_interest(self) -> None:
        f = self._make(operating_profit=10_000.0, net_profit=8_000.0)
        out = compute_derived_ratios(f, latest_price=None)
        assert out.interest_coverage == pytest.approx(10_000.0 / 2_000.0)

    def test_roce_uses_assets_minus_cash(self) -> None:
        f = self._make()
        out = compute_derived_ratios(f, latest_price=None)
        assert out.roce == pytest.approx(20_000.0 / (200_000.0 - 10_000.0) * 100.0)

    def test_roce_falls_back_to_equity_plus_debt(self) -> None:
        f = self._make(total_assets=None)
        out = compute_derived_ratios(f, latest_price=None)
        assert out.roce == pytest.approx(20_000.0 / (80_000.0 + 40_000.0) * 100.0)

    def test_negative_price_yields_none_pe_pb(self) -> None:
        f = self._make()
        out = compute_derived_ratios(f, latest_price=-1.0)
        assert out.pe is None
        assert out.pb is None
