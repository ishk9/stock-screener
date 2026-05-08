"""SQLite-backed implementation of :class:`PortfolioRepository`."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from ...core.errors import CacheError
from ...domain.entities.position import Position
from ...domain.value_objects.symbol import Exchange, Symbol


_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_positions (
    symbol_code   TEXT    NOT NULL,
    exchange      TEXT    NOT NULL,
    avg_buy_price REAL    NOT NULL CHECK (avg_buy_price > 0),
    quantity      REAL    NOT NULL CHECK (quantity > 0),
    bought_on     TEXT,
    notes         TEXT,
    PRIMARY KEY (symbol_code, exchange)
)
"""


class SqlitePortfolioRepository:
    """Stores user holdings in a single SQLite database (alongside the cache)."""

    def __init__(self, *, path: Path | str) -> None:
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self._path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        except sqlite3.Error as exc:
            raise CacheError(f"failed to open portfolio db at {self._path}: {exc}") from exc

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)

    # --------------------------- public API --------------------------- #
    def upsert(self, position: Position) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO portfolio_positions
                  (symbol_code, exchange, avg_buy_price, quantity, bought_on, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol_code, exchange) DO UPDATE SET
                  avg_buy_price = excluded.avg_buy_price,
                  quantity      = excluded.quantity,
                  bought_on     = excluded.bought_on,
                  notes         = excluded.notes
                """,
                (
                    position.symbol.code,
                    position.symbol.exchange.value,
                    float(position.avg_buy_price),
                    float(position.quantity),
                    position.bought_on.isoformat() if position.bought_on else None,
                    position.notes,
                ),
            )

    def remove(self, code: str) -> bool:
        code = code.strip().upper()
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "DELETE FROM portfolio_positions WHERE symbol_code = ?", (code,)
            )
            return cur.rowcount > 0

    def get(self, code: str) -> Position | None:
        code = code.strip().upper()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT symbol_code, exchange, avg_buy_price, quantity, bought_on, notes "
                "FROM portfolio_positions WHERE symbol_code = ? LIMIT 1",
                (code,),
            ).fetchone()
        return _row_to_position(row) if row else None

    def list(self) -> list[Position]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT symbol_code, exchange, avg_buy_price, quantity, bought_on, notes "
                "FROM portfolio_positions ORDER BY symbol_code"
            ).fetchall()
        return [_row_to_position(r) for r in rows]

    def clear(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM portfolio_positions")

    def count(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) FROM portfolio_positions").fetchone()
        return int(row[0]) if row else 0


def _row_to_position(row: tuple) -> Position:
    code, exchange, avg, qty, bought_on, notes = row
    return Position(
        symbol=Symbol(code=code, exchange=Exchange(exchange)),
        avg_buy_price=float(avg),
        quantity=float(qty),
        bought_on=date.fromisoformat(bought_on) if bought_on else None,
        notes=notes,
    )


__all__ = ["SqlitePortfolioRepository"]
