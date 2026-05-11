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

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from ..core.errors import LLMError
from ..core.logging import get_logger
from ..core.result import Err, Ok, Result
from ..domain.entities.chat import Chat
from ..domain.ports.chat_repo import ChatRepository
from ..domain.ports.llm_client import LLMClient
from ..domain.ports.portfolio_repo import PortfolioRepository
from ..domain.ports.universe_repo import UniverseRepository
from ..domain.value_objects.chat import ChatMessage

log = get_logger(__name__)

_TICKER_RE = re.compile(r"\b[A-Z][A-Z0-9&\-]{1,14}\b")
_MAX_AUTO_CONTEXT = 5

_BASE_SYSTEM = (
    "You are the AI assistant inside `ss`, a Python CLI for screening Indian "
    "equities (NSE/BSE) and managing the user's portfolio. Help the user with "
    "questions about Indian stocks, sectors, indices, valuation, technicals, "
    "macro context, and their own holdings.\n\n"
    "Rules:\n"
    "- Be concise, direct, and well-structured. Prefer short paragraphs and "
    "bullet points.\n"
    "- When you are uncertain or the question requires live data you don't have, "
    "say so plainly and suggest the relevant `ss` command (e.g. `ss analyse "
    "RELIANCE`, `ss screen`, `ss portfolio review`).\n"
    "- Always end any specific investment-leaning answer with: "
    "*Not investment advice.*\n"
    "- You do NOT need to repeat the context block back to the user."
)


@dataclass
class ChatService:
    chats: ChatRepository
    llm: LLMClient
    portfolio: PortfolioRepository | None = None
    universe: UniverseRepository | None = None

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

        wire = self._build_wire_messages(chat, user_text)
        result = await self.llm.chat(wire)
        if isinstance(result, Err):
            log.warning("chat_llm_error", chat_id=chat_id, err=str(result.error))
            return result

        answer = result.value
        self.chats.append_message(chat_id, "assistant", answer)
        return Ok(answer)

    # --------------------------- prompt building --------------------------- #
    def _build_wire_messages(self, chat: Chat, latest_user_text: str) -> list[ChatMessage]:
        wire: list[ChatMessage] = [ChatMessage(role="system", content=self._system_prompt(latest_user_text))]
        for turn in chat.messages:
            if turn.role == "system":
                continue
            wire.append(ChatMessage(role=turn.role, content=turn.content))
        wire.append(ChatMessage(role="user", content=latest_user_text))
        return wire

    def _system_prompt(self, user_text: str) -> str:
        parts: list[str] = [_BASE_SYSTEM]

        today = datetime.now(timezone.utc).strftime("%A, %d %b %Y")
        parts.append(f"\nToday is {today} (UTC).")

        portfolio_block = self._portfolio_block()
        if portfolio_block:
            parts.append("\nUser's portfolio:\n" + portfolio_block)
        else:
            parts.append("\nUser's portfolio: (empty)")

        ticker_block = self._ticker_context_block(user_text)
        if ticker_block:
            parts.append("\nKnown universe matches for tickers in the user's message:\n" + ticker_block)

        return "\n".join(parts)

    def _portfolio_block(self) -> str:
        if self.portfolio is None:
            return ""
        positions = self.portfolio.list()
        if not positions:
            return ""
        lines = []
        for p in positions:
            lines.append(
                f"- {p.symbol.code} ({p.symbol.exchange.value}): "
                f"avg ₹{p.avg_buy_price:.2f} x {p.quantity:g}"
                + (f", bought {p.bought_on.isoformat()}" if p.bought_on else "")
            )
        return "\n".join(lines)

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


__all__ = ["ChatService"]
