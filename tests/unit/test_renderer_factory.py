"""Tests for ``RendererFactory``."""

from __future__ import annotations

import pytest

from stock_screener.core.errors import RenderError
from stock_screener.infra.renderer.factory import RendererFactory
from stock_screener.infra.renderer.json_renderer import JSONRenderer
from stock_screener.infra.renderer.markdown_renderer import MarkdownRenderer
from stock_screener.infra.renderer.rich_renderer import RichRenderer


def test_default_is_rich() -> None:
    assert isinstance(RendererFactory.create(), RichRenderer)


def test_explicit_rich() -> None:
    assert isinstance(RendererFactory.create("rich"), RichRenderer)


def test_explicit_json() -> None:
    assert isinstance(RendererFactory.create("json"), JSONRenderer)


def test_explicit_markdown_aliases() -> None:
    assert isinstance(RendererFactory.create("md"), MarkdownRenderer)
    assert isinstance(RendererFactory.create("markdown"), MarkdownRenderer)


def test_unknown_raises_render_error() -> None:
    with pytest.raises(RenderError):
        RendererFactory.create("xml")


def test_factory_lists_supported_names() -> None:
    assert set(RendererFactory.names()) == {"rich", "json", "md"}
