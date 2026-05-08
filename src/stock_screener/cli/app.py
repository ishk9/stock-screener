"""Typer entry-point for the `ss` command.

Sub-commands live in :mod:`stock_screener.cli.commands`.
"""

from __future__ import annotations

import typer

from .commands import analyse, config, screen, universe

app = typer.Typer(
    name="ss",
    help="AI-powered terminal screener for Indian-listed companies (NSE / BSE).",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

app.command("screen", help="Screen companies by market-cap bucket.")(screen.screen_cmd)
app.command("analyse", help="Deep-dive analysis on one ticker.")(analyse.analyse_cmd)
app.add_typer(universe.app, name="universe", help="Manage the company universe.")
app.add_typer(config.app, name="config", help="View / set configuration.")


def main() -> None:  # pragma: no cover - re-exported as console script
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
