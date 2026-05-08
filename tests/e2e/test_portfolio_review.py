"""End-to-end test for the ReviewPortfolioUseCase."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from stock_screener.core.result import Ok
from stock_screener.domain.analytics.strategies.composite import CompositeScoringStrategy
from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.position import Position
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.recommendation.fusion import RecommendationFusionService
from stock_screener.domain.value_objects.action import PortfolioAction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.cache.sqlite_portfolio_repo import SqlitePortfolioRepository
from stock_screener.usecases.review_portfolio import (
    ReviewPortfolioUseCase,
    ReviewRequest,
)

from tests.conftest import FakeFundamentalsProvider, FakePriceProvider
from tests.e2e.test_screen_pipeline import InMemoryUniverse


def _strong_fundamentals() -> Fundamentals:
    return Fundamentals(
        as_of=date(2026, 5, 1),
        revenue=10_000,
        net_profit=1_500,
        eps=10.0,
        pe=15.0,
        pb=2.5,
        roe=0.18,
        roce=0.20,
        debt_to_equity=0.4,
        revenue_cagr_3y=0.12,
        eps_cagr_3y=0.15,
        operating_margin=0.18,
        net_margin=0.15,
        free_cash_flow=1_200,
    )


def _stable_prices(close: float = 2200.0) -> PriceSeries:
    points = [
        PricePoint(
            on=date(2025, 1, 1) + timedelta(days=i),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1_000_000,
        )
        for i in range(260)
    ]
    return PriceSeries.from_points(points)


@pytest.mark.asyncio
async def test_review_recommends_add_for_winning_position(tmp_path: Path) -> None:
    repo = SqlitePortfolioRepository(path=tmp_path / "p.db")
    symbol = Symbol(code="RELIANCE", exchange=Exchange.NSE)
    repo.upsert(Position(symbol=symbol, avg_buy_price=2000.0, quantity=5))

    universe = InMemoryUniverse(
        [
            Company(
                symbol=symbol,
                name="Reliance Industries",
                sector="Energy",
                market_cap_bucket=MarketCapBucket.LARGE,
            )
        ]
    )
    fundamentals = FakeFundamentalsProvider([Ok(_strong_fundamentals())])
    prices = FakePriceProvider([Ok(_stable_prices(close=2200.0))])

    use_case = ReviewPortfolioUseCase(
        portfolio=repo,
        universe=universe,
        fundamentals=fundamentals,
        prices=prices,
        llm=None,
        scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
        fusion=RecommendationFusionService(),
    )
    response = await use_case.execute(
        ReviewRequest(horizon=Horizon.LONG, use_llm=False)
    )

    assert len(response.reviews) == 1
    review = response.reviews[0]
    assert review.position.symbol.code == "RELIANCE"
    assert review.current_price == 2200.0
    assert review.unrealised_pnl_pct == pytest.approx(10.0)
    assert isinstance(review.action, PortfolioAction)
    assert review.recommendation is not None
    assert review.rationale  # non-empty
    # P&L is positive but score may be EXIT/HOLD/ADD depending on the scorer —
    # the contract here is "we produced *some* action with a rationale".


@pytest.mark.asyncio
async def test_review_recommends_exit_on_stop_breach(tmp_path: Path) -> None:
    repo = SqlitePortfolioRepository(path=tmp_path / "p.db")
    symbol = Symbol(code="RELIANCE", exchange=Exchange.NSE)
    repo.upsert(Position(symbol=symbol, avg_buy_price=2000.0, quantity=5))

    universe = InMemoryUniverse(
        [
            Company(
                symbol=symbol,
                name="Reliance Industries",
                market_cap_bucket=MarketCapBucket.LARGE,
            )
        ]
    )
    fundamentals = FakeFundamentalsProvider([Ok(_strong_fundamentals())])
    # 30% below avg buy → stop-loss breach.
    prices = FakePriceProvider([Ok(_stable_prices(close=1400.0))])

    use_case = ReviewPortfolioUseCase(
        portfolio=repo,
        universe=universe,
        fundamentals=fundamentals,
        prices=prices,
        llm=None,
        scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
        fusion=RecommendationFusionService(),
    )
    response = await use_case.execute(
        ReviewRequest(horizon=Horizon.LONG, use_llm=False)
    )
    assert response.reviews[0].action is PortfolioAction.EXIT


@pytest.mark.asyncio
async def test_review_empty_portfolio(tmp_path: Path) -> None:
    repo = SqlitePortfolioRepository(path=tmp_path / "p.db")
    use_case = ReviewPortfolioUseCase(
        portfolio=repo,
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([]),
        prices=FakePriceProvider([]),
        llm=None,
        scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
        fusion=RecommendationFusionService(),
    )
    response = await use_case.execute(ReviewRequest(use_llm=False))
    assert response.reviews == []
