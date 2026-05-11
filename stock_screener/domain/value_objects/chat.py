"""Chat-related value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A single turn in an LLM chat — provider-agnostic wire format."""

    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("system", "user", "assistant"):
            raise ValueError(f"invalid chat role: {self.role!r}")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")


__all__ = ["ChatMessage", "ChatRole"]
