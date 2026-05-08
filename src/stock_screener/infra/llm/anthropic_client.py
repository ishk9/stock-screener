"""Anthropic Messages adapter."""

from __future__ import annotations

import importlib
from typing import Any

from ...core.errors import LLMError, LLMRateLimitError
from ...domain.ports.llm_client import LLMRequest
from .base import BaseLLMClient

_JSON_SUFFIX = (
    "\n\nReply with VALID JSON ONLY — no prose, no markdown, no code fences."
)


class AnthropicClient(BaseLLMClient):
    """Adapter around the official ``anthropic`` SDK."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        anthropic_module: Any | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMError("Anthropic API key is required")
        self.model = model
        self._timeout_s = timeout_s
        self._module = (
            anthropic_module if anthropic_module is not None else self._load_module()
        )
        self._client = self._module.Anthropic(api_key=api_key)

    @staticmethod
    def _load_module() -> Any:
        try:
            return importlib.import_module("anthropic")
        except ImportError as exc:
            raise LLMError(
                "anthropic package is not installed. `pip install anthropic` "
                "or use the 'stub' provider."
            ) from exc

    async def _call_model(self, request: LLMRequest) -> str:
        system_prompt = request.system + _JSON_SUFFIX
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": request.user}],
                temperature=request.temperature,
            )
        except Exception as exc:
            raise self._map_error(exc) from exc

        try:
            block = message.content[0]
            text = getattr(block, "text", None) or block["text"]
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise LLMError(f"Malformed Anthropic response: {exc}") from exc

        if not text:
            raise LLMError("Anthropic returned empty content")
        return text

    def _map_error(self, exc: BaseException) -> LLMError:
        rate = getattr(self._module, "RateLimitError", None)
        auth = getattr(self._module, "AuthenticationError", None)
        if rate is not None and isinstance(exc, rate):
            return LLMRateLimitError(str(exc))
        if auth is not None and isinstance(exc, auth):
            return LLMError(f"auth: {exc}")
        return LLMError(f"{type(exc).__name__}: {exc}")


__all__ = ["AnthropicClient"]
