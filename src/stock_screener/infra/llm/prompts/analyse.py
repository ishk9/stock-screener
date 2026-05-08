"""``analyse`` prompt — output schema and prompt builder."""

from __future__ import annotations

from typing import Any, Literal

from jinja2 import Environment
from pydantic import BaseModel, ConfigDict, Field

from ....domain.entities.snapshot import CompanySnapshot
from ....domain.ports.llm_client import LLMRequest
from ....domain.value_objects.horizon import Horizon
from .templates import ANALYSE_TEMPLATE, SYSTEM_PROMPT

_MAX_HEADLINES = 5
_FUNDAMENTAL_FIELDS = (
    "pe",
    "pb",
    "roe",
    "roce",
    "debt_to_equity",
    "revenue_cagr_3y",
    "profit_growth_yoy",
    "operating_margin",
    "net_margin",
    "dividend_yield",
)


class AnalysisOutput(BaseModel):
    """Structured response expected from the LLM analyst."""

    model_config = ConfigDict(frozen=True)

    thesis_summary: str = Field(min_length=1)
    key_risks: tuple[str, ...] = Field(default_factory=tuple)
    catalysts: tuple[str, ...] = Field(default_factory=tuple)
    qualitative_risk: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_horizon: Literal["short", "mid", "long"] | None = None


def _project_fundamentals(snap: CompanySnapshot) -> dict[str, str]:
    f = snap.fundamentals
    if f is None:
        return {}
    out: dict[str, str] = {}
    for name in _FUNDAMENTAL_FIELDS:
        val = getattr(f, name, None)
        if val is None:
            continue
        out[name] = f"{val:.2f}" if isinstance(val, (int, float)) else str(val)
    return out


def _project_returns(snap: CompanySnapshot) -> dict[str, str]:
    if snap.prices is None:
        return {}
    out: dict[str, str] = {}
    for label, sessions in (("1m", 21), ("3m", 63), ("1y", 252)):
        r = snap.prices.return_over(sessions=sessions)
        if r is None:
            continue
        out[label] = f"{r * 100:.2f}%"
    return out


def _project_headlines(snap: CompanySnapshot) -> list[str]:
    items = list(snap.news[:_MAX_HEADLINES])
    return [n.headline.strip() for n in items if n.headline.strip()]


def build_analysis_prompt(snapshot: CompanySnapshot, horizon: Horizon) -> LLMRequest:
    """Render the analyse prompt for a single ``CompanySnapshot``."""

    company = snapshot.company
    context: dict[str, Any] = {
        "name": company.name,
        "symbol": str(company.symbol),
        "sector": company.sector,
        "industry": company.industry,
        "market_cap_bucket": (
            company.market_cap_bucket.label if company.market_cap_bucket else None
        ),
        "horizon": horizon.label,
        "fundamentals": _project_fundamentals(snapshot),
        "returns": _project_returns(snapshot),
        "headlines": _project_headlines(snapshot),
    }

    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    template = env.from_string(ANALYSE_TEMPLATE)
    user_prompt = template.render(**context).strip()

    return LLMRequest(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.2,
        max_tokens=1500,
    )


__all__ = ["AnalysisOutput", "build_analysis_prompt"]
