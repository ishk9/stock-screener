"""`ss universe ...` sub-commands."""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from ...core.config import Config
from ...core.di import make_default_container
from ...core.errors import SSError
from ...core.logging import configure_logging
from ...domain.ports.market_data import FundamentalsProvider
from ...domain.ports.universe_repo import UniverseRepository
from ...domain.value_objects.market_cap import MarketCapBucket
from ...infra.providers.nse_listings_provider import NseListingsProvider
from ...usecases.refresh_universe import RefreshRequest, RefreshUniverseUseCase

app = typer.Typer(name="universe", no_args_is_help=True)


@app.command("refresh", help="Pull NSE/BSE listings and rebuild market-cap buckets.")
def refresh(
    no_enrich: Annotated[
        bool,
        typer.Option("--no-enrich", help="Skip market-cap enrichment (faster, less accurate)."),
    ] = False,
    limit: Annotated[
        Optional[int],
        typer.Option("--limit", help="Cap number of tickers (for first-run / testing)."),
    ] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    configure_logging("DEBUG" if verbose else "INFO")
    config = Config.load(api_key=api_key)
    container = make_default_container(config)

    use_case = RefreshUniverseUseCase(
        listings=container.resolve(NseListingsProvider),
        fundamentals=container.resolve(FundamentalsProvider),
        repo=container.resolve(UniverseRepository),
    )
    try:
        resp = asyncio.run(
            use_case.execute(
                RefreshRequest(
                    enrich_market_cap=not no_enrich,
                    limit=limit,
                )
            )
        )
    except SSError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"Refreshed: {resp.count} companies persisted.")


@app.command("show", help="Show a slice of the persisted universe.")
def show(
    cap: Annotated[
        Optional[str], typer.Option("--cap", "-c", help="lg | md | sm")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 25,
) -> None:
    config = Config.load()
    container = make_default_container(config)
    repo = container.resolve(UniverseRepository)
    bucket = MarketCapBucket.from_short_code(cap) if cap else None
    companies = repo.list(bucket)[:limit]

    table = Table(title="Universe")
    table.add_column("Symbol")
    table.add_column("Name")
    table.add_column("Sector")
    table.add_column("Bucket")
    table.add_column("Rank", justify="right")
    table.add_column("M-Cap (₹ Cr)", justify="right")
    for c in companies:
        table.add_row(
            c.symbol.code,
            c.name or "",
            c.sector or "",
            (c.market_cap_bucket.value if c.market_cap_bucket else ""),
            str(c.market_cap_rank or ""),
            f"{(c.market_cap_inr or 0) / 1e7:,.0f}" if c.market_cap_inr else "",
        )
    Console().print(table)
    Console().print(f"[dim]Total: {repo.count()} | Showing: {len(companies)}[/dim]")
