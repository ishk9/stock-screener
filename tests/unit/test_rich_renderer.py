"""Tests for ``RichRenderer``."""

from __future__ import annotations

from rich.console import Console

from stock_screener.domain.entities.recommendation import Recommendation
from stock_screener.domain.ports.renderer import RenderOpts
from stock_screener.domain.value_objects.conviction import Conviction
from stock_screener.domain.value_objects.horizon import Horizon
from stock_screener.domain.value_objects.pct import Pct
from stock_screener.domain.value_objects.score import Score
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.renderer.rich_renderer import RichRenderer


def _rec() -> Recommendation:
    return Recommendation(
        symbol=Symbol(code="TCS", exchange=Exchange.NSE),
        company_name="Tata Consultancy Services",
        sector="IT",
        score=Score(82.0),
        conviction=Conviction.HIGH,
        risk_pct=Pct(15.0),
        suggested_horizon=Horizon.LONG,
        target=4200.0,
        thesis_summary="Strong digital deal pipeline.",
        key_risks=("FX volatility",),
        catalysts=("Margin expansion",),
    )


def test_render_screen_outputs_table_and_disclaimer() -> None:
    console = Console(record=True, width=120)
    renderer = RichRenderer(console=console)
    renderer.render_screen([_rec()], RenderOpts())
    text = console.export_text()
    assert "TCS" in text
    assert "Stock Screen" in text
    assert "Not investment advice" in text
    assert "82.00" in text


def test_render_screen_with_explain_includes_thesis_and_risks() -> None:
    console = Console(record=True, width=120)
    renderer = RichRenderer(console=console)
    renderer.render_screen([_rec()], RenderOpts(explain=True))
    text = console.export_text()
    assert "Strong digital deal pipeline." in text
    assert "FX volatility" in text
    assert "Margin expansion" in text


def test_render_analysis_uses_screen_layout_for_single_pick() -> None:
    console = Console(record=True, width=120)
    renderer = RichRenderer(console=console)
    renderer.render_analysis(_rec(), RenderOpts())
    text = console.export_text()
    assert "TCS" in text


def test_renderer_name_is_rich() -> None:
    assert RichRenderer().name == "rich"
