"""SQLite-backed implementation of ``UniverseRepository``."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ...core.errors import CacheError
from ...domain.entities.company import Company
from ...domain.value_objects.market_cap import MarketCapBucket
from ...domain.value_objects.symbol import Exchange, Symbol

_COMPANIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    symbol_code TEXT NOT NULL,
    exchange TEXT NOT NULL,
    name TEXT NOT NULL,
    isin TEXT,
    sector TEXT,
    industry TEXT,
    market_cap_inr REAL,
    market_cap_bucket TEXT,
    market_cap_rank INTEGER,
    listing_date TEXT,
    PRIMARY KEY(symbol_code, exchange)
);
"""

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS universe_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_EXCHANGE_PREFERENCE = ("NSE", "BSE")


class SqliteUniverseRepo:
    """Persists the tradable Indian-equity universe in SQLite."""

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        try:
            self._conn = sqlite3.connect(
                self._path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.execute(_COMPANIES_SCHEMA)
            self._conn.execute(_META_SCHEMA)
        except sqlite3.Error as exc:
            raise CacheError(f"Failed to open universe repo at {self._path}: {exc}") from exc

    def upsert_many(self, companies: list[Company]) -> None:
        rows = [self._company_to_row(c) for c in companies]
        try:
            with self._conn:
                self._conn.execute("BEGIN")
                self._conn.executemany(
                    "INSERT INTO companies(symbol_code, exchange, name, isin, sector, "
                    "industry, market_cap_inr, market_cap_bucket, market_cap_rank, "
                    "listing_date) VALUES (?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(symbol_code, exchange) DO UPDATE SET "
                    "name=excluded.name, isin=excluded.isin, sector=excluded.sector, "
                    "industry=excluded.industry, market_cap_inr=excluded.market_cap_inr, "
                    "market_cap_bucket=excluded.market_cap_bucket, "
                    "market_cap_rank=excluded.market_cap_rank, "
                    "listing_date=excluded.listing_date",
                    rows,
                )
                self._conn.execute(
                    "INSERT INTO universe_meta(key, value) VALUES ('last_refreshed_at', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (datetime.now(timezone.utc).isoformat(),),
                )
        except sqlite3.Error as exc:
            raise CacheError(f"upsert_many failed: {exc}") from exc

    def list(self, bucket: MarketCapBucket | None = None) -> list[Company]:
        try:
            if bucket is None:
                cur = self._conn.execute(
                    "SELECT symbol_code, exchange, name, isin, sector, industry, "
                    "market_cap_inr, market_cap_bucket, market_cap_rank, listing_date "
                    "FROM companies ORDER BY market_cap_rank IS NULL, market_cap_rank, symbol_code"
                )
            else:
                cur = self._conn.execute(
                    "SELECT symbol_code, exchange, name, isin, sector, industry, "
                    "market_cap_inr, market_cap_bucket, market_cap_rank, listing_date "
                    "FROM companies WHERE market_cap_bucket = ? "
                    "ORDER BY market_cap_rank IS NULL, market_cap_rank, symbol_code",
                    (bucket.value,),
                )
            return [self._row_to_company(r) for r in cur.fetchall()]
        except sqlite3.Error as exc:
            raise CacheError(f"list failed: {exc}") from exc

    def get(self, code: str) -> Company | None:
        norm = code.strip().upper()
        try:
            cur = self._conn.execute(
                "SELECT symbol_code, exchange, name, isin, sector, industry, "
                "market_cap_inr, market_cap_bucket, market_cap_rank, listing_date "
                "FROM companies WHERE symbol_code = ?",
                (norm,),
            )
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            raise CacheError(f"get failed: {exc}") from exc
        if not rows:
            return None
        rows.sort(key=lambda r: _EXCHANGE_PREFERENCE.index(r[1]) if r[1] in _EXCHANGE_PREFERENCE else 99)
        return self._row_to_company(rows[0])

    def count(self) -> int:
        try:
            (n,) = self._conn.execute("SELECT COUNT(*) FROM companies").fetchone()
            return int(n)
        except sqlite3.Error as exc:
            raise CacheError(f"count failed: {exc}") from exc

    def last_refreshed_at(self) -> str | None:
        try:
            row = self._conn.execute(
                "SELECT value FROM universe_meta WHERE key = 'last_refreshed_at'"
            ).fetchone()
        except sqlite3.Error as exc:
            raise CacheError(f"last_refreshed_at failed: {exc}") from exc
        return None if row is None else str(row[0])

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    @staticmethod
    def _company_to_row(c: Company) -> tuple:
        return (
            c.symbol.code,
            c.symbol.exchange.value,
            c.name,
            c.isin,
            c.sector,
            c.industry,
            c.market_cap_inr,
            c.market_cap_bucket.value if c.market_cap_bucket else None,
            c.market_cap_rank,
            c.listing_date,
        )

    @staticmethod
    def _row_to_company(row: tuple) -> Company:
        (
            code,
            exchange,
            name,
            isin,
            sector,
            industry,
            market_cap_inr,
            market_cap_bucket,
            market_cap_rank,
            listing_date,
        ) = row
        bucket = MarketCapBucket(market_cap_bucket) if market_cap_bucket else None
        symbol = Symbol(code=code, exchange=Exchange(exchange))
        return Company(
            symbol=symbol,
            name=name,
            isin=isin,
            sector=sector,
            industry=industry,
            market_cap_inr=market_cap_inr,
            market_cap_bucket=bucket,
            market_cap_rank=market_cap_rank,
            listing_date=listing_date,
        )


__all__ = ["SqliteUniverseRepo"]
