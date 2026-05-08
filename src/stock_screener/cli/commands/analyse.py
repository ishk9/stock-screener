"""`ss analyse <TICKER>` — single-ticker deep dive."""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

from ...core.config import Config
from ...core.di import Container, make_default_container
from ...core.errors import ConfigError, SSError
from ...core.logging import configure_logging
from ...domain.analytics.strategies.composite import CompositeScoringStrategy
from ...domain.ports.llm_client import LLMClient
from ...domain.ports.market_data import FundamentalsProvider, PriceProvider
from ...domain.ports.renderer import Renderer, RenderOpts
from ...domain.ports.universe_repo import UniverseRepository
from ...domain.value_objects.horizon import Horizon
from ...domain.value_objects.symbol import Symbol
from ...infra.renderer.factory import RendererFactory
from ...usecases.analyse_ticker import AnalyseRequest, AnalyseTickerUseCase


def analyse_cmd(
    ticker: Annotated[str, typer.Argument(help="Ticker e.g. RELIANCE, TCS.NS, BSE:RELIANCE")],
    horizon: Annotated[str, typer.Option("--horizon", "-H")] = "long",
    api_key: Annotated[
        Optional[str], typer.Option("--api-key", help="LLM API key.")
    ] = None,
    no_llm: Annotated[bool, typer.Option("--no-llm")] = False,
    fmt: Annotated[str, typer.Option("--format", "-f", help="rich | json | md")] = "rich",
    explain: Annotated[bool, typer.Option("--explain")] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    configure_logging("DEBUG" if verbose else "INFO")
    try:
        symbol = Symbol.parse(ticker)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    horizon_vo = Horizon(horizon.lower())
    try:
        config = Config.load(api_key=api_key)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    container: Container = make_default_container(config)
    use_case = AnalyseTickerUseCase(
        universe=container.resolve(UniverseRepository),
        fundamentals=container.resolve(FundamentalsProvider),
        prices=container.resolve(PriceProvider),
        llm=None if no_llm else container.resolve(LLMClient),
        scorer=CompositeScoringStrategy.make_default(weights=config.scoring.weights),
    )

    renderer: Renderer = RendererFactory.create(fmt)

    try:
        rec = asyncio.run(
            use_case.execute(AnalyseRequest(symbol=symbol, horizon=horizon_vo, use_llm=not no_llm))
        )
    except SSError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    renderer.render_analysis(rec, RenderOpts(explain=explain))


__all__ = ["analyse_cmd"]
