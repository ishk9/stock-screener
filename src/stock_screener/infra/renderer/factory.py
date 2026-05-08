"""Renderer factory — selects ``rich`` | ``json`` | ``md``."""

from __future__ import annotations

from ...core.errors import RenderError
from ...domain.ports.renderer import Renderer
from .json_renderer import JSONRenderer
from .markdown_renderer import MarkdownRenderer
from .rich_renderer import RichRenderer

_DEFAULT = "rich"


class RendererFactory:
    """Resolves a renderer name to a concrete adapter."""

    @staticmethod
    def names() -> list[str]:
        return ["rich", "json", "md"]

    @staticmethod
    def create(name: str = _DEFAULT) -> Renderer:
        normalised = (name or _DEFAULT).strip().lower()
        if normalised == "rich":
            return RichRenderer()
        if normalised == "json":
            return JSONRenderer()
        if normalised in {"md", "markdown"}:
            return MarkdownRenderer()
        raise RenderError(
            f"Unknown renderer {name!r}. Choose one of {RendererFactory.names()}"
        )


__all__ = ["RendererFactory"]
