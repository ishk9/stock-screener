"""Tests for RecommendationBuilder."""

from __future__ import annotations

from datetime import datetime

import pytest

from stock_screener.domain.recommendation.builder import RecommendationBuilder
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


def _seed_builder() -> RecommendationBuilder:
    return (
        RecommendationBuilder()
        .with_symbol(Symbol(code="TCS", exchange=Exchange.NSE))
        .with_company_name("Tata Consultancy Services")
        .with_score(Score(72.0))
        .with_conviction(Conviction.HIGH)
        .with_risk_pct(Pct(35.0))
        .with_horizon(Horizon.LONG)
    )


class TestRecommendationBuilder:
    def test_happy_path(self) -> None:
        rec = _seed_builder().build()
        assert rec.symbol.code == "TCS"
        assert rec.company_name == "Tata Consultancy Services"
        assert rec.score.value == 72.0
        assert rec.conviction is Conviction.HIGH
        assert rec.risk_pct.value == 35.0
        assert rec.suggested_horizon is Horizon.LONG

    def test_chaining_returns_self(self) -> None:
        b = RecommendationBuilder()
        assert b.with_company_name("X") is b
        assert b.with_score(Score(50.0)) is b

    def test_optional_fields_round_trip(self) -> None:
        rec = (
            _seed_builder()
            .with_sector("IT")
            .with_market_cap_bucket(MarketCapBucket.LARGE)
            .with_entry_band((100.0, 105.0))
            .with_stop_loss(95.0)
            .with_target(125.0)
            .with_thesis("Solid franchise.")
            .with_key_risks(("currency",))
            .with_catalysts(("deal cycle",))
            .with_citations(("ar2024",))
            .with_data_freshness(datetime(2026, 5, 8))
            .build()
        )
        assert rec.sector == "IT"
        assert rec.entry_band == (100.0, 105.0)
        assert rec.stop_loss == 95.0
        assert rec.target == 125.0
        assert rec.thesis_summary == "Solid franchise."
        assert rec.key_risks == ("currency",)
        assert rec.catalysts == ("deal cycle",)
        assert rec.citations == ("ar2024",)

    def test_immutable_result(self) -> None:
        rec = _seed_builder().build()
        with pytest.raises(Exception):
            rec.thesis_summary = "tampered"  # type: ignore[misc]

    def test_missing_mandatory_raises(self) -> None:
        b = RecommendationBuilder().with_company_name("X")
        with pytest.raises(ValueError) as ei:
            b.build()
        msg = str(ei.value)
        assert "symbol" in msg
        assert "score" in msg
        assert "conviction" in msg
        assert "risk_pct" in msg
        assert "suggested_horizon" in msg

    def test_partial_missing_one_field(self) -> None:
        b = (
            RecommendationBuilder()
            .with_symbol(Symbol(code="T", exchange=Exchange.NSE))
            .with_company_name("T")
            .with_score(Score(50.0))
            .with_conviction(Conviction.MEDIUM)
            .with_risk_pct(Pct(20.0))
        )
        with pytest.raises(ValueError) as ei:
            b.build()
        assert "suggested_horizon" in str(ei.value)
