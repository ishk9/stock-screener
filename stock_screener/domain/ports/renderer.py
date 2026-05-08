"""Renderer port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from ..entities.recommendation import Recommendation


@dataclass(frozen=True, slots=True)
class RenderOpts:
    explain: bool = False
    color: bool = True


@runtime_checkable
class Renderer(Protocol):
    name: str

    def render_screen(
        self, recs: Sequence[Recommendation], opts: RenderOpts
    ) -> None: ...

    def render_analysis(
        self, rec: Recommendation, opts: RenderOpts
    ) -> None: ...


__all__ = ["Renderer", "RenderOpts"]
