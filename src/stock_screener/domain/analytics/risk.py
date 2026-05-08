"""Risk decomposition — volatility, beta, leverage, drawdown, quality concern."""

from __future__ import annotations

import math
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from ..entities.snapshot import CompanySnapshot
from ..value_objects.pct import Pct

DEFAULT_WEIGHTS: dict[str, float] = {
    "volatility": 0.35,
    "leverage": 0.25,
    "drawdown": 0.25,
    "quality": 0.15,
}

TRADING_DAYS_PER_YEAR = 252


class RiskBreakdown(BaseModel):
    """Per-axis risk view plus a single aggregate ``composite``."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    volatility: Pct | None = None
    beta: Pct | None = None
    leverage: Pct | None = None
    drawdown: Pct | None = None
    quality_concern: Pct | None = None
    composite: Pct = Field(...)


def _daily_returns(closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev <= 0:
            continue
        out.append((closes[i] - prev) / prev)
    return out


def _stdev(samples: Sequence[float]) -> float | None:
    n = len(samples)
    if n < 2:
        return None
    mean = sum(samples) / n
    variance = sum((x - mean) ** 2 for x in samples) / (n - 1)
    if variance < 0:
        return None
    return math.sqrt(variance)


def _annualised_vol(daily_returns: Sequence[float]) -> float | None:
    sigma = _stdev(daily_returns)
    if sigma is None:
        return None
    return sigma * math.sqrt(TRADING_DAYS_PER_YEAR)


def _max_drawdown(closes: Sequence[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak <= 0:
            continue
        dd = (peak - c) / peak
        if dd > worst:
            worst = dd
    return worst


def _beta(stock_returns: Sequence[float], market_returns: Sequence[float]) -> float | None:
    n = min(len(stock_returns), len(market_returns))
    if n < 2:
        return None
    s = list(stock_returns[-n:])
    m = list(market_returns[-n:])
    s_mean = sum(s) / n
    m_mean = sum(m) / n
    cov = sum((si - s_mean) * (mi - m_mean) for si, mi in zip(s, m)) / (n - 1)
    var_m = sum((mi - m_mean) ** 2 for mi in m) / (n - 1)
    if var_m <= 0:
        return None
    return cov / var_m


def _vol_to_pct(annual_vol: float | None) -> Pct | None:
    if annual_vol is None:
        return None
    return Pct.from_ratio(min(1.0, max(0.0, annual_vol / 0.6)))


def _beta_to_pct(beta: float | None) -> Pct | None:
    if beta is None:
        return None
    return Pct.from_ratio(min(1.0, max(0.0, abs(beta) / 2.0)))


def _de_to_pct(de: float | None) -> Pct | None:
    if de is None:
        return None
    if de < 0:
        return Pct.from_ratio(1.0)
    return Pct.from_ratio(min(1.0, de / 2.0))


def _drawdown_to_pct(dd: float | None) -> Pct | None:
    if dd is None:
        return None
    return Pct.from_ratio(min(1.0, max(0.0, dd)))


def _quality_concern(snapshot: CompanySnapshot) -> Pct | None:
    f = snapshot.fundamentals
    if f is None:
        return None
    score = 0.0
    weight = 0.0
    if f.interest_coverage is not None:
        weight += 1.0
        ic = float(f.interest_coverage)
        if ic <= 0:
            score += 1.0
        elif ic < 1.5:
            score += 0.8
        elif ic < 3:
            score += 0.5
        elif ic < 6:
            score += 0.2
    if f.free_cash_flow is not None:
        weight += 1.0
        if f.free_cash_flow < 0:
            score += 0.9
        elif f.net_profit is not None and f.net_profit > 0:
            ratio = f.free_cash_flow / f.net_profit
            if ratio < 0.3:
                score += 0.5
            elif ratio < 0.6:
                score += 0.2
    if f.current_ratio is not None:
        weight += 1.0
        cr = float(f.current_ratio)
        if cr < 1.0:
            score += 0.7
        elif cr < 1.2:
            score += 0.3
    if weight == 0.0:
        return None
    return Pct.from_ratio(score / weight)


def _weighted_average(parts: dict[str, Pct | None], weights: dict[str, float]) -> float:
    num = 0.0
    den = 0.0
    for key, pct in parts.items():
        if pct is None:
            continue
        w = weights.get(key, 0.0)
        num += pct.as_ratio * w
        den += w
    if den == 0.0:
        return 0.5
    return num / den


def compute_risk(
    snapshot: CompanySnapshot,
    market_returns: Sequence[float] | None = None,
) -> RiskBreakdown:
    """Decompose risk for a snapshot into volatility, beta, leverage, drawdown, quality.

    Tolerates missing data: any unavailable axis becomes ``None`` and is
    excluded from the composite. ``composite`` is always a valid ``Pct``;
    when no signal is available we fall back to a neutral ``50%``.
    """
    closes = snapshot.prices.closes() if snapshot.prices is not None else ()
    daily = _daily_returns(closes)

    annual_vol = _annualised_vol(daily) if daily else None
    vol_pct = _vol_to_pct(annual_vol)

    beta_value: float | None = None
    if market_returns is not None and daily:
        beta_value = _beta(daily, market_returns)
    beta_pct = _beta_to_pct(beta_value)

    de = snapshot.fundamentals.debt_to_equity if snapshot.fundamentals is not None else None
    leverage_pct = _de_to_pct(de)

    drawdown_pct = _drawdown_to_pct(_max_drawdown(closes))
    quality_pct = _quality_concern(snapshot)

    parts: dict[str, Pct | None] = {
        "volatility": vol_pct,
        "leverage": leverage_pct,
        "drawdown": drawdown_pct,
        "quality": quality_pct,
    }
    composite_ratio = _weighted_average(parts, DEFAULT_WEIGHTS)
    composite = Pct.from_ratio(composite_ratio)

    return RiskBreakdown(
        volatility=vol_pct,
        beta=beta_pct,
        leverage=leverage_pct,
        drawdown=drawdown_pct,
        quality_concern=quality_pct,
        composite=composite,
    )


__all__ = ["RiskBreakdown", "compute_risk", "DEFAULT_WEIGHTS", "TRADING_DAYS_PER_YEAR"]
