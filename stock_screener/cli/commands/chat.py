"""`ss chat` — persistent multi-turn LLM chat about your portfolio and the market.

`ss chat` (no args) — start a new chat and drop into an interactive REPL.
Inside the REPL, slash-commands let you switch/pin/delete/rename without
re-running the CLI. The chat is persisted to SQLite, so you can come back
later with `ss chat resume <id>`.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ...core.config import Config
from ...core.di import make_default_container
from ...core.logging import configure_logging
from ...core.result import Err, Ok
from ...domain.entities.chat import Chat
from ...domain.ports.chat_repo import ChatRepository
from ...domain.ports.llm_client import LLMClient
from ...domain.ports.portfolio_repo import PortfolioRepository
from ...domain.ports.universe_repo import UniverseRepository
from ...usecases.chat_service import ChatService

try:  # Enable arrow-key history in input() on POSIX.
    import readline  # noqa: F401
except ImportError:  # pragma: no cover - Windows
    pass

console = Console()
app = typer.Typer(name="chat", invoke_without_command=True)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _build_service(api_key: Optional[str] = None, *, verbose: bool = False) -> ChatService:
    configure_logging("DEBUG" if verbose else "INFO")
    config = Config.load(api_key=api_key)
    container = make_default_container(config)
    return ChatService(
        chats=container.resolve(ChatRepository),
        llm=container.resolve(LLMClient),
        portfolio=container.resolve(PortfolioRepository),
        universe=container.resolve(UniverseRepository),
    )


def _resolve_or_die(service: ChatService, ref: str) -> Chat:
    match = service.resolve_detailed(ref)
    if isinstance(match, Chat):
        return match
    if isinstance(match, list):
        typer.echo(
            f"error: {ref!r} is ambiguous — {len(match)} chats match. Be more specific:",
            err=True,
        )
        for c in match:
            typer.echo(f"  {c.id}  {c.title}", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"error: no chat matches {ref!r} (try `ss chat list` to see ids and indexes).",
        err=True,
    )
    raise typer.Exit(1)


def _print_chat_header(chat: Chat) -> None:
    pin = "[yellow]pinned[/yellow] · " if chat.pinned else ""
    console.print(
        Panel.fit(
            f"[bold]{chat.title}[/bold]\n[dim]id: {chat.id} · {pin}"
            f"{chat.turn_count} turns · updated {chat.updated_at:%Y-%m-%d %H:%M}[/dim]",
            border_style="cyan",
        )
    )


def _print_assistant(text: str) -> None:
    console.print(Panel(Markdown(text), border_style="green", title="assistant"))


def _print_history(chat: Chat) -> None:
    if not chat.messages:
        console.print("[dim](no messages yet)[/dim]")
        return
    for turn in chat.messages:
        if turn.role == "system":
            continue
        style = "cyan" if turn.role == "user" else "green"
        console.print(
            Panel(
                Markdown(turn.content) if turn.role == "assistant" else turn.content,
                border_style=style,
                title=f"{turn.role} · {turn.created_at:%H:%M}",
            )
        )


# --------------------------------------------------------------------------- #
# `ss chat` — root: start a new chat and run the REPL
# --------------------------------------------------------------------------- #
@app.callback(invoke_without_command=True)
def chat_root(
    ctx: typer.Context,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="LLM API key.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Open a new chat and start chatting.

    Sub-commands (`list`, `show`, `resume`, `delete`, `pin`, `unpin`, `rename`)
    are available; if you just run `ss chat` with no sub-command, a new chat is
    created and the REPL starts.
    """
    if ctx.invoked_subcommand is not None:
        return
    service = _build_service(api_key=api_key, verbose=verbose)
    chat = service.new_chat()
    _print_chat_header(chat)
    console.print(
        "[dim]Type your message and press Enter. Slash commands: /help, /list, "
        "/switch, /new, /pin, /unpin, /delete, /rename, /show, /clear, /exit.[/dim]"
    )
    _run_repl(service, chat)


# --------------------------------------------------------------------------- #
# `ss chat resume`
# --------------------------------------------------------------------------- #
@app.command("resume", help="Continue an existing chat by id or list index.")
def resume(
    chat_ref: Annotated[str, typer.Argument(help="Chat id (c-xxxxxx) or list index.")],
    api_key: Annotated[Optional[str], typer.Option("--api-key")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    service = _build_service(api_key=api_key, verbose=verbose)
    chat = _resolve_or_die(service, chat_ref)
    _print_chat_header(chat)
    _print_history(chat)
    _run_repl(service, chat)


# --------------------------------------------------------------------------- #
# `ss chat list`
# --------------------------------------------------------------------------- #
@app.command("list", help="Show all saved chats (pinned first, newest next).")
def list_chats() -> None:
    service = _build_service()
    chats = service.list()
    if not chats:
        console.print("[dim]No chats yet. Start one with `ss chat`.[/dim]")
        return
    table = Table(title="Chats")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Id", style="bold")
    table.add_column("Title")
    table.add_column("Pinned", justify="center")
    table.add_column("Turns", justify="right")
    table.add_column("Updated")
    for i, c in enumerate(chats, start=1):
        table.add_row(
            str(i),
            c.id,
            c.title,
            "[yellow]●[/yellow]" if c.pinned else "",
            str(c.turn_count),
            c.updated_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


# --------------------------------------------------------------------------- #
# `ss chat show`
# --------------------------------------------------------------------------- #
@app.command("show", help="Print the full transcript of a chat.")
def show(
    chat_ref: Annotated[str, typer.Argument(help="Chat id or list index.")],
) -> None:
    service = _build_service()
    chat = _resolve_or_die(service, chat_ref)
    _print_chat_header(chat)
    _print_history(chat)


# --------------------------------------------------------------------------- #
# `ss chat delete`
# --------------------------------------------------------------------------- #
@app.command("delete", help="Delete a chat (and all its messages).")
def delete(
    chat_ref: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    service = _build_service()
    chat = _resolve_or_die(service, chat_ref)
    if not yes:
        typer.confirm(f"Delete chat {chat.id} ({chat.title!r})?", abort=True)
    service.delete(chat.id)
    typer.echo(f"Deleted chat {chat.id}.")


# --------------------------------------------------------------------------- #
# `ss chat pin / unpin`
# --------------------------------------------------------------------------- #
@app.command("pin", help="Pin a chat to the top of the list.")
def pin(chat_ref: Annotated[str, typer.Argument()]) -> None:
    service = _build_service()
    chat = _resolve_or_die(service, chat_ref)
    service.pin(chat.id)
    typer.echo(f"Pinned {chat.id}.")


@app.command("unpin", help="Unpin a chat.")
def unpin(chat_ref: Annotated[str, typer.Argument()]) -> None:
    service = _build_service()
    chat = _resolve_or_die(service, chat_ref)
    service.unpin(chat.id)
    typer.echo(f"Unpinned {chat.id}.")


# --------------------------------------------------------------------------- #
# `ss chat rename`
# --------------------------------------------------------------------------- #
@app.command("rename", help="Rename a chat.")
def rename(
    chat_ref: Annotated[str, typer.Argument()],
    title: Annotated[str, typer.Argument(help="New title.")],
) -> None:
    service = _build_service()
    chat = _resolve_or_die(service, chat_ref)
    if not service.rename(chat.id, title):
        typer.echo("error: title cannot be empty.", err=True)
        raise typer.Exit(2)
    typer.echo(f"Renamed {chat.id} → {title!r}.")


# --------------------------------------------------------------------------- #
# REPL
# --------------------------------------------------------------------------- #
_HELP_TEXT = """\
Slash commands:
  /help                show this help
  /list                list all chats
  /switch <id|index>   switch to another chat
  /new [title]         start a new chat in this session
  /show [id|index]     print history (defaults to current chat)
  /pin                 pin the current chat
  /unpin               unpin the current chat
  /rename <title>      rename the current chat
  /delete <id|index>   delete a chat (current chat if omitted)
  /clear               clear the screen
  /exit                exit (Ctrl-D also works)

Anything that doesn't start with `/` is sent to the assistant.
"""


def _run_repl(service: ChatService, chat: Chat) -> None:
    current = chat
    while True:
        try:
            user_text = input(f"\n[{current.id}] you ▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye.[/dim]")
            return

        if not user_text:
            continue

        if user_text.startswith("/"):
            action = _handle_slash(service, current, user_text)
            if action is None:
                return  # user typed /exit
            if action is not current:
                current = action
                _print_chat_header(current)
            continue

        # Real user message → LLM round-trip.
        with console.status("[cyan]thinking…[/cyan]", spinner="dots"):
            result = asyncio.run(service.send(current.id, user_text))
        if isinstance(result, Err):
            console.print(f"[red]error:[/red] {result.error}")
            continue
        _print_assistant(result.value)
        refreshed = service.get(current.id)
        if refreshed is not None:
            current = refreshed


def _handle_slash(service: ChatService, current: Chat, raw: str) -> Chat | None:
    """Process a slash command. Returns:

    - the (possibly new) current chat on success,
    - the same ``current`` if the command was handled in-place,
    - ``None`` to signal exit.
    """
    parts = raw[1:].strip().split(maxsplit=1)
    if not parts:
        return current
    cmd, rest = parts[0].lower(), (parts[1] if len(parts) > 1 else "")

    if cmd in ("exit", "quit", "q"):
        console.print("[dim]bye.[/dim]")
        return None

    if cmd in ("help", "h", "?"):
        console.print(_HELP_TEXT)
        return current

    if cmd == "clear":
        console.clear()
        _print_chat_header(current)
        return current

    if cmd == "list":
        for i, c in enumerate(service.list(), start=1):
            marker = "● " if c.pinned else "  "
            here = " ← here" if c.id == current.id else ""
            console.print(
                f"{i:>2}. {marker}{c.id}  {c.title}  "
                f"[dim]({c.turn_count} turns, {c.updated_at:%Y-%m-%d %H:%M})[/dim]{here}"
            )
        return current

    if cmd == "switch":
        if not rest:
            console.print("[red]usage:[/red] /switch <id|index>")
            return current
        target = service.resolve(rest)
        if target is None:
            console.print(f"[red]no chat matches[/red] {rest!r}")
            return current
        _print_history(target)
        return target

    if cmd == "new":
        new = service.new_chat(title=rest or None)
        console.print(f"[green]Started new chat[/green] {new.id}")
        return new

    if cmd == "show":
        target = service.resolve(rest) if rest else current
        if target is None:
            console.print(f"[red]no chat matches[/red] {rest!r}")
            return current
        _print_history(target)
        return current

    if cmd == "pin":
        service.pin(current.id)
        console.print(f"[yellow]pinned[/yellow] {current.id}")
        refreshed = service.get(current.id)
        return refreshed or current

    if cmd == "unpin":
        service.unpin(current.id)
        console.print(f"[dim]unpinned[/dim] {current.id}")
        refreshed = service.get(current.id)
        return refreshed or current

    if cmd == "rename":
        if not rest:
            console.print("[red]usage:[/red] /rename <new title>")
            return current
        if service.rename(current.id, rest):
            console.print(f"[green]renamed →[/green] {rest!r}")
        refreshed = service.get(current.id)
        return refreshed or current

    if cmd == "delete":
        target = service.resolve(rest) if rest else current
        if target is None:
            console.print(f"[red]no chat matches[/red] {rest!r}")
            return current
        try:
            confirm = input(f"Delete {target.id} ({target.title!r})? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return current
        if confirm not in ("y", "yes"):
            console.print("[dim]cancelled[/dim]")
            return current
        service.delete(target.id)
        console.print(f"[red]deleted[/red] {target.id}")
        if target.id == current.id:
            new = service.new_chat()
            console.print(f"[green]Started new chat[/green] {new.id}")
            return new
        return current

    console.print(f"[red]unknown command[/red] /{cmd} — try /help")
    return current
