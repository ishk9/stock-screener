"""Tests for ``BaseLLMClient`` Template Method behaviour."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from stock_screener.core.errors import LLMError, LLMSchemaError
from stock_screener.core.result import Err, Ok
from stock_screener.domain.ports.llm_client import LLMRequest
from stock_screener.infra.llm.base import BaseLLMClient


class _Schema(BaseModel):
    a: int
    b: str


class _CannedClient(BaseLLMClient):
    name = "canned"
    model = "test"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    async def _call_model(self, request: LLMRequest) -> str:
        return self._payload


class _RaisingClient(BaseLLMClient):
    name = "raising"
    model = "test"

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def _call_model(self, request: LLMRequest) -> str:
        raise self._exc


def _request() -> LLMRequest:
    return LLMRequest(system="sys", user="hello")


async def test_analyse_happy_path_returns_ok() -> None:
    client = _CannedClient(json.dumps({"a": 1, "b": "x"}))
    result = await client.analyse(_request(), _Schema)
    assert isinstance(result, Ok)
    assert result.value == _Schema(a=1, b="x")


async def test_analyse_invalid_json_returns_schema_error() -> None:
    client = _CannedClient("not-json {")
    result = await client.analyse(_request(), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMSchemaError)


async def test_analyse_validation_failure_returns_schema_error() -> None:
    client = _CannedClient(json.dumps({"a": "not-an-int", "b": "x"}))
    result = await client.analyse(_request(), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMSchemaError)


async def test_analyse_missing_fields_returns_schema_error() -> None:
    client = _CannedClient(json.dumps({"a": 1}))
    result = await client.analyse(_request(), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMSchemaError)


async def test_analyse_empty_user_prompt_short_circuits() -> None:
    client = _CannedClient(json.dumps({"a": 1, "b": "x"}))
    result = await client.analyse(LLMRequest(system="sys", user="   "), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMSchemaError)


async def test_analyse_propagates_llm_error_from_subclass() -> None:
    client = _RaisingClient(LLMError("boom"))
    result = await client.analyse(_request(), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)


async def test_analyse_wraps_unknown_exception_as_llm_error() -> None:
    client = _RaisingClient(RuntimeError("kaboom"))
    result = await client.analyse(_request(), _Schema)
    assert isinstance(result, Err)
    assert isinstance(result.error, LLMError)


def test_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseLLMClient()  # type: ignore[abstract]
