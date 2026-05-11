"""CLI tests for ``ss chat`` (sub-commands + interactive REPL)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest
from typer.testing import CliRunner

from stock_screener.cli.app import app
from stock_screener.core.di import Container
from stock_screener.core.errors import LLMError
from stock_screener.core.result import Err, Ok, Result
from stock_screener.domain.ports.chat_repo import ChatRepository
from stock_screener.domain.ports.llm_client import LLMClient, LLMRequest
from stock_screener.domain.ports.portfolio_repo import PortfolioRepository
from stock_screener.domain.ports.universe_repo import UniverseRepository
from stock_screener.domain.value_objects.chat import ChatMessage
from stock_screener.infra.cache.sqlite_chat_repo import SqliteChatRepository
from stock_screener.infra.cache.sqlite_portfolio_repo import SqlitePortfolioRepository
from stock_screener.infra.cache.sqlite_universe_repo import SqliteUniverseRepo


class _ScriptedLLM:
    name = "scripted"
    model = "scripted-1"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
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
        if not self.replies:
            return Err(LLMError("out of scripted replies"))
        return Ok(self.replies.pop(0))


def _container(*, db_path: Path, llm: LLMClient) -> Container:
    container = Container()
    container.register_instance(ChatRepository, SqliteChatRepository(path=db_path))
    container.register_instance(
        PortfolioRepository, SqlitePortfolioRepository(path=db_path)
    )
    container.register_instance(UniverseRepository, SqliteUniverseRepo(path=db_path))
    container.register_instance(LLMClient, llm)
    return container


def _patch(monkeypatch: pytest.MonkeyPatch, container: Container) -> None:
    monkeypatch.setattr(
        "stock_screener.cli.commands.chat.make_default_container",
        lambda _config: container,
    )


@pytest.fixture
def runner(silence_logging: None) -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)  # type: ignore[call-arg]
    except TypeError:
        return CliRunner()


# --------------------------------------------------------------------------- #
# REPL
# --------------------------------------------------------------------------- #
def test_chat_repl_creates_chat_and_persists_turns(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "x.db"
    llm = _ScriptedLLM(["Hello! How can I help?"])
    container = _container(db_path=db, llm=llm)
    _patch(monkeypatch, container)

    result = runner.invoke(app, ["chat"], input="hi there\n/exit\n")
    assert result.exit_code == 0, result.stderr
    assert "Hello! How can I help?" in result.stdout

    chats = container.resolve(ChatRepository).list()
    assert len(chats) == 1
    msgs = chats[0].messages
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "hi there"
    assert msgs[1].content == "Hello! How can I help?"
    assert chats[0].title == "hi there"


def test_chat_repl_handles_slash_help(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _ScriptedLLM([])
    container = _container(db_path=tmp_path / "x.db", llm=llm)
    _patch(monkeypatch, container)
    result = runner.invoke(app, ["chat"], input="/help\n/exit\n")
    assert result.exit_code == 0
    assert "/switch" in result.stdout
    assert "/pin" in result.stdout
    # No LLM call should have been made.
    assert llm.calls == []


def test_chat_repl_new_creates_second_chat(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _ScriptedLLM(["A1"])
    container = _container(db_path=tmp_path / "x.db", llm=llm)
    _patch(monkeypatch, container)
    result = runner.invoke(app, ["chat"], input="first message\n/new\n/exit\n")
    assert result.exit_code == 0
    chats = container.resolve(ChatRepository).list()
    assert len(chats) == 2


def test_chat_repl_pin_and_rename(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _ScriptedLLM([])
    container = _container(db_path=tmp_path / "x.db", llm=llm)
    _patch(monkeypatch, container)
    result = runner.invoke(
        app, ["chat"], input="/pin\n/rename Project Notes\n/exit\n"
    )
    assert result.exit_code == 0
    chats = container.resolve(ChatRepository).list()
    assert chats[0].pinned is True
    assert chats[0].title == "Project Notes"


def test_chat_repl_delete_current_creates_new(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _ScriptedLLM([])
    container = _container(db_path=tmp_path / "x.db", llm=llm)
    _patch(monkeypatch, container)
    result = runner.invoke(app, ["chat"], input="/delete\ny\n/exit\n")
    assert result.exit_code == 0
    chats = container.resolve(ChatRepository).list()
    # original deleted, fresh one created
    assert len(chats) == 1


def test_chat_repl_delete_aborts_on_no(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _ScriptedLLM([])
    container = _container(db_path=tmp_path / "x.db", llm=llm)
    _patch(monkeypatch, container)
    result = runner.invoke(app, ["chat"], input="/delete\nn\n/exit\n")
    assert result.exit_code == 0
    chats = container.resolve(ChatRepository).list()
    assert len(chats) == 1


def test_chat_repl_handles_llm_error_without_crashing(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = _ScriptedLLM([])  # empty → returns Err
    container = _container(db_path=tmp_path / "x.db", llm=llm)
    _patch(monkeypatch, container)
    result = runner.invoke(app, ["chat"], input="hi\n/exit\n")
    assert result.exit_code == 0
    assert "error" in result.stdout.lower() or "Err" in result.stdout


# --------------------------------------------------------------------------- #
# sub-commands
# --------------------------------------------------------------------------- #
def test_chat_list_empty(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _container(db_path=tmp_path / "x.db", llm=_ScriptedLLM([]))
    _patch(monkeypatch, container)
    result = runner.invoke(app, ["chat", "list"])
    assert result.exit_code == 0
    assert "No chats" in result.stdout


def test_chat_list_after_repl(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "x.db"
    container = _container(db_path=db, llm=_ScriptedLLM(["ack"]))
    _patch(monkeypatch, container)

    # 1) Create a chat with one message.
    runner.invoke(app, ["chat"], input="ping\n/exit\n")
    # 2) List should now show one row.
    result = runner.invoke(app, ["chat", "list"])
    assert result.exit_code == 0
    assert "ping" in result.stdout


def test_chat_resume_unknown_exits_1(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = _container(db_path=tmp_path / "x.db", llm=_ScriptedLLM([]))
    _patch(monkeypatch, container)
    result = runner.invoke(app, ["chat", "resume", "c-nope"], input="/exit\n")
    assert result.exit_code == 1
    assert "no chat" in result.stderr.lower()


def test_chat_show_resume_pin_unpin_rename_delete_flow(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "x.db"
    container = _container(db_path=db, llm=_ScriptedLLM(["ok"]))
    _patch(monkeypatch, container)

    # create a chat with one user/assistant turn
    runner.invoke(app, ["chat"], input="hello world\n/exit\n")
    chats = container.resolve(ChatRepository).list()
    assert len(chats) == 1
    chat_id = chats[0].id

    show = runner.invoke(app, ["chat", "show", chat_id])
    assert show.exit_code == 0
    assert "hello world" in show.stdout

    pin = runner.invoke(app, ["chat", "pin", chat_id])
    assert pin.exit_code == 0
    assert container.resolve(ChatRepository).get(chat_id).pinned is True  # type: ignore[union-attr]

    unpin = runner.invoke(app, ["chat", "unpin", chat_id])
    assert unpin.exit_code == 0
    assert container.resolve(ChatRepository).get(chat_id).pinned is False  # type: ignore[union-attr]

    rename = runner.invoke(app, ["chat", "rename", chat_id, "Renamed Title"])
    assert rename.exit_code == 0
    assert container.resolve(ChatRepository).get(chat_id).title == "Renamed Title"  # type: ignore[union-attr]

    delete = runner.invoke(app, ["chat", "delete", chat_id, "--yes"])
    assert delete.exit_code == 0
    assert container.resolve(ChatRepository).get(chat_id) is None


def test_chat_show_by_index(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "x.db"
    container = _container(db_path=db, llm=_ScriptedLLM(["ok"]))
    _patch(monkeypatch, container)

    runner.invoke(app, ["chat"], input="testing 123\n/exit\n")
    result = runner.invoke(app, ["chat", "show", "1"])
    assert result.exit_code == 0
    assert "testing 123" in result.stdout
