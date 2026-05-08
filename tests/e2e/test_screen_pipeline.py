"""End-to-end orchestration test for the screen use-case.

Wires real domain services with fake adapters and asserts that running the
pipeline against an in-memory universe produces well-formed recommendations.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from stock_screener.core.result import Err, Ok
from stock_screener.domain.analytics.strategies.composite import (
    CompositeScoringStrategy,
)
from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.recommendation.fusion import RecommendationFusionService
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.usecases.screen_companies import (
    ScreenCompaniesUseCase,
    ScreenRequest,
)

from tests.conftest import FakeFundamentalsProvider, FakePriceProvider


class InMemoryUniverse:
    def __init__(self, companies: list[Company]) -> None:
        self._companies = companies

    def upsert_many(self, companies: list[Company]) -> None:  # pragma: no cover
        self._companies = companies

    def list(self, bucket: MarketCapBucket | None = None) -> list[Company]:
        if bucket is None:
            return list(self._companies)
        return [c for c in self._companies if c.market_cap_bucket == bucket]

    def get(self, code: str) -> Company | None:
        return next((c for c in self._companies if c.symbol.code == code), None)

    def count(self) -> int:
        return len(self._companies)

    def last_refreshed_at(self) -> str | None:  # pragma: no cover
        return None


def _make_fundamentals() -> Fundamentals:
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


def _make_prices() -> PriceSeries:
    points = [
        PricePoint(
            on=date(2025, 1, 1) + timedelta(days=i),
            open=100.0 + i * 0.05,
            high=101.0 + i * 0.05,
            low=99.0 + i * 0.05,
            close=100.0 + i * 0.05,
            volume=1_000_000,
        )
        for i in range(260)
    ]
    return PriceSeries.from_points(points)


@pytest.mark.asyncio
async def test_screen_pipeline_produces_top_n_recommendations() -> None:
    companies = [
        Company(
            symbol=Symbol(code=f"TEST{i}", exchange=Exchange.NSE),
            name=f"Test Co {i}",
            sector="IT",
            market_cap_inr=1e12 - i * 1e10,
            market_cap_bucket=MarketCapBucket.LARGE,
            market_cap_rank=i + 1,
        )
        for i in range(5)
    ]
    universe = InMemoryUniverse(companies)
    f_responses = [Ok(_make_fundamentals()) for _ in companies]
    p_responses = [Ok(_make_prices()) for _ in companies]

    fundamentals = FakeFundamentalsProvider(f_responses)
    prices = FakePriceProvider(p_responses)

    use_case = ScreenCompaniesUseCase(
        universe=universe,
        fundamentals=fundamentals,
        prices=prices,
        news=None,
        llm=None,
        scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
        fusion=RecommendationFusionService(),
    )

    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=3,
            horizon=Horizon.LONG,
            use_llm=False,
        )
    )

    assert response.universe_size == 5
    assert response.candidates_scored == 5
    assert len(response.recommendations) == 3
    for rec in response.recommendations:
        assert 0 <= rec.score.value <= 100
        assert 0 <= rec.risk_pct.value <= 100
        assert rec.suggested_horizon == Horizon.LONG


@pytest.mark.asyncio
async def test_screen_pipeline_empty_universe_returns_empty() -> None:
    use_case = ScreenCompaniesUseCase(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([]),
        prices=FakePriceProvider([]),
        news=None,
        llm=None,
        scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
        fusion=RecommendationFusionService(),
    )
    response = await use_case.execute(
        ScreenRequest(bucket=MarketCapBucket.LARGE, top=5, horizon=Horizon.LONG, use_llm=False)
    )
    assert response.recommendations == []


@pytest.mark.asyncio
async def test_screen_pipeline_handles_missing_data_gracefully() -> None:
    """When providers fail, the pipeline degrades gracefully — never raises."""
    from stock_screener.core.errors import UnavailableError

    company = Company(
        symbol=Symbol(code="BAD", exchange=Exchange.NSE),
        name="Bad Co",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    use_case = ScreenCompaniesUseCase(
        universe=InMemoryUniverse([company]),
        fundamentals=FakeFundamentalsProvider([Err(UnavailableError("down"))]),
        prices=FakePriceProvider([Err(UnavailableError("down"))]),
        news=None,
        llm=None,
        scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
        fusion=RecommendationFusionService(),
    )
    response = await use_case.execute(
        ScreenRequest(bucket=MarketCapBucket.LARGE, top=5, horizon=Horizon.LONG, use_llm=False)
    )
    assert response.recommendations == []
