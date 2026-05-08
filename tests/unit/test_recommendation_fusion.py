"""Tests for RecommendationFusionService and LLMAnalystOutput."""

from __future__ import annotations

import pytest

from stock_screener.domain.analytics.risk import compute_risk
from stock_screener.domain.recommendation.fusion import (
    LLMAnalystOutput,
    RecommendationFusionService,
)
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score

from .conftest import make_snapshot


class TestLLMAnalystOutput:
    def test_round_trip(self) -> None:
        out = LLMAnalystOutput(
            thesis_summary="ok",
            qualitative_risk=Pct(30.0),
            confidence=0.8,
        )
        assert out.confidence == 0.8
        assert out.suggested_horizon is None
        assert out.key_risks == ()
        assert out.catalysts == ()

    def test_invalid_confidence(self) -> None:
        with pytest.raises(ValueError):
            LLMAnalystOutput(
                thesis_summary="x",
                qualitative_risk=Pct(0.0),
                confidence=1.5,
            )

    def test_immutable(self) -> None:
        out = LLMAnalystOutput(
            thesis_summary="x",
            qualitative_risk=Pct(0.0),
            confidence=0.5,
        )
        with pytest.raises(Exception):
            out.thesis_summary = "y"  # type: ignore[misc]


class TestFuse:
    def setup_method(self) -> None:
        self.svc = RecommendationFusionService()
        self.snapshot = make_snapshot()
        self.risk = compute_risk(self.snapshot)

    def test_without_llm_uses_risk_composite_directly(self) -> None:
        rec = self.svc.fuse(
            self.snapshot,
            Score(80.0),
            None,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        assert rec.risk_pct.value == pytest.approx(self.risk.composite.value)
        assert rec.thesis_summary.startswith("Quantitative")
        assert rec.key_risks == ()
        assert rec.catalysts == ()

    def test_with_llm_blends_risk_60_40(self) -> None:
        llm = LLMAnalystOutput(
            thesis_summary="LLM thesis",
            key_risks=("regulation",),
            catalysts=("new product",),
            qualitative_risk=Pct(80.0),
            confidence=0.9,
        )
        rec = self.svc.fuse(
            self.snapshot,
            Score(70.0),
            llm,
            self.risk,
            Horizon.MID,
            scoring_profile="composite",
        )
        expected = self.risk.composite.value * 0.6 + 80.0 * 0.4
        assert rec.risk_pct.value == pytest.approx(expected, abs=0.01)
        assert rec.thesis_summary == "LLM thesis"
        assert rec.key_risks == ("regulation",)
        assert rec.catalysts == ("new product",)

    def test_conviction_high_score_high(self) -> None:
        rec = self.svc.fuse(
            self.snapshot,
            Score(90.0),
            None,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        assert rec.conviction is Conviction.HIGH

    def test_low_confidence_downgrades_high_to_medium(self) -> None:
        llm = LLMAnalystOutput(
            thesis_summary="ok",
            qualitative_risk=Pct(30.0),
            confidence=0.3,
        )
        rec = self.svc.fuse(
            self.snapshot,
            Score(85.0),
            llm,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        assert rec.conviction is Conviction.MEDIUM

    def test_low_confidence_downgrades_medium_to_low(self) -> None:
        llm = LLMAnalystOutput(
            thesis_summary="ok",
            qualitative_risk=Pct(30.0),
            confidence=0.2,
        )
        rec = self.svc.fuse(
            self.snapshot,
            Score(60.0),
            llm,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        assert rec.conviction is Conviction.LOW

    def test_high_confidence_keeps_conviction(self) -> None:
        llm = LLMAnalystOutput(
            thesis_summary="ok",
            qualitative_risk=Pct(30.0),
            confidence=0.9,
        )
        rec = self.svc.fuse(
            self.snapshot,
            Score(85.0),
            llm,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        assert rec.conviction is Conviction.HIGH

    def test_low_score_low_confidence_stays_low(self) -> None:
        llm = LLMAnalystOutput(
            thesis_summary="ok",
            qualitative_risk=Pct(30.0),
            confidence=0.2,
        )
        rec = self.svc.fuse(
            self.snapshot,
            Score(20.0),
            llm,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        assert rec.conviction is Conviction.LOW

    def test_trade_levels_long_horizon(self) -> None:
        rec = self.svc.fuse(
            self.snapshot,
            Score(70.0),
            None,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        last = self.snapshot.prices.latest.close  # type: ignore[union-attr]
        assert rec.entry_band is not None
        lo, hi = rec.entry_band
        assert lo < last < hi
        assert rec.target is not None and rec.target > last
        assert rec.stop_loss is not None and rec.stop_loss < last

    def test_trade_levels_short_smaller_than_long(self) -> None:
        long_rec = self.svc.fuse(
            self.snapshot,
            Score(70.0),
            None,
            self.risk,
            Horizon.LONG,
            scoring_profile="composite",
        )
        short_rec = self.svc.fuse(
            self.snapshot,
            Score(70.0),
            None,
            self.risk,
            Horizon.SHORT,
            scoring_profile="composite",
        )
        assert short_rec.target is not None
        assert long_rec.target is not None
        assert short_rec.target < long_rec.target

    def test_no_prices_no_trade_levels(self) -> None:
        snap = make_snapshot(omit_prices=True)
        rec = self.svc.fuse(
            snap,
            Score(60.0),
            None,
            self.risk,
            Horizon.LONG,
            scoring_profile="value",
        )
        assert rec.entry_band is None
        assert rec.target is None
        assert rec.stop_loss is None
