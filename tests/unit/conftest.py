"""Shared fixtures for unit tests."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

import pytest

from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.entities.snapshot import CompanySnapshot
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol


def make_company(
    *,
    code: str = "RELIANCE",
    name: str = "Reliance Industries",
    sector: str = "Energy",
    bucket: MarketCapBucket | None = MarketCapBucket.LARGE,
    market_cap_inr: float | None = 1_500_000.0,
) -> Company:
    return Company(
        symbol=Symbol(code=code, exchange=Exchange.NSE),
        name=name,
        sector=sector,
        market_cap_bucket=bucket,
        market_cap_inr=market_cap_inr,
    )


def make_fundamentals(**overrides: object) -> Fundamentals:
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
        operating_cash_flow=18_000.0,
        free_cash_flow=12_000.0,
        capex=6_000.0,
        ev_ebitda=10.0,
        current_ratio=1.5,
        revenue_cagr_3y=12.0,
        eps_cagr_3y=15.0,
        profit_growth_yoy=20.0,
        dividend_yield=2.0,
        payout_ratio=20.0,
    )
    base.update(overrides)
    return Fundamentals(**base)  # type: ignore[arg-type]


def make_price_series(
    closes: Sequence[float],
    *,
    start: date = date(2024, 1, 1),
) -> PriceSeries:
    points: list[PricePoint] = []
    for i, c in enumerate(closes):
        d = start + timedelta(days=i)
        c_f = float(c)
        points.append(
            PricePoint(
                on=d,
                open=c_f,
                high=c_f * 1.01,
                low=c_f * 0.99,
                close=c_f,
                volume=1_000,
            )
        )
    return PriceSeries.from_points(points)


def make_trend_prices(n: int = 260, start_price: float = 100.0, drift: float = 0.001) -> PriceSeries:
    closes: list[float] = []
    p = start_price
    for i in range(n):
        p = p * (1.0 + drift + 0.0005 * ((i % 7) - 3))
        closes.append(round(p, 4))
    return make_price_series(closes)


def make_snapshot(
    *,
    company: Company | None = None,
    fundamentals: Fundamentals | None = None,
    prices: PriceSeries | None = None,
    omit_fundamentals: bool = False,
    omit_prices: bool = False,
) -> CompanySnapshot:
    return CompanySnapshot(
        company=company or make_company(),
        fundamentals=None if omit_fundamentals else (fundamentals or make_fundamentals()),
        prices=None if omit_prices else (prices or make_trend_prices()),
    )


@pytest.fixture
def snapshot_factory():
    return make_snapshot


@pytest.fixture
def fundamentals_factory():
    return make_fundamentals


@pytest.fixture
def price_factory():
    return make_price_series


@pytest.fixture
def trend_prices_factory():
    return make_trend_prices


@pytest.fixture
def company_factory():
    return make_company


@pytest.fixture
def silence_logging(monkeypatch: pytest.MonkeyPatch):
    """Silence structlog + project logger setup for CLI invocation tests.

    Required for CLI tests because structlog's default ``PrintLoggerFactory``
    writes to ``sys.stdout``, which contaminates ``--format json``/``md`` output.
    Tests that rely on real log output should NOT request this fixture.
    """
    import logging
    import structlog

    from stock_screener.core import logging as logging_mod

    monkeypatch.setattr(logging_mod, "_CONFIGURED", True)

    def _noop(self, *args, **kwargs) -> None:  # noqa: ANN001
        return None

    for method in (
        "msg",
        "log",
        "debug",
        "info",
        "warning",
        "warn",
        "error",
        "err",
        "critical",
        "fatal",
        "exception",
        "failure",
    ):
        monkeypatch.setattr(structlog.PrintLogger, method, _noop)

    structlog.reset_defaults()
    structlog.configure(
        processors=[],
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
        logger_factory=structlog.ReturnLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    yield
    structlog.reset_defaults()
