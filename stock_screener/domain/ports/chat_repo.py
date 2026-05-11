"""Chat repository port."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ..entities.chat import Chat


@runtime_checkable
class ChatRepository(Protocol):
    """Persistent storage of chat sessions and their full history."""

    def create(self, chat: Chat) -> None: ...
    def update(self, chat: Chat) -> None: ...
    def get(self, chat_id: str) -> Chat | None: ...
    def list(self) -> list[Chat]: ...
    def delete(self, chat_id: str) -> bool: ...
    def set_pinned(self, chat_id: str, pinned: bool) -> bool: ...
    def set_title(self, chat_id: str, title: str) -> bool: ...
    def append_message(
        self,
        chat_id: str,
        role: Literal["system", "user", "assistant"],
        content: str,
    ) -> None: ...


__all__ = ["ChatRepository"]
