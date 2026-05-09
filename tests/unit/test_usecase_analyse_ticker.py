"""Unit tests for ``AnalyseTickerUseCase``."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from stock_screener.core.errors import LLMError, UnavailableError
from stock_screener.core.result import Err, Ok, Result
from stock_screener.domain.analytics.strategies.composite import CompositeScoringStrategy
from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.ports.llm_client import LLMRequest
from stock_screener.domain.recommendation.fusion import RecommendationFusionService
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.llm.prompts.analyse import AnalysisOutput
from stock_screener.usecases.analyse_ticker import (
    AnalyseRequest,
    AnalyseTickerUseCase,
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


class _StubLLMClient:
    name = "stub"
    model = "stub-1"

    def __init__(self) -> None:
        self.call_count = 0
        self.calls: list[LLMRequest] = []

    async def analyse(
        self, request: LLMRequest, schema: type
    ) -> Result[AnalysisOutput, LLMError]:
        self.call_count += 1
        self.calls.append(request)
        return Ok(
            AnalysisOutput(
                thesis_summary="Stable cash flow.",
                key_risks=("regulatory",),
                catalysts=("margin expansion",),
                qualitative_risk=0.4,
                confidence=0.7,
                suggested_horizon="long",
            )
        )


@pytest.fixture
def reliance_symbol() -> Symbol:
    return Symbol(code="RELIANCE", exchange=Exchange.NSE)


@pytest.fixture
def use_case_factory():
    def _factory(
        *,
        universe,
        fundamentals,
        prices,
        llm,
    ) -> AnalyseTickerUseCase:
        return AnalyseTickerUseCase(
            universe=universe,
            fundamentals=fundamentals,
            prices=prices,
            llm=llm,
            scorer=CompositeScoringStrategy.make_default({"value": 1.0}),
            fusion=RecommendationFusionService(),
        )

    return _factory


@pytest.mark.asyncio
async def test_returns_recommendation_for_existing_company(
    use_case_factory, reliance_symbol: Symbol
) -> None:
    company = Company(
        symbol=reliance_symbol,
        name="Reliance Industries",
        sector="Energy",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    use_case = use_case_factory(
        universe=InMemoryUniverse([company]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=_StubLLMClient(),
    )
    rec = await use_case.execute(
        AnalyseRequest(symbol=reliance_symbol, horizon=Horizon.LONG, use_llm=True)
    )
    assert rec.symbol == reliance_symbol
    assert rec.company_name == "Reliance Industries"


@pytest.mark.asyncio
async def test_falls_back_to_constructed_company_when_universe_misses(
    use_case_factory, reliance_symbol: Symbol
) -> None:
    use_case = use_case_factory(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=None,
    )
    rec = await use_case.execute(
        AnalyseRequest(symbol=reliance_symbol, horizon=Horizon.LONG, use_llm=False)
    )
    assert rec.company_name == reliance_symbol.code


@pytest.mark.asyncio
async def test_no_llm_does_not_call_stub(
    use_case_factory, reliance_symbol: Symbol
) -> None:
    stub = _StubLLMClient()
    use_case = use_case_factory(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=stub,
    )
    await use_case.execute(
        AnalyseRequest(symbol=reliance_symbol, use_llm=False)
    )
    assert stub.call_count == 0


@pytest.mark.asyncio
async def test_provider_failures_do_not_raise(
    use_case_factory, reliance_symbol: Symbol
) -> None:
    use_case = use_case_factory(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([Err(UnavailableError("down"))]),
        prices=FakePriceProvider([Err(UnavailableError("down"))]),
        llm=None,
    )
    rec = await use_case.execute(
        AnalyseRequest(symbol=reliance_symbol, horizon=Horizon.LONG, use_llm=False)
    )
    assert rec is not None
    assert rec.symbol == reliance_symbol


@pytest.mark.asyncio
async def test_horizon_flows_through(
    use_case_factory, reliance_symbol: Symbol
) -> None:
    use_case = use_case_factory(
        universe=InMemoryUniverse([]),
        fundamentals=FakeFundamentalsProvider([Ok(_full_fundamentals())]),
        prices=FakePriceProvider([Ok(_flat_prices())]),
        llm=None,
    )
    rec = await use_case.execute(
        AnalyseRequest(symbol=reliance_symbol, horizon=Horizon.MID, use_llm=False)
    )
    assert rec.suggested_horizon == Horizon.MID
