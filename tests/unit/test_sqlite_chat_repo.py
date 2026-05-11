"""Unit tests for SqliteChatRepository."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_screener.core.errors import CacheError
from stock_screener.domain.entities.chat import Chat, ChatTurn
from stock_screener.infra.cache.sqlite_chat_repo import SqliteChatRepository


@pytest.fixture
def repo(tmp_path: Path) -> SqliteChatRepository:
    return SqliteChatRepository(path=tmp_path / "chat.sqlite")


def test_create_and_get_roundtrip(repo: SqliteChatRepository):
    chat = Chat(title="My first chat")
    chat.append("user", "hello")
    chat.append("assistant", "hi there")
    repo.create(chat)

    fetched = repo.get(chat.id)
    assert fetched is not None
    assert fetched.id == chat.id
    assert fetched.title == "My first chat"
    assert fetched.pinned is False
    assert len(fetched.messages) == 2
    assert fetched.messages[0].role == "user"
    assert fetched.messages[0].content == "hello"
    assert fetched.messages[1].role == "assistant"


def test_get_returns_none_for_missing(repo: SqliteChatRepository):
    assert repo.get("c-nonexist") is None


def test_create_rejects_duplicate(repo: SqliteChatRepository):
    chat = Chat()
    repo.create(chat)
    with pytest.raises(CacheError):
        repo.create(chat)


def test_append_message_updates_timestamp_and_persists(repo: SqliteChatRepository):
    chat = Chat()
    repo.create(chat)
    original_updated = chat.updated_at

    repo.append_message(chat.id, "user", "first")
    repo.append_message(chat.id, "assistant", "ack")
    fetched = repo.get(chat.id)
    assert fetched is not None
    assert [m.content for m in fetched.messages] == ["first", "ack"]
    assert fetched.updated_at >= original_updated


def test_append_message_to_missing_chat_raises(repo: SqliteChatRepository):
    with pytest.raises(CacheError):
        repo.append_message("c-missing", "user", "hi")


def test_pin_and_unpin(repo: SqliteChatRepository):
    chat = Chat()
    repo.create(chat)
    assert repo.set_pinned(chat.id, True) is True
    assert repo.get(chat.id).pinned is True  # type: ignore[union-attr]
    assert repo.set_pinned(chat.id, False) is True
    assert repo.get(chat.id).pinned is False  # type: ignore[union-attr]
    assert repo.set_pinned("c-missing", True) is False


def test_set_title(repo: SqliteChatRepository):
    chat = Chat()
    repo.create(chat)
    assert repo.set_title(chat.id, "Renamed") is True
    assert repo.get(chat.id).title == "Renamed"  # type: ignore[union-attr]
    assert repo.set_title("c-missing", "x") is False


def test_delete_removes_messages_via_cascade(repo: SqliteChatRepository):
    chat = Chat()
    repo.create(chat)
    repo.append_message(chat.id, "user", "hi")
    assert repo.delete(chat.id) is True
    assert repo.get(chat.id) is None
    assert repo.delete(chat.id) is False


def test_list_orders_pinned_first_then_recent(repo: SqliteChatRepository):
    a = Chat(title="A")
    b = Chat(title="B")
    c = Chat(title="C")
    for chat in (a, b, c):
        repo.create(chat)
        repo.append_message(chat.id, "user", "hi")
    repo.set_pinned(b.id, True)

    chats = repo.list()
    assert chats[0].id == b.id
    assert {ch.id for ch in chats} == {a.id, b.id, c.id}


def test_update_changes_metadata_not_messages(repo: SqliteChatRepository):
    chat = Chat()
    chat.append("user", "preserved")
    repo.create(chat)

    chat.title = "via update"
    chat.pinned = True
    repo.update(chat)

    fetched = repo.get(chat.id)
    assert fetched is not None
    assert fetched.title == "via update"
    assert fetched.pinned is True
    assert [m.content for m in fetched.messages] == ["preserved"]


def test_persistence_across_repo_instances(tmp_path: Path):
    path = tmp_path / "chat.sqlite"
    r1 = SqliteChatRepository(path=path)
    chat = Chat(title="persist")
    r1.create(chat)
    r1.append_message(chat.id, "user", "stays")

    r2 = SqliteChatRepository(path=path)
    fetched = r2.get(chat.id)
    assert fetched is not None
    assert fetched.title == "persist"
    assert [m.content for m in fetched.messages] == ["stays"]
