"""Derived ratio calculation — pure, None-safe arithmetic."""

from __future__ import annotations

from typing import Any

from ..entities.fundamentals import Fundamentals


def safe_div(num: float | None, den: float | None) -> float | None:
    """Return ``num / den`` or ``None`` when undefined.

    ``None`` denominator, zero, or non-positive denominators all collapse
    to ``None`` to avoid spurious ratios from negative-equity or zero-debt
    edge cases.
    """
    if num is None or den is None:
        return None
    try:
        d = float(den)
    except (TypeError, ValueError):
        return None
    if d <= 0.0:
        return None
    try:
        return float(num) / d
    except (TypeError, ValueError):
        return None


def _fill(existing: float | None, computed: float | None) -> float | None:
    if existing is not None:
        return existing
    return computed


def _maybe_market_cap(f: Fundamentals, latest_price: float | None) -> float | None:
    if latest_price is None or f.shares_outstanding is None:
        return None
    if latest_price <= 0:
        return None
    return float(latest_price) * float(f.shares_outstanding)


def _compute_pe(f: Fundamentals, latest_price: float | None) -> float | None:
    if latest_price is None or f.eps is None:
        return None
    if float(latest_price) <= 0:
        return None
    return safe_div(float(latest_price), float(f.eps))


def _compute_pb(f: Fundamentals, latest_price: float | None) -> float | None:
    market_cap = _maybe_market_cap(f, latest_price)
    if market_cap is None or f.total_equity is None:
        return None
    return safe_div(market_cap, float(f.total_equity))


def _compute_de(f: Fundamentals) -> float | None:
    if f.total_debt is None or f.total_equity is None:
        return None
    return safe_div(float(f.total_debt), float(f.total_equity))


def _compute_roe(f: Fundamentals) -> float | None:
    if f.net_profit is None or f.total_equity is None:
        return None
    ratio = safe_div(float(f.net_profit), float(f.total_equity))
    if ratio is None:
        return None
    return ratio * 100.0


def _compute_roce(f: Fundamentals) -> float | None:
    if f.operating_profit is None:
        return None
    capital_employed: float | None
    if f.total_assets is not None:
        ce = float(f.total_assets)
        if f.cash is not None:
            ce -= float(f.cash)
        capital_employed = ce
    elif f.total_equity is not None and f.total_debt is not None:
        capital_employed = float(f.total_equity) + float(f.total_debt)
    else:
        capital_employed = None
    ratio = safe_div(float(f.operating_profit), capital_employed)
    if ratio is None:
        return None
    return ratio * 100.0


def _compute_interest_coverage(f: Fundamentals) -> float | None:
    if f.operating_profit is None or f.net_profit is None:
        return None
    interest_expense = float(f.operating_profit) - float(f.net_profit)
    if interest_expense <= 0:
        return None
    return safe_div(float(f.operating_profit), interest_expense)


def _compute_gross_margin(f: Fundamentals) -> float | None:
    if f.operating_profit is None or f.revenue is None:
        return None
    ratio = safe_div(float(f.operating_profit), float(f.revenue))
    if ratio is None:
        return None
    return ratio * 100.0


def _compute_operating_margin(f: Fundamentals) -> float | None:
    if f.operating_profit is None or f.revenue is None:
        return None
    ratio = safe_div(float(f.operating_profit), float(f.revenue))
    if ratio is None:
        return None
    return ratio * 100.0


def _compute_net_margin(f: Fundamentals) -> float | None:
    if f.net_profit is None or f.revenue is None:
        return None
    ratio = safe_div(float(f.net_profit), float(f.revenue))
    if ratio is None:
        return None
    return ratio * 100.0


def compute_derived_ratios(
    f: Fundamentals,
    latest_price: float | None,
) -> Fundamentals:
    """Return a new ``Fundamentals`` with computable ratios filled in.

    Existing non-None fields are preserved verbatim. Missing inputs simply
    leave the corresponding output as ``None`` — this function never raises
    on partial data.
    """
    updates: dict[str, Any] = {
        "pe": _fill(f.pe, _compute_pe(f, latest_price)),
        "pb": _fill(f.pb, _compute_pb(f, latest_price)),
        "debt_to_equity": _fill(f.debt_to_equity, _compute_de(f)),
        "roe": _fill(f.roe, _compute_roe(f)),
        "roce": _fill(f.roce, _compute_roce(f)),
        "interest_coverage": _fill(f.interest_coverage, _compute_interest_coverage(f)),
        "gross_margin": _fill(f.gross_margin, _compute_gross_margin(f)),
        "operating_margin": _fill(f.operating_margin, _compute_operating_margin(f)),
        "net_margin": _fill(f.net_margin, _compute_net_margin(f)),
    }
    return f.model_copy(update=updates)


__all__ = ["compute_derived_ratios", "safe_div"]
