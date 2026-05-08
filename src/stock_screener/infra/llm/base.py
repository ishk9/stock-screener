"""Template Method base class for LLM adapters.

Subclasses implement only ``_call_model`` — JSON parsing, schema validation
and error mapping all live here. The string returned from ``_call_model``
MUST be JSON parseable.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ...core.errors import LLMError, LLMSchemaError
from ...core.result import Err, Ok, Result
from ...domain.ports.llm_client import LLMRequest

T = TypeVar("T", bound=BaseModel)


class BaseLLMClient(ABC):
    """Abstract LLM adapter — the structure of ``analyse`` is fixed.

    Concrete subclasses set ``name`` / ``model`` and implement
    :py:meth:`_call_model`. They never see JSON parsing or schema errors;
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

    @abstractmethod
    async def _call_model(self, request: LLMRequest) -> str:
        """Make the actual vendor API call and return the JSON string."""
        ...


__all__ = ["BaseLLMClient"]
