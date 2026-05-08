"""Tests for ``OpenAIClient`` — the SDK is fully faked."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from stock_screener.core.errors import LLMError, LLMRateLimitError
from stock_screener.core.result import Err, Ok
from stock_screener.domain.ports.llm_client import LLMRequest
from stock_screener.infra.llm.openai_client import OpenAIClient


class _Schema(BaseModel):
    a: int


class _FakeRateLimitError(Exception):
    pass


class _FakeAuthError(Exception):
    pass


class _FakeCompletions:
    def __init__(self, content: str | None = None, raises: Exception | None = None) -> None:
        self._content = content
        self._raises = raises
        self.last_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = _FakeChat(completions)


def _fake_module(completions: _FakeCompletions) -> Any:
    module = SimpleNamespace(
        OpenAI=lambda api_key: _FakeOpenAI(completions),
        RateLimitError=_FakeRateLimitError,
        AuthenticationError=_FakeAuthError,
    )
    return module


async def test_openai_happy_path_passes_payload_and_returns_ok() -> None:
    completions = _FakeCompletions(content=json.dumps({"a": 7}))
    module = _fake_module(completions)
    client = OpenAIClient(api_key="key", model="gpt-4o-mini", openai_module=module)

    result = await client.analyse(LLMRequest(system="sys", user="user"), _Schema)
    assert isinstance(result, Ok)
    assert result.value.a == 7

    kwargs = completions.last_kwargs
    assert kwargs is not None
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1]["role"] == "user"


async def test_openai_rate_limit_maps_to_llm_rate_limit() -> None:
    completions = _FakeCompletions(raises=_FakeRateLimitError("slow down"))
    client = OpenAIClient(
        api_key="key",
        model="m",
        openai_module=_fake_module(completions),
    )

    result = await client.analyse(LLMRequest(system="sys", user="user"), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMRateLimitError)


async def test_openai_auth_error_maps_to_llm_error() -> None:
    completions = _FakeCompletions(raises=_FakeAuthError("nope"))
    client = OpenAIClient(
        api_key="key",
        model="m",
        openai_module=_fake_module(completions),
    )
    result = await client.analyse(LLMRequest(system="sys", user="user"), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)


async def test_openai_generic_exception_maps_to_llm_error() -> None:
    completions = _FakeCompletions(raises=RuntimeError("boom"))
    client = OpenAIClient(
        api_key="key",
        model="m",
        openai_module=_fake_module(completions),
    )
    result = await client.analyse(LLMRequest(system="sys", user="user"), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)


def test_openai_requires_api_key() -> None:
    with pytest.raises(LLMError):
        OpenAIClient(api_key="", model="m", openai_module=_fake_module(_FakeCompletions(content="{}")))


async def test_openai_empty_content_yields_llm_error() -> None:
    completions = _FakeCompletions(content=None)
    client = OpenAIClient(
        api_key="key",
        model="m",
        openai_module=_fake_module(completions),
    )
    result = await client.analyse(LLMRequest(system="sys", user="user"), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)
