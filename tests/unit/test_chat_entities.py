"""Unit tests for Chat / ChatTurn entities and the ChatMessage VO."""

from __future__ import annotations

import pytest

from stock_screener.domain.entities.chat import Chat, ChatTurn
from stock_screener.domain.value_objects.chat import ChatMessage


def test_new_chat_has_generated_id_with_prefix():
    chat = Chat()
    assert chat.id.startswith("c-")
    assert len(chat.id) == 8  # "c-" + 6 chars
    assert chat.turn_count == 0
    assert chat.title == "New chat"
    assert chat.pinned is False


def test_chat_ids_are_unique():
    ids = {Chat().id for _ in range(100)}
    assert len(ids) == 100


def test_append_updates_timestamp_and_count():
    chat = Chat()
    t0 = chat.updated_at
    turn = chat.append("user", "hello")
    assert isinstance(turn, ChatTurn)
    assert chat.messages == [turn]
    assert chat.updated_at >= t0
    assert chat.turn_count == 1

    # system messages don't count toward turn_count
    chat.append("system", "ctx")
    assert chat.turn_count == 1
    chat.append("assistant", "hi")
    assert chat.turn_count == 2


def test_auto_title_picks_first_user_message():
    chat = Chat()
    chat.append("system", "ctx")
    chat.append("user", "What is the outlook for RELIANCE?\nMore lines.")
    chat.append("assistant", "...")
    assert chat.auto_title_from_first_user_message() == "What is the outlook for RELIANCE?"


def test_auto_title_truncates_long_message():
    chat = Chat()
    chat.append("user", "x" * 200)
    title = chat.auto_title_from_first_user_message(max_len=40)
    assert len(title) == 40


def test_auto_title_falls_back_when_empty():
    chat = Chat(title="default")
    assert chat.auto_title_from_first_user_message() == "default"


def test_chat_message_validates_role():
    ChatMessage(role="user", content="hi")  # valid
    ChatMessage(role="system", content="ctx")
    ChatMessage(role="assistant", content="hi")
    with pytest.raises(ValueError):
        ChatMessage(role="other", content="x")  # type: ignore[arg-type]


def test_chat_message_validates_content_type():
    with pytest.raises(TypeError):
        ChatMessage(role="user", content=123)  # type: ignore[arg-type]


def test_chat_message_is_hashable_and_frozen():
    m = ChatMessage(role="user", content="hi")
    hash(m)
    with pytest.raises(Exception):  # noqa: PT011 - frozen dataclass raises FrozenInstanceError
        m.content = "x"  # type: ignore[misc]
