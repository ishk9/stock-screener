"""Deterministic stub LLM — used for ``--dry-run`` and CI.

Emits a neutral, schema-valid JSON for the standard ``AnalysisOutput`` schema
and includes the keys most other ad-hoc schemas are likely to want.
"""

from __future__ import annotations

import json

from ...domain.ports.llm_client import LLMRequest
from .base import BaseLLMClient


class StubLLMClient(BaseLLMClient):
    """Returns canned, schema-valid JSON; never makes a network call."""

    name = "stub"
    model = "stub"

    def __init__(self) -> None:
        return

    async def _call_model(self, request: LLMRequest) -> str:
        payload = {
            "thesis_summary": (
                "Stub analysis: balanced fundamentals, neutral momentum. "
                "Generated without any external LLM call."
            ),
            "key_risks": (
                "Macro headwinds in the Indian market",
                "Sector-specific regulatory uncertainty",
                "Execution risk on stated guidance",
            ),
            "catalysts": (
                "Earnings beat in upcoming quarter",
                "Margin expansion from operating leverage",
                "Re-rating on improved capital allocation",
            ),
            "qualitative_risk": 0.5,
            "confidence": 0.6,
            "suggested_horizon": "mid",
        }
        return json.dumps(payload)


__all__ = ["StubLLMClient"]
