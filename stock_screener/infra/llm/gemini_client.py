"""Google Gemini (google-genai) adapter."""

from __future__ import annotations

import importlib
from typing import Any

from ...core.errors import LLMError, LLMRateLimitError
from ...domain.ports.llm_client import LLMRequest
from .base import BaseLLMClient


class GeminiClient(BaseLLMClient):
    """Adapter around the ``google-genai`` SDK.

    A pre-built ``client`` may be injected for tests; otherwise we lazy-import
    ``google.genai`` and instantiate ``genai.Client(api_key=...)``.
    """

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: Any | None = None,
        genai_module: Any | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        if client is None and not api_key:
            raise LLMError("Gemini API key is required")
        self.model = model
        self._timeout_s = timeout_s
        if client is not None:
            self._client = client
            self._module = genai_module
        else:
            self._module = (
                genai_module if genai_module is not None else self._load_module()
            )
            self._client = self._module.Client(api_key=api_key)

    @staticmethod
    def _load_module() -> Any:
        try:
            module = importlib.import_module("google.genai")
        except ImportError as exc:
            raise LLMError(
                "google-genai package is not installed. "
                "`pip install google-genai` or use the 'stub' provider."
            ) from exc
        return module

    async def _call_model(self, request: LLMRequest) -> str:
        contents = f"{request.system}\n\n---\n\n{request.user}"
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config={
                    "response_mime_type": "application/json",
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_tokens,
                },
            )
        except Exception as exc:
            raise self._map_error(exc) from exc

        text = getattr(response, "text", None)
        if not text:
            raise LLMError("Gemini returned empty content")
        return text

    def _map_error(self, exc: BaseException) -> LLMError:
        msg = str(exc).lower()
        if "rate" in msg and "limit" in msg:
            return LLMRateLimitError(str(exc))
        if "auth" in msg or "api key" in msg or "permission" in msg:
            return LLMError(f"auth: {exc}")
        return LLMError(f"{type(exc).__name__}: {exc}")


__all__ = ["GeminiClient"]
