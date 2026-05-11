"""SQLite-backed implementation of :class:`ChatRepository`."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ...core.errors import CacheError
from ...domain.entities.chat import Chat, ChatTurn

_CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    pinned      INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)
"""

_MSG_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    chat_id    TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, seq)
)
"""

_INDEX = "CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(pinned DESC, updated_at DESC)"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SqliteChatRepository:
    """Stores chats + messages in the same SQLite database family."""

    def __init__(self, *, path: Path | str) -> None:
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self._path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except sqlite3.Error as exc:
            raise CacheError(f"failed to open chat db at {self._path}: {exc}") from exc

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(_CHAT_SCHEMA)
            conn.execute(_MSG_SCHEMA)
            conn.execute(_INDEX)

    # --------------------------- public API --------------------------- #
    def create(self, chat: Chat) -> None:
        with closing(self._connect()) as conn:
            try:
                conn.execute(
                    "INSERT INTO chats (id, title, pinned, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        chat.id,
                        chat.title,
                        1 if chat.pinned else 0,
                        chat.created_at.isoformat(),
                        chat.updated_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise CacheError(f"chat {chat.id!r} already exists: {exc}") from exc
            for seq, turn in enumerate(chat.messages):
                conn.execute(
                    "INSERT INTO chat_messages (chat_id, seq, role, content, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (chat.id, seq, turn.role, turn.content, turn.created_at.isoformat()),
                )

    def update(self, chat: Chat) -> None:
        """Overwrite chat metadata. Does not touch messages — use append_message."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE chats SET title = ?, pinned = ?, updated_at = ? WHERE id = ?",
                (
                    chat.title,
                    1 if chat.pinned else 0,
                    chat.updated_at.isoformat(),
                    chat.id,
                ),
            )

    def get(self, chat_id: str) -> Chat | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, title, pinned, created_at, updated_at FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
            if row is None:
                return None
            msgs = conn.execute(
                "SELECT role, content, created_at FROM chat_messages "
                "WHERE chat_id = ? ORDER BY seq ASC",
                (chat_id,),
            ).fetchall()
        return _row_to_chat(row, msgs)

    def list(self) -> list[Chat]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, title, pinned, created_at, updated_at FROM chats "
                "ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
            chats: list[Chat] = []
            for r in rows:
                msgs = conn.execute(
                    "SELECT role, content, created_at FROM chat_messages "
                    "WHERE chat_id = ? ORDER BY seq ASC",
                    (r[0],),
                ).fetchall()
                chats.append(_row_to_chat(r, msgs))
        return chats

    def delete(self, chat_id: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            return cur.rowcount > 0

    def set_pinned(self, chat_id: str, pinned: bool) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE chats SET pinned = ?, updated_at = ? WHERE id = ?",
                (1 if pinned else 0, _utcnow_iso(), chat_id),
            )
            return cur.rowcount > 0

    def set_title(self, chat_id: str, title: str) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                (title, _utcnow_iso(), chat_id),
            )
            return cur.rowcount > 0

    def append_message(
        self,
        chat_id: str,
        role: Literal["system", "user", "assistant"],
        content: str,
    ) -> None:
        now = _utcnow_iso()
        with closing(self._connect()) as conn:
            exists = conn.execute(
                "SELECT 1 FROM chats WHERE id = ?", (chat_id,)
            ).fetchone()
            if exists is None:
                raise CacheError(f"chat {chat_id!r} does not exist")
            (next_seq,) = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM chat_messages WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            conn.execute(
                "INSERT INTO chat_messages (chat_id, seq, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, int(next_seq), role, content, now),
            )
            conn.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id)
            )


def _row_to_chat(row: tuple, msgs: list[tuple]) -> Chat:
    chat_id, title, pinned, created_at, updated_at = row
    return Chat(
        id=chat_id,
        title=title,
        pinned=bool(pinned),
        created_at=_parse_dt(created_at),
        updated_at=_parse_dt(updated_at),
        messages=[
            ChatTurn(role=r, content=c, created_at=_parse_dt(ts)) for r, c, ts in msgs
        ],
    )


__all__ = ["SqliteChatRepository"]
