"""LLM client port — provider-agnostic structured-output interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

from ...core.errors import LLMError
from ...core.result import Result

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class LLMRequest:
    system: str
    user: str
    temperature: float = 0.2
    max_tokens: int = 1500


@runtime_checkable
class LLMClient(Protocol):
    """A vendor-agnostic LLM that returns Pydantic-validated JSON."""

    name: str
    model: str

    async def analyse(
        self,
        request: LLMRequest,
        schema: Type[T],
    ) -> Result[T, LLMError]: ...


__all__ = ["LLMClient", "LLMRequest"]
