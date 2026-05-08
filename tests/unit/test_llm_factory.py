"""Tests for ``LLMClientFactory``."""

from __future__ import annotations

import pytest

from stock_screener.core.config import LLMConfig
from stock_screener.core.errors import ConfigError
from stock_screener.infra.llm.factory import LLMClientFactory
from stock_screener.infra.llm.stub_client import StubLLMClient


def test_stub_provider_resolves_to_stub_client() -> None:
    cfg = LLMConfig(provider="stub", model="stub", api_key=None)
    client = LLMClientFactory.create(cfg)
    assert isinstance(client, StubLLMClient)
    assert client.name == "stub"


def test_unknown_provider_raises_config_error() -> None:
    cfg = LLMConfig(provider="does-not-exist", model="m", api_key="x")
    with pytest.raises(ConfigError):
        LLMClientFactory.create(cfg)


def test_factory_lists_default_registered_names() -> None:
    names = LLMClientFactory.names()
    for expected in ("openai", "anthropic", "gemini", "stub"):
        assert expected in names


def test_register_and_create_custom_provider() -> None:
    sentinel = StubLLMClient()
    LLMClientFactory.register("custom-test", lambda _cfg: sentinel)
    try:
        cfg = LLMConfig(provider="custom-test", model="m", api_key="x")
        out = LLMClientFactory.create(cfg)
        assert out is sentinel
    finally:
        LLMClientFactory.unregister("custom-test")
