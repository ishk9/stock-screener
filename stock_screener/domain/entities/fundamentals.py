"""Fundamentals entity — accounting + ratio snapshot."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Fundamentals(BaseModel):
    """A point-in-time fundamentals snapshot.

    All amounts are in INR crore unless noted. Optional fields are ``None``
    when the upstream provider does not expose them.
    """

    model_config = ConfigDict(frozen=True)

    as_of: date

    # Income statement
    revenue: Optional[float] = Field(default=None, ge=0)
    operating_profit: Optional[float] = None
    net_profit: Optional[float] = None
    eps: Optional[float] = None

    # Balance sheet
    total_assets: Optional[float] = Field(default=None, ge=0)
    total_equity: Optional[float] = None
    total_debt: Optional[float] = Field(default=None, ge=0)
    cash: Optional[float] = Field(default=None, ge=0)
    shares_outstanding: Optional[float] = Field(default=None, ge=0)

    # Cash flow
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    capex: Optional[float] = None

    # Ratios (per-period; provider-supplied or computed)
    pe: Optional[float] = None
    pb: Optional[float] = None
    ev_ebitda: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    debt_to_equity: Optional[float] = Field(default=None, ge=0)
    current_ratio: Optional[float] = Field(default=None, ge=0)
    interest_coverage: Optional[float] = None

    # Growth (CAGR / yoy %)
    revenue_cagr_3y: Optional[float] = None
    revenue_cagr_5y: Optional[float] = None
    eps_cagr_3y: Optional[float] = None
    profit_growth_yoy: Optional[float] = None

    # Margins (%)
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None

    # Dividend
    dividend_yield: Optional[float] = Field(default=None, ge=0)
    payout_ratio: Optional[float] = None


__all__ = ["Fundamentals"]
