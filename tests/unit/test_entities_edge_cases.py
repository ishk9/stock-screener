"""Edge-case tests for domain entities (PriceSeries, Recommendation, Snapshot, etc.)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.news import NewsItem
from stock_screener.domain.entities.portfolio_review import PortfolioReview
from stock_screener.domain.entities.position import Position
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.entities.snapshot import CompanySnapshot
from stock_screener.domain.value_objects.action import Action, PortfolioAction
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


def _sym(code: str = "TEST") -> Symbol:
    return Symbol(code=code, exchange=Exchange.NSE)


def _pp(d: date, close: float = 100.0) -> PricePoint:
    return PricePoint(on=d, open=close, high=close + 1, low=close - 1, close=close, volume=1000)


# --------------------------------------------------------------------------- #
# PricePoint
# --------------------------------------------------------------------------- #
class TestPricePoint:
    def test_valid(self) -> None:
        p = _pp(date(2024, 1, 1))
        assert p.close == 100.0

    @pytest.mark.parametrize("field", ["open", "high", "low", "close"])
    def test_zero_or_negative_price_rejected(self, field: str) -> None:
        kwargs = {"on": date(2024, 1, 1), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 0}
        kwargs[field] = 0.0
        with pytest.raises(ValidationError):
            PricePoint(**kwargs)

    def test_negative_volume_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricePoint(
                on=date(2024, 1, 1), open=1.0, high=1.0, low=1.0, close=1.0, volume=-1
            )

    def test_zero_volume_allowed(self) -> None:
        p = PricePoint(on=date(2024, 1, 1), open=1.0, high=1.0, low=1.0, close=1.0, volume=0)
        assert p.volume == 0

    def test_immutable(self) -> None:
        p = _pp(date(2024, 1, 1))
        with pytest.raises(ValidationError):
            p.close = 200.0  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# PriceSeries
# --------------------------------------------------------------------------- #
class TestPriceSeries:
    def test_empty_series(self) -> None:
        ps = PriceSeries(points=())
        assert ps.latest is None
        assert ps.closes() == ()
        assert ps.return_over(sessions=1) is None

    def test_from_points_sorts(self) -> None:
        a = _pp(date(2024, 1, 3))
        b = _pp(date(2024, 1, 1))
        c = _pp(date(2024, 1, 2))
        ps = PriceSeries.from_points([a, b, c])
        assert [p.on for p in ps.points] == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]

    def test_construct_unsorted_raises(self) -> None:
        with pytest.raises(ValidationError):
            PriceSeries(points=(_pp(date(2024, 1, 2)), _pp(date(2024, 1, 1))))

    def test_construct_duplicate_dates_raises(self) -> None:
        with pytest.raises(ValidationError):
            PriceSeries(points=(_pp(date(2024, 1, 1)), _pp(date(2024, 1, 1))))

    def test_latest_returns_last(self) -> None:
        ps = PriceSeries.from_points(
            [_pp(date(2024, 1, 1), 10), _pp(date(2024, 1, 2), 20)]
        )
        assert ps.latest.close == 20

    def test_closes_in_order(self) -> None:
        ps = PriceSeries.from_points(
            [_pp(date(2024, 1, 1), 10), _pp(date(2024, 1, 2), 11)]
        )
        assert ps.closes() == (10.0, 11.0)

    def test_return_over_simple(self) -> None:
        ps = PriceSeries.from_points([
            _pp(date(2024, 1, 1), 100),
            _pp(date(2024, 1, 2), 110),
            _pp(date(2024, 1, 3), 121),
        ])
        # last close 121, two sessions back close = 100 → return = 21%
        assert ps.return_over(sessions=2) == pytest.approx(0.21)

    def test_return_over_too_few_sessions(self) -> None:
        ps = PriceSeries.from_points([_pp(date(2024, 1, 1), 100)])
        assert ps.return_over(sessions=10) is None

    def test_return_over_zero_sessions(self) -> None:
        ps = PriceSeries.from_points([
            _pp(date(2024, 1, 1), 100), _pp(date(2024, 1, 2), 110)
        ])
        assert ps.return_over(sessions=0) is None


# --------------------------------------------------------------------------- #
# Company
# --------------------------------------------------------------------------- #
class TestCompany:
    def test_minimal(self) -> None:
        c = Company(symbol=_sym(), name="Test Co")
        assert c.symbol.code == "TEST"
        assert c.market_cap_inr is None

    def test_negative_market_cap_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Company(symbol=_sym(), name="X", market_cap_inr=-1)

    def test_short_format(self) -> None:
        c = Company(symbol=_sym("RELIANCE"), name="Reliance")
        assert c.short() == "RELIANCE (NSE)"

    def test_immutable(self) -> None:
        c = Company(symbol=_sym(), name="X")
        with pytest.raises(ValidationError):
            c.name = "Y"  # type: ignore[misc]

    def test_with_full_metadata(self) -> None:
        c = Company(
            symbol=_sym("TCS"),
            name="Tata Consultancy",
            isin="INE467B01029",
            sector="IT",
            industry="Software",
            market_cap_inr=14_000_000,
            market_cap_bucket=MarketCapBucket.LARGE,
            market_cap_rank=2,
        )
        assert c.market_cap_bucket is MarketCapBucket.LARGE


# --------------------------------------------------------------------------- #
# Fundamentals
# --------------------------------------------------------------------------- #
class TestFundamentals:
    def test_minimal(self) -> None:
        f = Fundamentals(as_of=date(2024, 1, 1))
        assert f.revenue is None and f.pe is None

    def test_negative_revenue_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Fundamentals(as_of=date(2024, 1, 1), revenue=-1)

    def test_negative_total_debt_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Fundamentals(as_of=date(2024, 1, 1), total_debt=-1)

    def test_negative_dividend_yield_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Fundamentals(as_of=date(2024, 1, 1), dividend_yield=-0.5)

    def test_negative_eps_allowed(self) -> None:
        f = Fundamentals(as_of=date(2024, 1, 1), eps=-2.5)
        assert f.eps == -2.5


# --------------------------------------------------------------------------- #
# CompanySnapshot
# --------------------------------------------------------------------------- #
class TestCompanySnapshot:
    def test_has_minimum_data_false_when_empty(self) -> None:
        snap = CompanySnapshot(company=Company(symbol=_sym(), name="X"))
        assert snap.has_minimum_data is False

    def test_has_minimum_data_true_when_both(self) -> None:
        snap = CompanySnapshot(
            company=Company(symbol=_sym(), name="X"),
            fundamentals=Fundamentals(as_of=date(2024, 1, 1), pe=15),
            prices=PriceSeries.from_points([_pp(date(2024, 1, 1))]),
        )
        assert snap.has_minimum_data is True

    def test_has_minimum_data_false_when_only_fundamentals(self) -> None:
        snap = CompanySnapshot(
            company=Company(symbol=_sym(), name="X"),
            fundamentals=Fundamentals(as_of=date(2024, 1, 1)),
        )
        assert snap.has_minimum_data is False

    def test_default_news_empty(self) -> None:
        snap = CompanySnapshot(company=Company(symbol=_sym(), name="X"))
        assert snap.news == ()

    def test_fetched_at_is_utc(self) -> None:
        snap = CompanySnapshot(company=Company(symbol=_sym(), name="X"))
        assert snap.fetched_at.tzinfo is not None


# --------------------------------------------------------------------------- #
# Recommendation
# --------------------------------------------------------------------------- #
class TestRecommendation:
    def _build(self, **overrides) -> Recommendation:
        defaults = {
            "symbol": _sym(),
            "company_name": "Test",
            "score": Score(70),
            "conviction": Conviction.MEDIUM,
            "risk_pct": Pct(40),
            "suggested_horizon": Horizon.LONG,
            "action": Action.BUY,
            "data_freshness": datetime.now(timezone.utc),
        }
        defaults.update(overrides)
        return Recommendation(**defaults)

    def test_minimal(self) -> None:
        rec = self._build()
        assert rec.score.value == 70
        assert rec.action is Action.BUY

    def test_action_default_is_wait(self) -> None:
        rec = Recommendation(
            symbol=_sym(),
            company_name="x",
            score=Score(50),
            conviction=Conviction.MEDIUM,
            risk_pct=Pct(50),
            suggested_horizon=Horizon.LONG,
        )
        assert rec.action is Action.WAIT

    def test_immutable(self) -> None:
        rec = self._build()
        with pytest.raises(ValidationError):
            rec.score = Score(80)  # type: ignore[misc]

    def test_target_optional(self) -> None:
        rec = self._build()
        assert rec.target is None
        assert rec.entry_band is None
        assert rec.stop_loss is None

    def test_explicit_levels(self) -> None:
        rec = self._build(entry_band=(98.0, 102.0), stop_loss=92.0, target=120.0)
        assert rec.target == 120.0


# --------------------------------------------------------------------------- #
# NewsItem
# --------------------------------------------------------------------------- #
class TestNewsItem:
    def test_minimal(self) -> None:
        n = NewsItem(
            headline="x", source="y",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert n.url is None
        assert n.summary is None

    def test_immutable(self) -> None:
        n = NewsItem(
            headline="x", source="y",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(ValidationError):
            n.headline = "y"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# PortfolioReview
# --------------------------------------------------------------------------- #
class TestPortfolioReview:
    def test_minimal(self) -> None:
        pos = Position(symbol=_sym(), avg_buy_price=100, quantity=10)
        pr = PortfolioReview(position=pos, current_price=110.0)
        assert pr.action is PortfolioAction.HOLD
        assert pr.recommendation is None
        assert pr.rationale == ""

    def test_with_rationale(self) -> None:
        pos = Position(symbol=_sym(), avg_buy_price=100, quantity=10)
        pr = PortfolioReview(
            position=pos, current_price=150,
            unrealised_pnl_abs=500.0, unrealised_pnl_pct=50.0,
            action=PortfolioAction.TRIM,
            rationale="Booked partial profit.",
        )
        assert pr.action is PortfolioAction.TRIM
        assert "profit" in pr.rationale

    def test_immutable(self) -> None:
        pos = Position(symbol=_sym(), avg_buy_price=100, quantity=10)
        pr = PortfolioReview(position=pos, current_price=110.0)
        with pytest.raises(ValidationError):
            pr.action = PortfolioAction.EXIT  # type: ignore[misc]
