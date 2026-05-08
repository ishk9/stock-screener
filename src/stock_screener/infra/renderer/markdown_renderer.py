"""Markdown renderer — emits a table + optional per-pick sections."""

from __future__ import annotations

import sys
from typing import IO, Sequence

from ...domain.entities.recommendation import Recommendation
from ...domain.ports.renderer import RenderOpts

_DISCLAIMER = "_Not investment advice. For educational purposes only._"
_HEADERS = ("Rank", "Symbol", "Sector", "Score", "Conviction", "Risk %", "Horizon", "Target")


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

    def _write(self, text: str) -> None:
        out = self._stream if self._stream is not None else sys.stdout
        out.write(text)


__all__ = ["MarkdownRenderer"]
