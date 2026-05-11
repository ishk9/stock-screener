"""ChatService — persistent multi-turn LLM chat with portfolio-aware context.

Anchored on top of the existing :class:`LLMClient` (``chat()`` method) and
:class:`ChatRepository`. Responsibilities:

* CRUD over chat sessions (create/list/get/delete/pin/rename).
* Build an enriched system prompt for each turn (today's date, the user's
  current portfolio, plus any known tickers mentioned in the user message).
* Round-trip user/assistant turns to the repository so resuming a chat
  faithfully restores the LLM's context.

Kept deliberately lean: no streaming, no tool-calling — those can layer on
top later behind the same interface.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..core.errors import LLMError
from ..core.logging import get_logger
from ..core.result import Err, Ok, Result
from ..domain.entities.chat import Chat
from ..domain.entities.position import Position
from ..domain.ports.chat_repo import ChatRepository
from ..domain.ports.llm_client import LLMClient
from ..domain.ports.market_data import FundamentalsProvider, PriceProvider
from ..domain.ports.portfolio_repo import PortfolioRepository
from ..domain.ports.universe_repo import UniverseRepository
from ..domain.value_objects.chat import ChatMessage
from ..domain.value_objects.symbol import Symbol

log = get_logger(__name__)

_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&\-]{1,14}\b")
_MAX_AUTO_CONTEXT = 5
_PRICE_LOOKBACK = timedelta(days=7)
_LIVE_FETCH_CONCURRENCY = 8

# Keywords that signal the user is asking about live portfolio valuation /
# current prices. When any of these appears (and the user has positions), we
# pre-fetch live prices and inject them into the system prompt for that turn.
_PORTFOLIO_LIVE_KEYWORDS = {
    "value", "valuation", "worth", "total", "current", "now", "today",
    "portfolio", "holdings", "position", "positions",
    "pnl", "p&l", "gain", "gains", "loss", "losses", "profit", "return",
    "returns", "performance", "up", "down", "much", "price", "prices",
}

_BASE_SYSTEM = (
    "You are the AI assistant inside `ss`, a Python CLI for screening Indian "
    "equities (NSE/BSE) and managing the user's portfolio. Help the user with "
    "questions about Indian stocks, sectors, indices, valuation, technicals, "
    "macro context, and their own holdings.\n\n"
    "Rules:\n"
    "- Be concise, direct, and well-structured. Prefer short paragraphs and "
    "bullet points.\n"
    "- USE the data in the `Live data` block when present — that is fresh "
    "market data fetched seconds ago for this turn. Quote the numbers directly. "
    "Do NOT tell the user to run a CLI command when the answer is already in "
    "that block.\n"
    "- When answering ANY portfolio-valuation / P&L / 'what's it worth' "
    "question, you MUST first reproduce the per-position breakdown (one bullet "
    "per holding showing: qty, current price, current value, cost, P&L) before "
    "stating any total. This helps the user spot bad data immediately. Do not "
    "summarise to just a total.\n"
    "- If any holding shows `live price unavailable`, flag it explicitly.\n"
    "- Only suggest running a CLI command (e.g. `ss analyse RELIANCE`, "
    "`ss portfolio review`, `ss screen`) when the question genuinely needs "
    "data that is NOT in the context.\n"
    "- Always end any specific investment-leaning answer with: "
    "*Not investment advice.*"
)


@dataclass
class ChatService:
    chats: ChatRepository
    llm: LLMClient
    portfolio: PortfolioRepository | None = None
    universe: UniverseRepository | None = None
    prices: PriceProvider | None = None
    fundamentals: FundamentalsProvider | None = None

    # --------------------------- CRUD --------------------------- #
    def new_chat(self, title: str | None = None) -> Chat:
        chat = Chat(title=title or "New chat")
        self.chats.create(chat)
        return chat

    def get(self, chat_id: str) -> Chat | None:
        return self.chats.get(chat_id)

    def list(self) -> list[Chat]:
        return self.chats.list()

    def delete(self, chat_id: str) -> bool:
        return self.chats.delete(chat_id)

    def pin(self, chat_id: str) -> bool:
        return self.chats.set_pinned(chat_id, True)

    def unpin(self, chat_id: str) -> bool:
        return self.chats.set_pinned(chat_id, False)

    def rename(self, chat_id: str, title: str) -> bool:
        title = title.strip()
        if not title:
            return False
        return self.chats.set_title(chat_id, title)

    def resolve(self, ref: str) -> Chat | None:
        """Resolve a chat by id, by 1-based list-index, or by unambiguous id-prefix.

        Returns ``None`` if there is no match OR if the prefix is ambiguous
        (callers wanting to differentiate should use :meth:`resolve_detailed`).
        """
        match = self.resolve_detailed(ref)
        return match if isinstance(match, Chat) else None

    def resolve_detailed(self, ref: str) -> "Chat | list[Chat] | None":
        """Like :meth:`resolve` but returns the list of candidates when the
        prefix is ambiguous, or ``None`` when there is no match at all.
        """
        ref = ref.strip()
        if not ref:
            return None

        chat = self.chats.get(ref)
        if chat is not None:
            return chat

        if ref.isdigit():
            idx = int(ref) - 1
            chats = self.chats.list()
            if 0 <= idx < len(chats):
                return chats[idx]
            return None

        prefix = ref.lower()
        candidates = [c for c in self.chats.list() if c.id.lower().startswith(prefix)]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return candidates
        return None

    async def preview_context(self, user_text: str) -> str:
        """Build the system prompt that WOULD be sent for ``user_text`` — for
        debugging/inspection. No LLM call is made.
        """
        return await self._system_prompt(user_text)

    # --------------------------- send a turn --------------------------- #
    async def send(self, chat_id: str, user_text: str) -> Result[str, LLMError]:
        chat = self.chats.get(chat_id)
        if chat is None:
            return Err(LLMError(f"unknown chat: {chat_id!r}"))

        user_text = user_text.strip()
        if not user_text:
            return Err(LLMError("empty user message"))

        self.chats.append_message(chat_id, "user", user_text)
        if chat.title == "New chat":
            new_title = user_text.splitlines()[0][:60].rstrip()
            if new_title:
                self.chats.set_title(chat_id, new_title)

        wire = await self._build_wire_messages(chat, user_text)
        result = await self.llm.chat(wire)
        if isinstance(result, Err):
            log.warning("chat_llm_error", chat_id=chat_id, err=str(result.error))
            return result

        answer = result.value
        self.chats.append_message(chat_id, "assistant", answer)
        return Ok(answer)

    # --------------------------- prompt building --------------------------- #
    async def _build_wire_messages(
        self, chat: Chat, latest_user_text: str
    ) -> list[ChatMessage]:
        system_prompt = await self._system_prompt(latest_user_text)
        wire: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
        for turn in chat.messages:
            if turn.role == "system":
                continue
            wire.append(ChatMessage(role=turn.role, content=turn.content))
        wire.append(ChatMessage(role="user", content=latest_user_text))
        return wire

    async def _system_prompt(self, user_text: str) -> str:
        parts: list[str] = [_BASE_SYSTEM]

        now = datetime.now(timezone.utc)
        parts.append(f"\nToday is {now.strftime('%A, %d %b %Y')} (UTC).")

        positions = self._safe_list_positions()
        portfolio_block = self._portfolio_block(positions)
        if portfolio_block:
            parts.append("\nUser's portfolio (cost basis):\n" + portfolio_block)
        else:
            parts.append("\nUser's portfolio: (empty)")

        ticker_block = self._ticker_context_block(user_text)
        if ticker_block:
            parts.append(
                "\nKnown universe matches for tickers in the user's message:\n"
                + ticker_block
            )

        live_block = await self._live_data_block(user_text, positions, now)
        if live_block:
            parts.append("\nLive data (fetched just now):\n" + live_block)

        return "\n".join(parts)

    def _safe_list_positions(self) -> list[Position]:
        if self.portfolio is None:
            return []
        try:
            return self.portfolio.list()
        except Exception as exc:  # noqa: BLE001 — never let context-loading kill the chat
            log.warning("chat_portfolio_list_failed", err=str(exc))
            return []

    def _portfolio_block(self, positions: list[Position]) -> str:
        if not positions:
            return ""
        lines = []
        total_cost = 0.0
        for p in positions:
            total_cost += p.cost_basis
            lines.append(
                f"- {p.symbol.code} ({p.symbol.exchange.value}): "
                f"avg ₹{p.avg_buy_price:.2f} x {p.quantity:g} "
                f"(cost ₹{p.cost_basis:,.2f})"
                + (f", bought {p.bought_on.isoformat()}" if p.bought_on else "")
            )
        lines.append(f"- Total cost basis: ₹{total_cost:,.2f}")
        return "\n".join(lines)

    async def _live_data_block(
        self,
        user_text: str,
        positions: list[Position],
        now: datetime,
    ) -> str:
        if self.prices is None:
            return ""

        want_portfolio = bool(positions) and _mentions_portfolio_topic(user_text)
        ticker_mentions = (
            _extract_ticker_candidates(user_text) if self.universe is not None else []
        )
        # Resolve mentioned tickers to Symbols via the universe.
        mention_symbols: list[Symbol] = []
        if ticker_mentions and self.universe is not None:
            for code in ticker_mentions[:_MAX_AUTO_CONTEXT]:
                company = self.universe.get(code)
                if company is not None:
                    mention_symbols.append(company.symbol)

        if not want_portfolio and not mention_symbols:
            return ""

        # Build the set of symbols to fetch (de-duped).
        fetch_targets: dict[str, Symbol] = {}
        if want_portfolio:
            for p in positions:
                fetch_targets[p.symbol.code] = p.symbol
        for sym in mention_symbols:
            fetch_targets[sym.code] = sym

        latest_prices = await self._fetch_latest_prices(list(fetch_targets.values()))

        blocks: list[str] = []
        if want_portfolio:
            blocks.append(_portfolio_valuation_block(positions, latest_prices, now))
        if mention_symbols:
            mention_block = _mentioned_ticker_block(mention_symbols, latest_prices)
            if mention_block:
                blocks.append(mention_block)
        return "\n\n".join(b for b in blocks if b)

    async def _fetch_latest_prices(
        self, symbols: list[Symbol]
    ) -> dict[str, float | None]:
        """Return ``{symbol_code: latest_close_or_None}`` for each symbol.

        Errors are swallowed per-symbol so one missing feed never blocks the
        chat reply.
        """
        if not symbols or self.prices is None:
            return {}

        sem = asyncio.Semaphore(_LIVE_FETCH_CONCURRENCY)
        prices = self.prices

        async def _one(sym: Symbol) -> tuple[str, float | None]:
            async with sem:
                try:
                    res = await prices.get_prices(sym, _PRICE_LOOKBACK)
                except Exception as exc:  # noqa: BLE001
                    log.info("chat_price_fetch_exc", code=sym.code, err=str(exc))
                    return sym.code, None
            if isinstance(res, Err):
                log.info("chat_price_fetch_err", code=sym.code, err=str(res.error))
                return sym.code, None
            series = res.value
            if not series.points:
                return sym.code, None
            return sym.code, float(series.points[-1].close)

        results = await asyncio.gather(*(_one(s) for s in symbols))
        return dict(results)

    def _ticker_context_block(self, user_text: str) -> str:
        if self.universe is None:
            return ""
        candidates = _extract_ticker_candidates(user_text)
        if not candidates:
            return ""
        hits: list[str] = []
        for code in candidates[:_MAX_AUTO_CONTEXT]:
            company = self.universe.get(code)
            if company is None:
                continue
            sector = company.sector or "Unknown sector"
            mcap = (
                f"₹{company.market_cap_inr:.0f} cr"
                if company.market_cap_inr is not None
                else "market cap n/a"
            )
            bucket = (
                company.market_cap_bucket.value
                if company.market_cap_bucket is not None
                else "?"
            )
            hits.append(
                f"- {company.symbol.code}: {company.name} | {sector} | {mcap} | {bucket}"
            )
        return "\n".join(hits) if hits else ""


# ----------------- internal helpers ----------------- #


_STOPWORDS = {
    "I", "A", "AN", "THE", "AND", "OR", "BUT", "IS", "ARE", "WAS", "WERE", "BE",
    "TO", "OF", "IN", "ON", "AT", "BY", "FOR", "FROM", "WITH", "AS", "IT", "ITS",
    "MY", "ME", "WE", "YOU", "YOUR", "OUR", "THIS", "THAT", "THESE", "THOSE",
    "WHAT", "WHEN", "WHY", "HOW", "WHO", "DO", "DOES", "DID", "CAN", "COULD",
    "SHOULD", "WOULD", "WILL", "MAY", "MIGHT", "HAVE", "HAS", "HAD", "OK", "NO",
    "YES", "INR", "USD", "RS", "PE", "EPS", "ROE", "ROIC", "ATH", "ATL", "IPO",
    "NSE", "BSE", "SEBI", "RBI",
}


def _extract_ticker_candidates(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in _TICKER_RE.findall(text or ""):
        code = raw.upper()
        if code in _STOPWORDS or code in seen:
            continue
        if len(code) < 3:
            continue
        seen.add(code)
        out.append(code)
    return out


def _mentions_portfolio_topic(text: str) -> bool:
    """Heuristic: does ``text`` look like a portfolio-valuation question?"""
    words = re.findall(r"[A-Za-z&]+", (text or "").lower())
    return any(w in _PORTFOLIO_LIVE_KEYWORDS for w in words)


def _portfolio_valuation_block(
    positions: list[Position],
    latest_prices: dict[str, float | None],
    now: datetime,
) -> str:
    lines = [
        f"Portfolio valuation (last close, fetched at "
        f"{now.strftime('%Y-%m-%d %H:%M UTC')}):"
    ]
    total_cost = 0.0
    total_value = 0.0
    have_any_price = False
    for p in positions:
        cost = p.cost_basis
        total_cost += cost
        price = latest_prices.get(p.symbol.code)
        if price is None:
            lines.append(
                f"- {p.symbol.code}: qty {p.quantity:g} @ avg ₹{p.avg_buy_price:.2f} "
                f"= cost ₹{cost:,.2f} | live price unavailable"
            )
            continue
        have_any_price = True
        value = price * p.quantity
        total_value += value
        pnl_abs = value - cost
        pnl_pct = (pnl_abs / cost) * 100.0 if cost else 0.0
        sign = "+" if pnl_abs >= 0 else ""
        lines.append(
            f"- {p.symbol.code}: qty {p.quantity:g} @ ₹{price:,.2f} = "
            f"₹{value:,.2f} (cost ₹{cost:,.2f}, P&L {sign}₹{pnl_abs:,.2f} "
            f"/ {sign}{pnl_pct:.2f}%)"
        )

    if have_any_price:
        delta = total_value - total_cost
        delta_pct = (delta / total_cost) * 100.0 if total_cost else 0.0
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"- TOTAL: cost ₹{total_cost:,.2f}, current ₹{total_value:,.2f}, "
            f"P&L {sign}₹{delta:,.2f} ({sign}{delta_pct:.2f}%)"
        )
    else:
        lines.append(f"- TOTAL cost basis: ₹{total_cost:,.2f}; live prices unavailable")
    return "\n".join(lines)


def _mentioned_ticker_block(
    symbols: list[Symbol], latest_prices: dict[str, float | None]
) -> str:
    rows: list[str] = []
    for sym in symbols:
        price = latest_prices.get(sym.code)
        if price is None:
            continue
        rows.append(f"- {sym.code} ({sym.exchange.value}): last close ₹{price:,.2f}")
    if not rows:
        return ""
    return "Latest closes for tickers mentioned:\n" + "\n".join(rows)


__all__ = ["ChatService"]
