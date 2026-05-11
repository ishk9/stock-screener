"""Unit tests for the chat() method on BaseLLMClient and the stub adapter."""

from __future__ import annotations

import asyncio

import pytest

from stock_screener.core.errors import LLMError, LLMSchemaError
from stock_screener.core.result import Err, Ok
from stock_screener.domain.value_objects.chat import ChatMessage
from stock_screener.infra.llm.base import BaseLLMClient
from stock_screener.infra.llm.stub_client import StubLLMClient


class _BlowsUp(BaseLLMClient):
    name = "blowsup"
    model = "x"

    async def _call_model(self, request):  # pragma: no cover - unused
        return "{}"

    async def _chat_model(self, messages, *, temperature, max_tokens):
        raise RuntimeError("provider exploded")


class _Echo(BaseLLMClient):
    name = "echo"
    model = "x"

    async def _call_model(self, request):  # pragma: no cover - unused
        return "{}"

    async def _chat_model(self, messages, *, temperature, max_tokens):
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return f"  reply: {last_user}  "


class _ReturnsNonString(BaseLLMClient):
    name = "bad"
    model = "x"

    async def _call_model(self, request):  # pragma: no cover - unused
        return "{}"

    async def _chat_model(self, messages, *, temperature, max_tokens):
        return 42  # type: ignore[return-value]


def test_stub_chat_returns_canned_response():
    client = StubLLMClient()
    result = asyncio.run(client.chat([ChatMessage(role="user", content="hi")]))
    assert isinstance(result, Ok)
    assert "stub assistant" in result.value
    assert "Not investment advice" in result.value


def test_chat_rejects_empty_messages():
    client = StubLLMClient()
    result = asyncio.run(client.chat([]))
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMSchemaError)


def test_chat_rejects_messages_without_user_turn():
    client = StubLLMClient()
    result = asyncio.run(
        client.chat([ChatMessage(role="system", content="ctx")])
    )
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMSchemaError)


def test_chat_wraps_provider_exception():
    result = asyncio.run(_BlowsUp().chat([ChatMessage(role="user", content="hi")]))
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)
    assert "provider exploded" in str(result.error)


def test_chat_strips_whitespace_from_response():
    result = asyncio.run(_Echo().chat([ChatMessage(role="user", content="ping")]))
    assert isinstance(result, Ok)
    assert result.value == "reply: ping"


def test_chat_rejects_non_string_response():
    result = asyncio.run(
        _ReturnsNonString().chat([ChatMessage(role="user", content="hi")])
    )
    assert isinstance(result, Err)


def test_chat_passes_temperature_and_max_tokens():
    captured: dict[str, object] = {}

    class _Capturing(BaseLLMClient):
        name = "cap"
        model = "x"

        async def _call_model(self, request):  # pragma: no cover - unused
            return "{}"

        async def _chat_model(self, messages, *, temperature, max_tokens):
            captured["temperature"] = temperature
            captured["max_tokens"] = max_tokens
            return "ok"

    asyncio.run(
        _Capturing().chat(
            [ChatMessage(role="user", content="hi")],
            temperature=0.9,
            max_tokens=512,
        )
    )
    assert captured == {"temperature": 0.9, "max_tokens": 512}
