"""Tests for ``MarkdownRenderer``."""

from __future__ import annotations

import io

from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.ports.renderer import RenderOpts
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.renderer.markdown_renderer import MarkdownRenderer


def _rec() -> Recommendation:
    return Recommendation(
        symbol=Symbol(code="INFY", exchange=Exchange.NSE),
        company_name="Infosys",
        sector="IT",
        score=Score(78.0),
        conviction=Conviction.HIGH,
        risk_pct=Pct(18.0),
        suggested_horizon=Horizon.MID,
        thesis_summary="Decent digital growth.",
        key_risks=("US slowdown",),
        catalysts=("New deal wins",),
    )


def test_render_screen_emits_table_headers_and_disclaimer() -> None:
    buf = io.StringIO()
    renderer = MarkdownRenderer(stream=buf)
    renderer.render_screen([_rec()], RenderOpts())
    text = buf.getvalue()
    assert "| Rank |" in text
    assert "| Symbol |" in text or "Symbol" in text
    assert "INFY" in text
    assert "Not investment advice" in text


def test_render_screen_explain_emits_per_pick_sections() -> None:
    buf = io.StringIO()
    renderer = MarkdownRenderer(stream=buf)
    renderer.render_screen([_rec()], RenderOpts(explain=True))
    text = buf.getvalue()
    assert "### INFY — Infosys" in text
    assert "Decent digital growth." in text
    assert "**Key risks**" in text
    assert "**Catalysts**" in text


def test_render_analysis_includes_company() -> None:
    buf = io.StringIO()
    renderer = MarkdownRenderer(stream=buf)
    renderer.render_analysis(_rec(), RenderOpts(explain=True))
    text = buf.getvalue()
    assert "INFY" in text


def test_renderer_name_is_md() -> None:
    assert MarkdownRenderer().name == "md"
