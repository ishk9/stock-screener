"""Chat aggregate — a persistent conversation between user and assistant."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def _new_chat_id() -> str:
    """Generate a short, human-typeable chat id like ``c-x4f2k1``."""
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))
    return f"c-{suffix}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatTurn(BaseModel):
    """A single saved message in a chat history."""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str
    created_at: datetime = Field(default_factory=_utcnow)


class Chat(BaseModel):
    """A persistent multi-turn conversation."""

    model_config = ConfigDict()

    id: str = Field(default_factory=_new_chat_id)
    title: str = "New chat"
    pinned: bool = False
    messages: list[ChatTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self.messages if m.role != "system")

    def append(self, role: Literal["system", "user", "assistant"], content: str) -> ChatTurn:
        turn = ChatTurn(role=role, content=content)
        self.messages.append(turn)
        self.updated_at = turn.created_at
        return turn

    def auto_title_from_first_user_message(self, max_len: int = 60) -> str:
        """Derive a title from the first user message, used when none is set."""
        for m in self.messages:
            if m.role == "user":
                text = m.content.strip().splitlines()[0] if m.content.strip() else ""
                if text:
                    return text[:max_len].rstrip()
        return self.title


__all__ = ["Chat", "ChatTurn"]
