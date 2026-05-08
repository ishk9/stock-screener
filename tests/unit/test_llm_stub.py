"""Tests for ``StubLLMClient``."""

from __future__ import annotations

from stock_screener.core.result import Ok
from stock_screener.domain.ports.llm_client import LLMRequest
from stock_screener.infra.llm.prompts.analyse import AnalysisOutput
from stock_screener.infra.llm.stub_client import StubLLMClient


async def test_stub_returns_schema_valid_analysis_output() -> None:
    client = StubLLMClient()
    req = LLMRequest(system="sys", user="user")
    result = await client.analyse(req, AnalysisOutput)
    assert isinstance(result, Ok)
    out: AnalysisOutput = result.value
    assert out.thesis_summary
    assert 0.0 <= out.qualitative_risk <= 1.0
    assert 0.0 <= out.confidence <= 1.0
    assert out.suggested_horizon in {"short", "mid", "long", None}


async def test_stub_is_deterministic() -> None:
    client = StubLLMClient()
    req = LLMRequest(system="sys", user="user")
    a = (await client.analyse(req, AnalysisOutput)).unwrap()
    b = (await client.analyse(req, AnalysisOutput)).unwrap()
    assert a == b


def test_stub_metadata() -> None:
    client = StubLLMClient()
    assert client.name == "stub"
    assert client.model == "stub"
