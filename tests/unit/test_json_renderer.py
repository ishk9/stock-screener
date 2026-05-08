"""Tests for ``JSONRenderer``."""

from __future__ import annotations

import io
import json

from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.ports.renderer import RenderOpts
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.renderer.json_renderer import JSONRenderer


def _rec(code: str) -> Recommendation:
    return Recommendation(
        symbol=Symbol(code=code, exchange=Exchange.NSE),
        company_name=f"{code} Ltd",
        sector="IT",
        score=Score(80.0),
        conviction=Conviction.HIGH,
        risk_pct=Pct(20.0),
        suggested_horizon=Horizon.LONG,
    )


def test_render_screen_writes_json_array() -> None:
    buf = io.StringIO()
    renderer = JSONRenderer(stream=buf)
    renderer.render_screen([_rec("A"), _rec("B")], RenderOpts())
    payload = json.loads(buf.getvalue())
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["company_name"] == "A Ltd"


def test_render_analysis_writes_json_object() -> None:
    buf = io.StringIO()
    renderer = JSONRenderer(stream=buf)
    renderer.render_analysis(_rec("Z"), RenderOpts())
    payload = json.loads(buf.getvalue())
    assert isinstance(payload, dict)
    assert payload["company_name"] == "Z Ltd"


def test_renderer_name_is_json() -> None:
    assert JSONRenderer().name == "json"
