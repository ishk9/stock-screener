"""SQLite-backed run history (for replay & diagnostics)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...core.errors import CacheError
from ...domain.entities.recommendation import Recommendation

_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    command TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""

_RECS_SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    run_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(run_id, rank)
);
"""


class RunRepo:
    """Records ``ss screen``/``ss analyse`` runs and their picks."""

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        try:
            self._conn = sqlite3.connect(
                self._path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.execute(_RUNS_SCHEMA)
            self._conn.execute(_RECS_SCHEMA)
        except sqlite3.Error as exc:
            raise CacheError(f"Failed to open run repo at {self._path}: {exc}") from exc

    def save_run(
        self,
        run_id: str,
        command: str,
        payload: dict[str, Any],
        recs: list[Recommendation],
    ) -> None:
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn:
                self._conn.execute("BEGIN")
                self._conn.execute(
                    "INSERT INTO runs(id, started_at, command, payload_json) VALUES (?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET started_at=excluded.started_at, "
                    "command=excluded.command, payload_json=excluded.payload_json",
                    (run_id, started_at, command, json.dumps(payload, default=str)),
                )
                self._conn.execute(
                    "DELETE FROM recommendations WHERE run_id = ?", (run_id,)
                )
                rows = [
                    (run_id, rank, rec.model_dump_json())
                    for rank, rec in enumerate(recs, start=1)
                ]
                if rows:
                    self._conn.executemany(
                        "INSERT INTO recommendations(run_id, rank, payload_json) "
                        "VALUES (?,?,?)",
                        rows,
                    )
        except sqlite3.Error as exc:
            raise CacheError(f"save_run failed: {exc}") from exc

    def last_run(self) -> dict[str, Any] | None:
        try:
            row = self._conn.execute(
                "SELECT id, started_at, command, payload_json FROM runs "
                "ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            run_id, started_at, command, payload_json = row
            recs_rows = self._conn.execute(
                "SELECT rank, payload_json FROM recommendations "
                "WHERE run_id = ? ORDER BY rank",
                (run_id,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise CacheError(f"last_run failed: {exc}") from exc

        recs = [Recommendation.model_validate_json(p) for _, p in recs_rows]
        return {
            "id": run_id,
            "started_at": started_at,
            "command": command,
            "payload": json.loads(payload_json),
            "recommendations": recs,
        }

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


__all__ = ["RunRepo"]
