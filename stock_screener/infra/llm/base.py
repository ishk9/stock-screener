"""Template Method base class for LLM adapters.

Subclasses implement only ``_call_model`` (structured JSON) and ``_chat_model``
(free-form chat). JSON parsing, schema validation and error mapping live here.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ...core.errors import LLMError, LLMSchemaError
from ...core.result import Err, Ok, Result
from ...domain.ports.llm_client import LLMRequest
from ...domain.value_objects.chat import ChatMessage

T = TypeVar("T", bound=BaseModel)


class BaseLLMClient(ABC):
    """Abstract LLM adapter — the structure of ``analyse``/``chat`` is fixed.

    Concrete subclasses set ``name`` / ``model`` and implement
    :py:meth:`_call_model` (returns JSON string) and :py:meth:`_chat_model`
    (returns plain text). They never see JSON parsing or schema errors;
    those are mapped to :class:`LLMSchemaError` here.
    """

    name: str = "base"
    model: str = ""

    async def analyse(
        self,
        request: LLMRequest,
        schema: type[T],
    ) -> Result[T, LLMError]:
        if not request.user.strip():
            return Err(LLMSchemaError("Empty user prompt"))
        if not request.system.strip():
            return Err(LLMSchemaError("Empty system prompt"))

        try:
            raw = await self._call_model(request)
        except LLMError as exc:
            return Err(exc)
        except Exception as exc:  # noqa: BLE001 — boundary catch-all
            return Err(LLMError(f"{type(exc).__name__}: {exc}"))

        if not isinstance(raw, str):
            return Err(LLMSchemaError(f"_call_model must return str; got {type(raw).__name__}"))

        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            return Err(LLMSchemaError(f"Invalid JSON from {self.name}: {exc}"))

        try:
            instance = schema.model_validate_json(raw)
        except ValidationError as exc:
            return Err(LLMSchemaError(f"Schema validation failed: {exc}"))

        return Ok(instance)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> Result[str, LLMError]:
        if not messages:
            return Err(LLMSchemaError("chat() requires at least one message"))
        if not any(m.role == "user" for m in messages):
            return Err(LLMSchemaError("chat() requires at least one user message"))

        try:
            raw = await self._chat_model(
                list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except LLMError as exc:
            return Err(exc)
        except Exception as exc:  # noqa: BLE001 — boundary catch-all
            return Err(LLMError(f"{type(exc).__name__}: {exc}"))

        if not isinstance(raw, str):
            return Err(LLMError(f"_chat_model must return str; got {type(raw).__name__}"))

        return Ok(raw.strip())

    @abstractmethod
    async def _call_model(self, request: LLMRequest) -> str:
        """Make the actual vendor API call and return the JSON string."""
        ...

    @abstractmethod
    async def _chat_model(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Make the actual vendor chat API call and return assistant text."""
        ...


__all__ = ["BaseLLMClient"]
