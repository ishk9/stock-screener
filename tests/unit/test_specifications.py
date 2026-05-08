"""Tests for the Specification combinators and concrete specs."""

from __future__ import annotations

from datetime import datetime

from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.recommendation.policy import apply_specifications, rank_top
from stock_screener.domain.specifications import (
    HasMinimumDataSpec,
    MarketCapSpec,
    MaxRiskSpec,
    MinScoreSpec,
    SectorBlacklistSpec,
    SectorWhitelistSpec,
    Specification,
)
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol

from .conftest import make_company, make_snapshot


def _rec(
    code: str,
    score: float,
    risk: float,
    *,
    sector: str = "IT",
    bucket: MarketCapBucket = MarketCapBucket.LARGE,
) -> Recommendation:
    return Recommendation(
        symbol=Symbol(code=code, exchange=Exchange.NSE),
        company_name=code,
        sector=sector,
        market_cap_bucket=bucket,
        score=Score(score),
        conviction=Conviction.MEDIUM,
        risk_pct=Pct(risk),
        suggested_horizon=Horizon.MID,
        data_freshness=datetime(2026, 1, 1),
    )


# --------------------------------------------------------------------------- #
# Combinators
# --------------------------------------------------------------------------- #
class _Always(Specification[int]):
    def is_satisfied_by(self, candidate: int) -> bool:  # noqa: ARG002
        return True


class _Never(Specification[int]):
    def is_satisfied_by(self, candidate: int) -> bool:  # noqa: ARG002
        return False


class TestCombinators:
    def test_and_short_circuits(self) -> None:
        spec = _Always() & _Never()
        assert spec.is_satisfied_by(1) is False

    def test_and_both_pass(self) -> None:
        spec = _Always() & _Always()
        assert spec.is_satisfied_by(1) is True

    def test_or_either(self) -> None:
        spec = _Always() | _Never()
        assert spec.is_satisfied_by(1) is True

    def test_or_both_fail(self) -> None:
        spec = _Never() | _Never()
        assert spec.is_satisfied_by(1) is False

    def test_not_inverts(self) -> None:
        spec = ~_Always()
        assert spec.is_satisfied_by(1) is False
        spec2 = ~_Never()
        assert spec2.is_satisfied_by(1) is True

    def test_complex_expression(self) -> None:
        spec = (_Always() & _Never()) | _Always()
        assert spec.is_satisfied_by(1) is True


# --------------------------------------------------------------------------- #
# Concrete specs
# --------------------------------------------------------------------------- #
class TestConcreteSpecs:
    def test_market_cap_spec(self) -> None:
        large = make_snapshot(company=make_company(bucket=MarketCapBucket.LARGE))
        small = make_snapshot(company=make_company(bucket=MarketCapBucket.SMALL))
        spec = MarketCapSpec(MarketCapBucket.LARGE)
        assert spec.is_satisfied_by(large)
        assert not spec.is_satisfied_by(small)

    def test_sector_whitelist_empty_passes_all(self) -> None:
        snap = make_snapshot(company=make_company(sector="IT"))
        spec = SectorWhitelistSpec.of([])
        assert spec.is_satisfied_by(snap)

    def test_sector_whitelist_match_case_insensitive(self) -> None:
        snap = make_snapshot(company=make_company(sector="IT"))
        spec = SectorWhitelistSpec.of(["it", "Pharma"])
        assert spec.is_satisfied_by(snap)

    def test_sector_whitelist_miss(self) -> None:
        snap = make_snapshot(company=make_company(sector="Energy"))
        spec = SectorWhitelistSpec.of(["IT"])
        assert not spec.is_satisfied_by(snap)

    def test_sector_blacklist_empty_passes(self) -> None:
        snap = make_snapshot(company=make_company(sector="Tobacco"))
        spec = SectorBlacklistSpec.of([])
        assert spec.is_satisfied_by(snap)

    def test_sector_blacklist_blocks(self) -> None:
        snap = make_snapshot(company=make_company(sector="Tobacco"))
        spec = SectorBlacklistSpec.of(["Tobacco"])
        assert not spec.is_satisfied_by(snap)

    def test_has_minimum_data_true(self) -> None:
        assert HasMinimumDataSpec().is_satisfied_by(make_snapshot())

    def test_has_minimum_data_false_no_fundamentals(self) -> None:
        snap = make_snapshot(omit_fundamentals=True)
        assert not HasMinimumDataSpec().is_satisfied_by(snap)

    def test_has_minimum_data_false_no_prices(self) -> None:
        snap = make_snapshot(omit_prices=True)
        assert not HasMinimumDataSpec().is_satisfied_by(snap)

    def test_max_risk_spec(self) -> None:
        spec = MaxRiskSpec(Pct(40.0))
        assert spec.is_satisfied_by(_rec("A", 50.0, 30.0))
        assert spec.is_satisfied_by(_rec("A", 50.0, 40.0))
        assert not spec.is_satisfied_by(_rec("A", 50.0, 50.0))

    def test_min_score_spec(self) -> None:
        spec = MinScoreSpec(60.0)
        assert spec.is_satisfied_by(_rec("A", 70.0, 30.0))
        assert spec.is_satisfied_by(_rec("A", 60.0, 30.0))
        assert not spec.is_satisfied_by(_rec("A", 50.0, 30.0))


# --------------------------------------------------------------------------- #
# Policy helpers
# --------------------------------------------------------------------------- #
class TestPolicy:
    def test_apply_specifications_filters(self) -> None:
        snaps = [
            make_snapshot(company=make_company(code="A", sector="IT")),
            make_snapshot(company=make_company(code="B", sector="Energy")),
        ]
        spec = SectorWhitelistSpec.of(["IT"])
        out = apply_specifications(snaps, spec)
        assert len(out) == 1
        assert out[0].company.symbol.code == "A"

    def test_rank_top_orders_by_score_desc(self) -> None:
        recs = [_rec("A", 60.0, 20.0), _rec("B", 90.0, 30.0), _rec("C", 75.0, 10.0)]
        out = rank_top(recs, k=2)
        assert [r.company_name for r in out] == ["B", "C"]

    def test_rank_top_tiebreaks_by_lower_risk(self) -> None:
        recs = [_rec("A", 80.0, 50.0), _rec("B", 80.0, 20.0)]
        out = rank_top(recs, k=2)
        assert [r.company_name for r in out] == ["B", "A"]

    def test_rank_top_zero_k(self) -> None:
        recs = [_rec("A", 80.0, 50.0)]
        assert rank_top(recs, k=0) == []

    def test_rank_top_k_larger_than_input(self) -> None:
        recs = [_rec("A", 80.0, 50.0)]
        out = rank_top(recs, k=10)
        assert len(out) == 1

    def test_combined_specs_filter_recommendations(self) -> None:
        recs = [
            _rec("A", 80.0, 30.0),
            _rec("B", 50.0, 20.0),
            _rec("C", 90.0, 60.0),
        ]
        spec = MinScoreSpec(60.0) & MaxRiskSpec(Pct(40.0))
        out = apply_specifications(recs, spec)
        assert [r.company_name for r in out] == ["A"]
