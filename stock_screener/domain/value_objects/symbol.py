"""Canonicalised ticker symbols."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"

    @property
    def yahoo_suffix(self) -> str:
        return ".NS" if self is Exchange.NSE else ".BO"


@dataclass(frozen=True, slots=True)
class Symbol:
    """A canonical (ticker, exchange) pair.

    The ``code`` is the bare ticker (e.g. ``RELIANCE``), the ``exchange``
    encodes the listing venue. Use :py:meth:`yahoo` to get the Yahoo Finance
    string (``RELIANCE.NS``).
    """

    code: str
    exchange: Exchange

    def __post_init__(self) -> None:
        code = self.code.strip().upper()
        if not code:
            raise ValueError("Symbol code must be non-empty")
        if any(c.isspace() for c in code):
            raise ValueError(f"Symbol code must not contain whitespace: {self.code!r}")
        object.__setattr__(self, "code", code)

    @classmethod
    def parse(cls, raw: str) -> "Symbol":
        """Parse common forms: ``RELIANCE.NS``, ``TCS.BO``, ``NSE:RELIANCE``, ``RELIANCE``."""
        s = raw.strip().upper()
        if not s:
            raise ValueError("empty symbol")
        if ":" in s:
            ex, code = s.split(":", 1)
            return cls(code=code, exchange=Exchange(ex))
        if s.endswith(".NS"):
            return cls(code=s[:-3], exchange=Exchange.NSE)
        if s.endswith(".BO"):
            return cls(code=s[:-3], exchange=Exchange.BSE)
        return cls(code=s, exchange=Exchange.NSE)

    def yahoo(self) -> str:
        return f"{self.code}{self.exchange.yahoo_suffix}"

    def __str__(self) -> str:
        return self.yahoo()


__all__ = ["Exchange", "Symbol"]
