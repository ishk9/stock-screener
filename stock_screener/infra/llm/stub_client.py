"""Deterministic stub LLM — used for ``--dry-run`` and CI.

Emits a neutral, schema-valid JSON for the standard ``AnalysisOutput`` schema
and includes the keys most other ad-hoc schemas are likely to want. Chat mode
returns a short canned response that echoes the last user turn.
"""

from __future__ import annotations

import json

from ...domain.ports.llm_client import LLMRequest
from ...domain.value_objects.chat import ChatMessage
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

    async def _chat_model(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        snippet = (last_user or "").strip().splitlines()[0] if last_user else ""
        if len(snippet) > 80:
            snippet = snippet[:77] + "..."
        return (
            f"[stub assistant] You said: {snippet!r}\n"
            "No live LLM is configured. Set SS_LLM_PROVIDER and SS_OPENAI_API_KEY "
            "(or another provider) to enable real answers. Not investment advice."
        )


__all__ = ["StubLLMClient"]
