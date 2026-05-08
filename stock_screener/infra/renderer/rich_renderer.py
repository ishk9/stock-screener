"""Rich-based terminal renderer."""

from __future__ import annotations

from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...domain.entities.portfolio_review import PortfolioReview
from ...domain.entities.recommendation import Recommendation
from ...domain.ports.renderer import RenderOpts

_DISCLAIMER = "Not investment advice. For educational purposes only."


def _score_color(score: float) -> str:
    if score >= 75:
        return "bold green"
    if score >= 50:
        return "yellow"
    return "red"


_ACTION_STYLE = {
    "BUY": "bold white on green",
    "WAIT": "black on yellow",
    "AVOID": "bold white on red",
    "ADD": "bold white on green",
    "HOLD": "black on yellow",
    "TRIM": "black on cyan",
    "EXIT": "bold white on red",
}


def _action_badge(action_value: str) -> str:
    style = _ACTION_STYLE.get(action_value, "")
    return f"[{style}] {action_value} [/{style}]" if style else action_value


def _pnl_color(pct: float | None) -> str:
    if pct is None:
        return "dim"
    if pct >= 5:
        return "green"
    if pct <= -5:
        return "red"
    return "yellow"


class RichRenderer:
    """Pretty-prints recommendations to the terminal using ``rich``."""

    name = "rich"

    def __init__(self, console: Console | None = None) -> None:
        self._console = console if console is not None else Console()

    def render_screen(
        self, recs: Sequence[Recommendation], opts: RenderOpts
    ) -> None:
        table = Table(title="Stock Screen — top picks", show_lines=False)
        table.add_column("Rank", justify="right")
        table.add_column("Symbol", style="bold")
        table.add_column("Sector")
        table.add_column("Action", justify="center")
        table.add_column("Score", justify="right")
        table.add_column("Conviction")
        table.add_column("Risk %", justify="right")
        table.add_column("Horizon")
        table.add_column("Target", justify="right")

        for rank, rec in enumerate(recs, start=1):
            score_val = rec.score.value
            color = _score_color(score_val)
            table.add_row(
                str(rank),
                rec.symbol.code,
                rec.sector or "-",
                _action_badge(rec.action.value),
                f"[{color}]{score_val:.2f}[/{color}]",
                rec.conviction.value,
                f"{rec.risk_pct.value:.1f}",
                rec.suggested_horizon.value,
                "-" if rec.target is None else f"{rec.target:.2f}",
            )

        self._console.print(table)

        if opts.explain:
            for rec in recs:
                self._render_explain(rec)

        self._console.print(_DISCLAIMER)

    def render_analysis(
        self, rec: Recommendation, opts: RenderOpts
    ) -> None:
        self.render_screen([rec], opts)

    def render_portfolio(
        self, reviews: Sequence[PortfolioReview], opts: RenderOpts
    ) -> None:
        if not reviews:
            self._console.print("[dim]Portfolio is empty. Add positions with `ss portfolio add`.[/dim]")
            return

        table = Table(title="Portfolio review", show_lines=False)
        table.add_column("Symbol", style="bold")
        table.add_column("Qty", justify="right")
        table.add_column("Avg Buy", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P&L %", justify="right")
        table.add_column("Action", justify="center")
        table.add_column("Score", justify="right")
        table.add_column("Risk %", justify="right")

        total_cost = total_value = 0.0
        for r in reviews:
            pnl_pct = r.unrealised_pnl_pct
            current = r.current_price
            score = r.recommendation.score.value if r.recommendation else None
            risk = r.recommendation.risk_pct.value if r.recommendation else None
            cost = r.position.cost_basis
            value = (current or 0.0) * r.position.quantity
            total_cost += cost
            total_value += value
            table.add_row(
                r.position.symbol.code,
                f"{r.position.quantity:g}",
                f"{r.position.avg_buy_price:.2f}",
                "-" if current is None else f"{current:.2f}",
                "-" if pnl_pct is None
                else f"[{_pnl_color(pnl_pct)}]{pnl_pct:+.2f}%[/{_pnl_color(pnl_pct)}]",
                _action_badge(r.action.value),
                "-" if score is None else f"[{_score_color(score)}]{score:.1f}[/{_score_color(score)}]",
                "-" if risk is None else f"{risk:.1f}",
            )

        self._console.print(table)
        if total_cost > 0:
            total_pnl = total_value - total_cost
            total_pct = (total_pnl / total_cost) * 100.0
            color = _pnl_color(total_pct)
            self._console.print(
                f"[bold]Portfolio[/bold]  cost ₹{total_cost:,.0f}  value ₹{total_value:,.0f}  "
                f"P&L [{color}]{total_pnl:+,.0f} ({total_pct:+.2f}%)[/{color}]"
            )

        if opts.explain:
            for r in reviews:
                title = f"{r.position.symbol.code} — {r.action.value}"
                body = r.rationale
                if r.recommendation and r.recommendation.thesis_summary:
                    body += f"\n\n[bold]Research thesis:[/bold] {r.recommendation.thesis_summary}"
                self._console.print(Panel(body, title=title))

        self._console.print(_DISCLAIMER)

    def _render_explain(self, rec: Recommendation) -> None:
        risks = "\n".join(f"- {r}" for r in rec.key_risks) or "- (none reported)"
        catalysts = (
            "\n".join(f"- {c}" for c in rec.catalysts) or "- (none reported)"
        )
        body = (
            f"[bold]Thesis:[/bold] {rec.thesis_summary or '(no thesis)'}\n\n"
            f"[bold]Key risks:[/bold]\n{risks}\n\n"
            f"[bold]Catalysts:[/bold]\n{catalysts}"
        )
        title = f"{rec.symbol.code} — {rec.company_name}"
        self._console.print(Panel(body, title=title))


__all__ = ["RichRenderer"]
