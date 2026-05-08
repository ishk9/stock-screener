"""`ss portfolio ...` — manage and review held positions."""

from __future__ import annotations

import asyncio
import csv
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from ...core.config import Config
from ...core.di import make_default_container
from ...core.errors import SSError
from ...core.logging import configure_logging
from ...domain.analytics.strategies.composite import CompositeScoringStrategy
from ...domain.entities.position import Position
from ...domain.ports.llm_client import LLMClient
from ...domain.ports.market_data import FundamentalsProvider, PriceProvider
from ...domain.ports.portfolio_repo import PortfolioRepository
from ...domain.ports.renderer import RenderOpts
from ...domain.ports.universe_repo import UniverseRepository
from ...domain.value_objects.horizon import Horizon
from ...domain.value_objects.symbol import Symbol
from ...infra.renderer.factory import RendererFactory
from ...usecases.review_portfolio import ReviewPortfolioUseCase, ReviewRequest

app = typer.Typer(name="portfolio", no_args_is_help=True)


# --------------------------------------------------------------------------- #
# add
# --------------------------------------------------------------------------- #
@app.command("add", help="Record a held position.")
def add(
    ticker: Annotated[str, typer.Argument(help="Ticker, e.g. RELIANCE / TCS.NS / BSE:500325")],
    avg_price: Annotated[float, typer.Argument(help="Average buy price (₹).")],
    qty: Annotated[float, typer.Option("--qty", "-q", help="Quantity held.")] = 1.0,
    bought_on: Annotated[
        Optional[str],
        typer.Option("--bought-on", help="ISO date yyyy-mm-dd (optional)."),
    ] = None,
    notes: Annotated[Optional[str], typer.Option("--notes")] = None,
) -> None:
    config = Config.load()
    container = make_default_container(config)
    repo = container.resolve(PortfolioRepository)

    try:
        symbol = Symbol.parse(ticker)
        position = Position(
            symbol=symbol,
            avg_buy_price=avg_price,
            quantity=qty,
            bought_on=date.fromisoformat(bought_on) if bought_on else None,
            notes=notes,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    repo.upsert(position)
    typer.echo(
        f"Added {symbol.code} — qty {qty:g} @ ₹{avg_price:.2f} (cost ₹{position.cost_basis:,.2f})."
    )


# --------------------------------------------------------------------------- #
# remove
# --------------------------------------------------------------------------- #
@app.command("remove", help="Remove a position.")
def remove(
    ticker: Annotated[str, typer.Argument()],
) -> None:
    config = Config.load()
    container = make_default_container(config)
    repo = container.resolve(PortfolioRepository)
    symbol = Symbol.parse(ticker)
    if repo.remove(symbol.code):
        typer.echo(f"Removed {symbol.code}.")
    else:
        typer.echo(f"No position found for {symbol.code}.", err=True)
        raise typer.Exit(1)


# --------------------------------------------------------------------------- #
# clear
# --------------------------------------------------------------------------- #
@app.command("clear", help="Wipe all positions.")
def clear(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    if not yes:
        typer.confirm("This will delete all positions. Proceed?", abort=True)
    config = Config.load()
    container = make_default_container(config)
    container.resolve(PortfolioRepository).clear()
    typer.echo("Portfolio cleared.")


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #
@app.command("show", help="List all positions (no analysis, no network).")
def show() -> None:
    config = Config.load()
    container = make_default_container(config)
    repo = container.resolve(PortfolioRepository)
    positions = repo.list()
    if not positions:
        typer.echo("Portfolio is empty. Add positions with `ss portfolio add`.")
        return

    table = Table(title="Portfolio")
    table.add_column("Symbol", style="bold")
    table.add_column("Exchange")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Buy (₹)", justify="right")
    table.add_column("Cost (₹)", justify="right")
    table.add_column("Bought on")
    total = 0.0
    for p in positions:
        total += p.cost_basis
        table.add_row(
            p.symbol.code,
            p.symbol.exchange.value,
            f"{p.quantity:g}",
            f"{p.avg_buy_price:,.2f}",
            f"{p.cost_basis:,.2f}",
            p.bought_on.isoformat() if p.bought_on else "-",
        )
    Console().print(table)
    Console().print(f"[bold]Total cost basis:[/bold] ₹{total:,.2f}")


# --------------------------------------------------------------------------- #
# review
# --------------------------------------------------------------------------- #
@app.command("review", help="Run a fresh analysis and recommend ADD/HOLD/TRIM/EXIT per holding.")
def review(
    horizon: Annotated[str, typer.Option("--horizon", "-H")] = "long",
    api_key: Annotated[Optional[str], typer.Option("--api-key")] = None,
    no_llm: Annotated[bool, typer.Option("--no-llm")] = False,
    fmt: Annotated[str, typer.Option("--format", "-f")] = "rich",
    explain: Annotated[bool, typer.Option("--explain")] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    configure_logging("DEBUG" if verbose else "INFO")
    config = Config.load(api_key=api_key)
    container = make_default_container(config)
    horizon_vo = Horizon(horizon.lower())

    use_case = ReviewPortfolioUseCase(
        portfolio=container.resolve(PortfolioRepository),
        universe=container.resolve(UniverseRepository),
        fundamentals=container.resolve(FundamentalsProvider),
        prices=container.resolve(PriceProvider),
        llm=None if no_llm else container.resolve(LLMClient),
        scorer=CompositeScoringStrategy.make_default(weights=config.scoring.weights),
    )

    try:
        response = asyncio.run(
            use_case.execute(ReviewRequest(horizon=horizon_vo, use_llm=not no_llm))
        )
    except SSError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    renderer = RendererFactory.create(fmt)
    renderer.render_portfolio(response.reviews, RenderOpts(explain=explain))


# --------------------------------------------------------------------------- #
# import
# --------------------------------------------------------------------------- #
@app.command(
    "import",
    help="Bulk-load positions from a CSV with columns: symbol,avg_price[,qty,bought_on,notes].",
)
def import_csv(
    file: Annotated[Path, typer.Argument(exists=True, readable=True, dir_okay=False)],
    replace: Annotated[
        bool,
        typer.Option("--replace", help="Wipe existing portfolio before importing."),
    ] = False,
) -> None:
    config = Config.load()
    container = make_default_container(config)
    repo = container.resolve(PortfolioRepository)
    if replace:
        repo.clear()

    added = 0
    with file.open(newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "symbol" not in {f.lower() for f in reader.fieldnames}:
            typer.echo("error: CSV must have a 'symbol' column.", err=True)
            raise typer.Exit(2)
        for raw in reader:
            row = {k.lower().strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
            try:
                symbol = Symbol.parse(row["symbol"])
                position = Position(
                    symbol=symbol,
                    avg_buy_price=float(row["avg_price"]),
                    quantity=float(row.get("qty") or 1.0),
                    bought_on=date.fromisoformat(row["bought_on"]) if row.get("bought_on") else None,
                    notes=row.get("notes") or None,
                )
            except (KeyError, ValueError) as exc:
                typer.echo(f"skipping row {row}: {exc}", err=True)
                continue
            repo.upsert(position)
            added += 1

    typer.echo(f"Imported {added} positions from {file}.")
