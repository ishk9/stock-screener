"""JSON renderer — emits a JSON array of recommendations to stdout."""

from __future__ import annotations

import json
import sys
from typing import IO, Sequence

from ...domain.entities.recommendation import Recommendation
from ...domain.ports.renderer import RenderOpts


class JSONRenderer:
    """Dumps recommendations as a JSON array.

    A custom ``stream`` may be injected for tests; defaults to ``sys.stdout``.
    """

    name = "json"

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream = stream

    def render_screen(
        self, recs: Sequence[Recommendation], opts: RenderOpts
    ) -> None:
        payload = [rec.model_dump(mode="json") for rec in recs]
        text = json.dumps(payload, indent=2, default=str)
        self._write(text + "\n")

    def render_analysis(
        self, rec: Recommendation, opts: RenderOpts
    ) -> None:
        text = json.dumps(rec.model_dump(mode="json"), indent=2, default=str)
        self._write(text + "\n")

    def _write(self, text: str) -> None:
        out = self._stream if self._stream is not None else sys.stdout
        out.write(text)


__all__ = ["JSONRenderer"]
