"""Edge-case tests for ``ScreenCompaniesUseCase``."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from stock_screener.core.events import (
    EventBus,
    UseCaseCompleted,
    UseCaseStarted,
)
from stock_screener.core.result import Ok
from stock_screener.domain.analytics.strategies.composite import CompositeScoringStrategy
from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.recommendation.fusion import RecommendationFusionService
from stock_screener.domain.specifications import (
    HasMinimumDataSpec,
    MaxRiskSpec,
    SectorBlacklistSpec,
)
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.usecases.screen_companies import (
    ScreenCompaniesUseCase,
    ScreenRequest,
)

from tests.conftest import FakeFundamentalsProvider, FakePriceProvider
from tests.e2e.test_screen_pipeline import InMemoryUniverse


def _full_fundamentals() -> Fundamentals:
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


def _flat_prices() -> PriceSeries:
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


def _company(code: str, *, sector: str | None = None) -> Company:
    return Company(
        symbol=Symbol(code=code, exchange=Exchange.NSE),
        name=code,
        sector=sector,
        market_cap_bucket=MarketCapBucket.LARGE,
    )


def _make_use_case(
    *,
    universe,
    fundamentals,
    prices,
    llm=None,
    events: EventBus | None = None,
) -> ScreenCompaniesUseCase:
    return ScreenCompaniesUseCase(
        universe=universe,
        fundamentals=fundamentals,
        prices=prices,
        news=None,
        llm=llm,
        scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
        fusion=RecommendationFusionService(),
        events=events,
    )


@pytest.mark.asyncio
async def test_snapshot_spec_filters_by_sector_blacklist() -> None:
    companies = [
        _company("FIN", sector="Finance"),
        _company("PHA", sector="Pharma"),
    ]
    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider(
            [Ok(_full_fundamentals()), Ok(_full_fundamentals())]
        ),
        prices=FakePriceProvider([Ok(_flat_prices()), Ok(_flat_prices())]),
    )
    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=5,
            horizon=Horizon.LONG,
            snapshot_spec=SectorBlacklistSpec.of(["Finance"]),
            use_llm=False,
        )
    )
    codes = {r.symbol.code for r in response.recommendations}
    assert "FIN" not in codes
    assert "PHA" in codes


@pytest.mark.asyncio
async def test_rec_spec_filters_by_max_risk() -> None:
    companies = [_company(f"S{i}") for i in range(4)]
    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
    )
    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=10,
            horizon=Horizon.LONG,
            rec_spec=MaxRiskSpec(Pct(20.0)),
            use_llm=False,
        )
    )
    for rec in response.recommendations:
        assert rec.risk_pct.value <= 20.0


@pytest.mark.asyncio
async def test_top_n_when_fewer_candidates_returns_all() -> None:
    companies = [_company(f"S{i}") for i in range(2)]
    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies]),
        prices=FakePriceProvider([Ok(_flat_prices()) for _ in companies]),
    )
    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=10,
            horizon=Horizon.LONG,
            use_llm=False,
        )
    )
    assert len(response.recommendations) <= 2


@pytest.mark.asyncio
async def test_use_llm_true_with_no_llm_does_not_crash() -> None:
    companies = [_company("A")]
    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=None,
    )
    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=5,
            horizon=Horizon.LONG,
            use_llm=True,
        )
    )
    assert len(response.recommendations) == 1


@pytest.mark.asyncio
async def test_universe_limit_zero_returns_empty() -> None:
    companies = [_company(f"S{i}") for i in range(5)]
    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([]),
        prices=FakePriceProvider([]),
    )
    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=5,
            horizon=Horizon.LONG,
            use_llm=False,
            universe_limit=0,
        )
    )
    assert response.recommendations == []


@pytest.mark.asyncio
async def test_event_bus_receives_started_and_completed() -> None:
    companies = [_company("A")]
    bus = EventBus()
    events: list[object] = []
    bus.subscribe_all(events.append)

    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        events=bus,
    )
    await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=5,
            horizon=Horizon.LONG,
            use_llm=False,
        )
    )
    types = [type(e) for e in events]
    assert UseCaseStarted in types
    assert UseCaseCompleted in types


@pytest.mark.asyncio
async def test_concurrent_fetch_with_low_concurrency() -> None:
    companies = [_company(f"S{i}") for i in range(20)]
    fundamentals = FakeFundamentalsProvider([Ok(_full_fundamentals()) for _ in companies])
    prices = FakePriceProvider([Ok(_flat_prices()) for _ in companies])
    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=fundamentals,
        prices=prices,
    )
    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=20,
            horizon=Horizon.LONG,
            use_llm=False,
            max_concurrency=3,
        )
    )
    assert len(fundamentals.calls) == 20
    assert len(prices.calls) == 20
    assert len(response.recommendations) <= 20


@pytest.mark.asyncio
async def test_has_minimum_data_spec_filters_partial_snapshots() -> None:
    from stock_screener.core.errors import UnavailableError
    from stock_screener.core.result import Err

    companies = [_company("FULL"), _company("PARTIAL")]
    fundamentals = FakeFundamentalsProvider(
        [Ok(_full_fundamentals()), Ok(_full_fundamentals())]
    )
    prices = FakePriceProvider(
        [Ok(_flat_prices()), Err(UnavailableError("down"))]
    )
    use_case = _make_use_case(
        universe=InMemoryUniverse(companies),
        fundamentals=fundamentals,
        prices=prices,
    )
    response = await use_case.execute(
        ScreenRequest(
            bucket=MarketCapBucket.LARGE,
            top=5,
            horizon=Horizon.LONG,
            snapshot_spec=HasMinimumDataSpec(),
            use_llm=False,
        )
    )
    codes = {r.symbol.code for r in response.recommendations}
    assert "PARTIAL" not in codes
    assert "FULL" in codes
