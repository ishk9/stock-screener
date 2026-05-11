"""Unit tests for ChatService (use-case layer)."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

import pytest

from stock_screener.core.errors import LLMError, ProviderError
from stock_screener.core.result import Err, Ok, Result
from stock_screener.domain.entities.position import Position
from stock_screener.domain.entities.price_series import PricePoint, PriceSeries
from stock_screener.domain.ports.llm_client import LLMRequest
from stock_screener.domain.value_objects.chat import ChatMessage
from stock_screener.domain.value_objects.market_cap import MarketCapBucket
from stock_screener.domain.value_objects.symbol import Exchange, Symbol
from stock_screener.infra.cache.sqlite_chat_repo import SqliteChatRepository
from stock_screener.infra.cache.sqlite_portfolio_repo import SqlitePortfolioRepository
from stock_screener.infra.cache.sqlite_universe_repo import SqliteUniverseRepo
from stock_screener.usecases.chat_service import (
    ChatService,
    _extract_ticker_candidates,
    _mentions_portfolio_topic,
)

from .conftest import make_company


class _RecordingLLM:
    """In-memory LLM that records every chat() call."""

    name = "fake"
    model = "fake-1"

    def __init__(self, reply: str = "ack", error: LLMError | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[list[ChatMessage]] = []

    async def analyse(self, request: LLMRequest, schema):  # pragma: no cover - unused
        raise NotImplementedError

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.5,
        max_tokens: int = 1024,
    ) -> Result[str, LLMError]:
        self.calls.append(list(messages))
        if self.error is not None:
            return Err(self.error)
        return Ok(self.reply)


@pytest.fixture
def chat_repo(tmp_path: Path) -> SqliteChatRepository:
    return SqliteChatRepository(path=tmp_path / "c.sqlite")


@pytest.fixture
def portfolio_repo(tmp_path: Path) -> SqlitePortfolioRepository:
    return SqlitePortfolioRepository(path=tmp_path / "p.sqlite")


@pytest.fixture
def universe_repo(tmp_path: Path) -> SqliteUniverseRepo:
    return SqliteUniverseRepo(path=tmp_path / "u.sqlite")


def test_new_chat_persists(chat_repo: SqliteChatRepository):
    llm = _RecordingLLM()
    svc = ChatService(chats=chat_repo, llm=llm)
    chat = svc.new_chat(title="Hello")
    assert chat.title == "Hello"
    fetched = svc.get(chat.id)
    assert fetched is not None
    assert fetched.id == chat.id


def test_resolve_by_id_and_by_index(chat_repo: SqliteChatRepository):
    llm = _RecordingLLM()
    svc = ChatService(chats=chat_repo, llm=llm)
    a = svc.new_chat(title="A")
    b = svc.new_chat(title="B")

    assert svc.resolve(a.id).id == a.id  # type: ignore[union-attr]
    # list ordering: pinned-first then updated desc; b is newest
    chats = svc.list()
    assert chats[0].id == b.id
    assert svc.resolve("1").id == b.id  # type: ignore[union-attr]
    assert svc.resolve("2").id == a.id  # type: ignore[union-attr]
    assert svc.resolve("99") is None
    assert svc.resolve("c-missing") is None
    assert svc.resolve("") is None


def test_pin_unpin_rename_delete(chat_repo: SqliteChatRepository):
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    chat = svc.new_chat()
    assert svc.pin(chat.id) is True
    assert svc.get(chat.id).pinned is True  # type: ignore[union-attr]
    assert svc.unpin(chat.id) is True
    assert svc.rename(chat.id, "renamed") is True
    assert svc.get(chat.id).title == "renamed"  # type: ignore[union-attr]
    assert svc.rename(chat.id, "  ") is False
    assert svc.delete(chat.id) is True
    assert svc.get(chat.id) is None


def test_send_records_user_assistant_and_calls_llm(chat_repo: SqliteChatRepository):
    llm = _RecordingLLM(reply="here's my answer")
    svc = ChatService(chats=chat_repo, llm=llm)
    chat = svc.new_chat()

    result = asyncio.run(svc.send(chat.id, "what about RELIANCE?"))
    assert isinstance(result, Ok)
    assert result.value == "here's my answer"

    fetched = svc.get(chat.id)
    assert fetched is not None
    assert [m.role for m in fetched.messages] == ["user", "assistant"]
    assert fetched.messages[0].content == "what about RELIANCE?"
    assert fetched.messages[1].content == "here's my answer"

    assert len(llm.calls) == 1
    wire = llm.calls[0]
    assert wire[0].role == "system"
    assert wire[-1].role == "user"
    assert wire[-1].content == "what about RELIANCE?"


def test_send_first_user_message_auto_titles(chat_repo: SqliteChatRepository):
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "What is your view on TCS?\nplease summarise."))
    refreshed = svc.get(chat.id)
    assert refreshed is not None
    assert refreshed.title == "What is your view on TCS?"


def test_send_does_not_overwrite_explicit_title(chat_repo: SqliteChatRepository):
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    chat = svc.new_chat(title="My fixed title")
    asyncio.run(svc.send(chat.id, "hi"))
    assert svc.get(chat.id).title == "My fixed title"  # type: ignore[union-attr]


def test_send_rejects_unknown_chat(chat_repo: SqliteChatRepository):
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    result = asyncio.run(svc.send("c-missing", "hi"))
    assert isinstance(result, Err)


def test_send_rejects_empty_message(chat_repo: SqliteChatRepository):
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    chat = svc.new_chat()
    result = asyncio.run(svc.send(chat.id, "   "))
    assert isinstance(result, Err)


def test_send_passes_through_llm_error(chat_repo: SqliteChatRepository):
    err = LLMError("boom")
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM(error=err))
    chat = svc.new_chat()
    result = asyncio.run(svc.send(chat.id, "hi"))
    assert isinstance(result, Err)
    assert result.error is err

    # User turn IS recorded, but no assistant turn (because LLM failed).
    fetched = svc.get(chat.id)
    assert fetched is not None
    assert [m.role for m in fetched.messages] == ["user"]


def test_send_history_is_replayed_to_llm(chat_repo: SqliteChatRepository):
    llm = _RecordingLLM(reply="2nd reply")
    svc = ChatService(chats=chat_repo, llm=llm)
    chat = svc.new_chat()

    asyncio.run(svc.send(chat.id, "first"))
    asyncio.run(svc.send(chat.id, "second"))

    wire_second_call = llm.calls[-1]
    # system, user(first), assistant(reply), user(second)
    assert wire_second_call[0].role == "system"
    assert wire_second_call[1].role == "user"
    assert wire_second_call[1].content == "first"
    assert wire_second_call[2].role == "assistant"
    assert wire_second_call[-1].role == "user"
    assert wire_second_call[-1].content == "second"


def test_system_prompt_embeds_portfolio(
    chat_repo: SqliteChatRepository,
    portfolio_repo: SqlitePortfolioRepository,
):
    portfolio_repo.upsert(
        Position(
            symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
            avg_buy_price=2500.0,
            quantity=10,
            bought_on=date(2024, 1, 5),
        )
    )
    llm = _RecordingLLM()
    svc = ChatService(chats=chat_repo, llm=llm, portfolio=portfolio_repo)
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "what next?"))
    system_msg = llm.calls[0][0].content
    assert "RELIANCE" in system_msg
    assert "2500.00" in system_msg


def test_system_prompt_embeds_universe_match(
    chat_repo: SqliteChatRepository,
    universe_repo: SqliteUniverseRepo,
):
    universe_repo.upsert_many(
        [make_company(code="TCS", name="Tata Consultancy", sector="IT", bucket=MarketCapBucket.LARGE)]
    )
    llm = _RecordingLLM()
    svc = ChatService(chats=chat_repo, llm=llm, universe=universe_repo)
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "any thoughts on TCS?"))
    system_msg = llm.calls[0][0].content
    assert "TCS" in system_msg
    assert "Tata Consultancy" in system_msg


def test_universe_match_skips_unknown_symbols(
    chat_repo: SqliteChatRepository,
    universe_repo: SqliteUniverseRepo,
):
    llm = _RecordingLLM()
    svc = ChatService(chats=chat_repo, llm=llm, universe=universe_repo)
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "how about XYZ123 the unknown?"))
    system_msg = llm.calls[0][0].content
    assert "Known universe matches" not in system_msg


def test_extract_ticker_candidates_filters_stopwords():
    candidates = _extract_ticker_candidates("How is RELIANCE doing? I think TCS is OK.")
    assert "RELIANCE" in candidates
    assert "TCS" in candidates
    assert "OK" not in candidates
    assert "I" not in candidates


def test_extract_ticker_candidates_dedupes_preserves_order():
    candidates = _extract_ticker_candidates("RELIANCE RELIANCE TCS INFY TCS")
    assert candidates == ["RELIANCE", "TCS", "INFY"]


# --------------------------------------------------------------------------- #
# prefix resolution
# --------------------------------------------------------------------------- #
def test_resolve_by_unambiguous_prefix(chat_repo: SqliteChatRepository):
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    chat = svc.new_chat(title="solo")
    # Take the first 4 chars of the id (c-xx) — strictly only one match.
    prefix = chat.id[:4]
    found = svc.resolve(prefix)
    assert found is not None
    assert found.id == chat.id


def test_resolve_detailed_returns_list_when_prefix_ambiguous(
    chat_repo: SqliteChatRepository,
):
    """Force two chats with a shared prefix and confirm we get the list back."""
    from stock_screener.domain.entities.chat import Chat

    chat_repo.create(Chat(id="c-abcdef", title="A"))
    chat_repo.create(Chat(id="c-abcxyz", title="B"))

    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    match = svc.resolve_detailed("c-abc")
    assert isinstance(match, list)
    assert {c.id for c in match} == {"c-abcdef", "c-abcxyz"}


def test_resolve_returns_none_for_unknown_prefix(chat_repo: SqliteChatRepository):
    svc = ChatService(chats=chat_repo, llm=_RecordingLLM())
    svc.new_chat()
    assert svc.resolve("c-zzzzzz") is None
    assert svc.resolve_detailed("c-zzzzzz") is None


def test_mentions_portfolio_topic_keyword_detection():
    assert _mentions_portfolio_topic("what is the total value of my portfolio?")
    assert _mentions_portfolio_topic("how much is my holdings worth now?")
    assert _mentions_portfolio_topic("current PnL please")
    assert not _mentions_portfolio_topic("explain ROCE in simple terms")
    assert not _mentions_portfolio_topic("")


# --------------------------------------------------------------------------- #
# live-data injection
# --------------------------------------------------------------------------- #
class _StubPriceProvider:
    name = "stub-prices"

    def __init__(self, prices: dict[str, float | None]) -> None:
        self._prices = prices
        self.calls: list[str] = []

    async def get_prices(self, symbol: Symbol, lookback: timedelta):
        self.calls.append(symbol.code)
        price = self._prices.get(symbol.code)
        if price is None:
            return Err(ProviderError(f"no price for {symbol.code}"))
        return Ok(
            PriceSeries.from_points(
                [
                    PricePoint(
                        on=date(2026, 5, 11),
                        open=price * 0.99,
                        high=price * 1.01,
                        low=price * 0.98,
                        close=price,
                        volume=1_000,
                    )
                ]
            )
        )


def test_live_portfolio_valuation_block_is_injected(
    chat_repo: SqliteChatRepository,
    portfolio_repo: SqlitePortfolioRepository,
):
    portfolio_repo.upsert(
        Position(
            symbol=Symbol(code="ARE&M", exchange=Exchange.NSE),
            avg_buy_price=1402.01,
            quantity=90,
        )
    )
    portfolio_repo.upsert(
        Position(
            symbol=Symbol(code="RELIANCE", exchange=Exchange.NSE),
            avg_buy_price=2500.0,
            quantity=10,
        )
    )
    prices = _StubPriceProvider({"ARE&M": 1559.05, "RELIANCE": 2890.50})
    llm = _RecordingLLM()
    svc = ChatService(
        chats=chat_repo, llm=llm, portfolio=portfolio_repo, prices=prices
    )
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "what is the total value of my portfolio?"))

    system = llm.calls[0][0].content
    assert "Live data (fetched" in system
    assert "ARE&M" in system
    assert "RELIANCE" in system
    # Live numbers actually computed (not just cost basis).
    assert "1,559.05" in system or "1559.05" in system
    assert "TOTAL" in system
    # Prices were fetched for both.
    assert set(prices.calls) == {"ARE&M", "RELIANCE"}


def test_live_block_skipped_when_no_keywords_match(
    chat_repo: SqliteChatRepository,
    portfolio_repo: SqlitePortfolioRepository,
):
    portfolio_repo.upsert(
        Position(
            symbol=Symbol(code="TCS", exchange=Exchange.NSE),
            avg_buy_price=3000.0,
            quantity=5,
        )
    )
    prices = _StubPriceProvider({"TCS": 3500.0})
    llm = _RecordingLLM()
    svc = ChatService(
        chats=chat_repo, llm=llm, portfolio=portfolio_repo, prices=prices
    )
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "explain dollar-cost averaging"))
    system = llm.calls[0][0].content
    assert "Live data (fetched" not in system
    assert prices.calls == []  # no fetch happened


def test_live_block_handles_missing_price_gracefully(
    chat_repo: SqliteChatRepository,
    portfolio_repo: SqlitePortfolioRepository,
):
    portfolio_repo.upsert(
        Position(
            symbol=Symbol(code="GHOST", exchange=Exchange.NSE),
            avg_buy_price=100.0,
            quantity=10,
        )
    )
    prices = _StubPriceProvider({"GHOST": None})
    llm = _RecordingLLM()
    svc = ChatService(
        chats=chat_repo, llm=llm, portfolio=portfolio_repo, prices=prices
    )
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "what's my portfolio worth?"))
    system = llm.calls[0][0].content
    assert "Live data (fetched" in system
    assert "live price unavailable" in system
    # No crash; total falls back to cost basis.
    assert "1,000.00" in system  # cost = 100 * 10


def test_live_block_for_mentioned_ticker_only(
    chat_repo: SqliteChatRepository,
    universe_repo: SqliteUniverseRepo,
):
    # No portfolio configured.
    universe_repo.upsert_many(
        [make_company(code="INFY", name="Infosys", sector="IT")]
    )
    prices = _StubPriceProvider({"INFY": 1825.50})
    llm = _RecordingLLM()
    svc = ChatService(
        chats=chat_repo, llm=llm, universe=universe_repo, prices=prices
    )
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "How much is INFY trading at right now?"))
    system = llm.calls[0][0].content
    assert "Latest closes for tickers mentioned" in system
    assert "INFY" in system
    assert "1,825.50" in system
    assert prices.calls == ["INFY"]


def test_live_block_absent_when_prices_provider_not_wired(
    chat_repo: SqliteChatRepository,
    portfolio_repo: SqlitePortfolioRepository,
):
    portfolio_repo.upsert(
        Position(
            symbol=Symbol(code="TCS", exchange=Exchange.NSE),
            avg_buy_price=3000.0,
            quantity=5,
        )
    )
    llm = _RecordingLLM()
    svc = ChatService(chats=chat_repo, llm=llm, portfolio=portfolio_repo)
    chat = svc.new_chat()
    asyncio.run(svc.send(chat.id, "what is my portfolio worth?"))
    system = llm.calls[0][0].content
    assert "Live data (fetched" not in system
