"""Markdown renderer — emits a table + optional per-pick sections."""

from __future__ import annotations

import sys
from typing import IO, Sequence

from ...domain.entities.portfolio_review import PortfolioReview
from ...domain.entities.recommendation import Recommendation
from ...domain.ports.renderer import RenderOpts

_DISCLAIMER = "_Not investment advice. For educational purposes only._"
_HEADERS = ("Rank", "Symbol", "Sector", "Action", "Score", "Conviction", "Risk %", "Horizon", "Target")


class MarkdownRenderer:
    """Plain-text Markdown output suitable for piping into a file."""

    name = "md"

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream = stream

    def render_screen(
        self, recs: Sequence[Recommendation], opts: RenderOpts
    ) -> None:
        lines: list[str] = []
        lines.append("| " + " | ".join(_HEADERS) + " |")
        lines.append("|" + "|".join("---" for _ in _HEADERS) + "|")
        for rank, rec in enumerate(recs, start=1):
            lines.append(
                "| " + " | ".join(
                    [
                        str(rank),
                        rec.symbol.code,
                        rec.sector or "-",
                        f"**{rec.action.value}**",
                        f"{rec.score.value:.2f}",
                        rec.conviction.value,
                        f"{rec.risk_pct.value:.1f}",
                        rec.suggested_horizon.value,
                        "-" if rec.target is None else f"{rec.target:.2f}",
                    ]
                )
                + " |"
            )

        if opts.explain:
            for rec in recs:
                lines.append("")
                lines.append(f"### {rec.symbol.code} — {rec.company_name}")
                if rec.thesis_summary:
                    lines.append("")
                    lines.append(rec.thesis_summary)
                if rec.key_risks:
                    lines.append("")
                    lines.append("**Key risks**")
                    lines.extend(f"- {r}" for r in rec.key_risks)
                if rec.catalysts:
                    lines.append("")
                    lines.append("**Catalysts**")
                    lines.extend(f"- {c}" for c in rec.catalysts)

        lines.append("")
        lines.append(_DISCLAIMER)
        self._write("\n".join(lines) + "\n")

    def render_analysis(
        self, rec: Recommendation, opts: RenderOpts
    ) -> None:
        self.render_screen([rec], opts)

    def render_portfolio(
        self, reviews: Sequence[PortfolioReview], opts: RenderOpts
    ) -> None:
        headers = ("Symbol", "Qty", "Avg Buy", "Current", "P&L %", "Action", "Score", "Risk %")
        lines: list[str] = []
        lines.append("# Portfolio review")
        lines.append("")
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join("---" for _ in headers) + "|")
        for r in reviews:
            score = r.recommendation.score.value if r.recommendation else None
            risk = r.recommendation.risk_pct.value if r.recommendation else None
            lines.append(
                "| " + " | ".join([
                    r.position.symbol.code,
                    f"{r.position.quantity:g}",
                    f"{r.position.avg_buy_price:.2f}",
                    "-" if r.current_price is None else f"{r.current_price:.2f}",
                    "-" if r.unrealised_pnl_pct is None else f"{r.unrealised_pnl_pct:+.2f}%",
                    f"**{r.action.value}**",
                    "-" if score is None else f"{score:.1f}",
                    "-" if risk is None else f"{risk:.1f}",
                ]) + " |"
            )

        if opts.explain:
            for r in reviews:
                lines.append("")
                lines.append(f"### {r.position.symbol.code} — {r.action.value}")
                lines.append("")
                lines.append(r.rationale)
                if r.recommendation and r.recommendation.thesis_summary:
                    lines.append("")
                    lines.append(f"**Research thesis:** {r.recommendation.thesis_summary}")

        lines.append("")
        lines.append(_DISCLAIMER)
        self._write("\n".join(lines) + "\n")

    def _write(self, text: str) -> None:
        out = self._stream if self._stream is not None else sys.stdout
        out.write(text)


__all__ = ["MarkdownRenderer"]
