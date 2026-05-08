"""Tests for the analyse prompt builder."""

from __future__ import annotations

from datetime import date, datetime, timezone

from stock_screener.domain.entities.company import Company
from stock_screener.domain.entities.fundamentals import Fundamentals
from stock_screener.domain.entities.news import NewsItem
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.entities.snapshot import CompanySnapshot
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.llm.prompts import (
    SYSTEM_PROMPT,
    AnalysisOutput,
    build_analysis_prompt,
)


def _snapshot() -> CompanySnapshot:
    company = Company(
        symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
        name="Reliance Industries",
        sector="Energy",
        industry="Refining",
        market_cap_bucket=MarketCapBucket.LARGE,
    )
    fundamentals = Fundamentals(
        as_of=date(2026, 1, 1),
        pe=22.5,
        pb=2.1,
        roe=0.18,
        debt_to_equity=0.4,
        operating_margin=0.15,
    )
    points = [
        PricePoint(
            on=date(2025, 1, 1),
            open=2400.0,
            high=2410.0,
            low=2390.0,
            close=2400.0,
            volume=1000,
        ),
        PricePoint(
            on=date(2025, 2, 1),
            open=2500.0,
            high=2510.0,
            low=2490.0,
            close=2500.0,
            volume=1000,
        ),
    ]
    prices = PriceSeries.from_points(points)
    news = (
        NewsItem(
            headline="Q3 results beat estimates",
            source="Mint",
            published_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        ),
    )
    return CompanySnapshot(
        company=company, fundamentals=fundamentals, prices=prices, news=news
    )


def test_build_analysis_prompt_returns_request_with_expected_shape() -> None:
    req = build_analysis_prompt(_snapshot(), Horizon.LONG)
    assert req.system == SYSTEM_PROMPT
    assert req.user.strip()
    assert req.temperature == 0.2
    assert req.max_tokens == 1500


def test_build_analysis_prompt_contains_company_and_fundamentals() -> None:
    req = build_analysis_prompt(_snapshot(), Horizon.MID)
    assert "Reliance Industries" in req.user
    assert "RELIANCE" in req.user
    assert "pe" in req.user
    assert "Q3 results beat estimates" in req.user


def test_build_analysis_prompt_user_is_token_budget_aware() -> None:
    req = build_analysis_prompt(_snapshot(), Horizon.SHORT)
    assert len(req.user) < 8000


def test_analysis_output_validates_canonical_payload() -> None:
    out = AnalysisOutput(
        thesis_summary="Reasonable",
        key_risks=("a", "b"),
        catalysts=("c",),
        qualitative_risk=0.4,
        confidence=0.7,
        suggested_horizon="long",
    )
    assert out.suggested_horizon == "long"
    assert out.qualitative_risk == 0.4


def test_build_analysis_prompt_handles_missing_optional_fields() -> None:
    company = Company(
        symbol=Symbol(code="ACME", exchange=Exchange.NSE),
        name="Acme",
    )
    snap = CompanySnapshot(company=company)
    req = build_analysis_prompt(snap, Horizon.MID)
    assert "Acme" in req.user
    assert "(no recent headlines)" in req.user
