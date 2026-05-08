"""OpenAI Chat Completions adapter."""

from __future__ import annotations

import importlib
from typing import Any

from ...core.errors import LLMError, LLMRateLimitError
from ...domain.ports.llm_client import LLMRequest
from .base import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    """Adapter around the official ``openai`` SDK.

    The SDK module is lazy-imported (and can be injected) so that this file
    is import-safe even when ``openai`` is not installed.
    """

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        openai_module: Any | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMError("OpenAI API key is required")
        self.model = model
        self._timeout_s = timeout_s
        self._module = openai_module if openai_module is not None else self._load_module()
        self._client = self._module.OpenAI(api_key=api_key)

    @staticmethod
    def _load_module() -> Any:
        try:
            return importlib.import_module("openai")
        except ImportError as exc:
            raise LLMError(
                "openai package is not installed. `pip install openai` or "
                "use the 'stub' provider."
            ) from exc

    async def _call_model(self, request: LLMRequest) -> str:
        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
                response_format={"type": "json_object"},
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout=self._timeout_s,
            )
        except Exception as exc:
            raise self._map_error(exc) from exc

        try:
            content = completion.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError(f"Malformed OpenAI response: {exc}") from exc

        if content is None:
            raise LLMError("OpenAI returned empty content")
        return content

    def _map_error(self, exc: BaseException) -> LLMError:
        rate = getattr(self._module, "RateLimitError", None)
        auth = getattr(self._module, "AuthenticationError", None)
        if rate is not None and isinstance(exc, rate):
            return LLMRateLimitError(str(exc))
        if auth is not None and isinstance(exc, auth):
            return LLMError(f"auth: {exc}")
        return LLMError(f"{type(exc).__name__}: {exc}")


__all__ = ["OpenAIClient"]
