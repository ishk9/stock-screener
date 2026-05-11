"""LLM client port — provider-agnostic structured-output and chat interface."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

from ...core.errors import LLMError
from ...core.result import Result
from ..value_objects.chat import ChatMessage

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system: str
    user: str
    temperature: float = 0.2
    max_tokens: int = 1500


@runtime_checkable
class LLMClient(Protocol):
    """A vendor-agnostic LLM supporting both structured analyse() and free-form chat()."""

    name: str
    model: str

    async def analyse(
        self,
        request: LLMRequest,
        schema: Type[T],
    ) -> Result[T, LLMError]: ...

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> Result[str, LLMError]: ...


__all__ = ["ChatMessage", "LLMClient", "LLMRequest"]
