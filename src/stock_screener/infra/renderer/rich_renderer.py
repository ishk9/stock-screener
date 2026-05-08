"""Rich-based terminal renderer."""

from __future__ import annotations

from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...domain.entities.recommendation import Recommendation
from ...domain.ports.renderer import RenderOpts

_DISCLAIMER = "Not investment advice. For educational purposes only."


def _score_color(score: float) -> str:
    if score >= 75:
        return "bold green"
    if score >= 50:
        return "yellow"
    return "red"


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
