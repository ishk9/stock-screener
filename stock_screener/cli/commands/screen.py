"""`ss screen` — the headline command."""

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
from ...domain.specifications import (
    HasMinimumDataSpec,
    MaxRiskSpec,
    SectorBlacklistSpec,
    SectorWhitelistSpec,
)
from ...domain.value_objects.horizon import Horizon
from ...domain.value_objects.market_cap import MarketCapBucket
from ...domain.value_objects.pct import Pct
from ...infra.cache.run_repo import RunRepo
from ...infra.renderer.factory import RendererFactory
from ...usecases.screen_companies import ScreenCompaniesUseCase, ScreenRequest


def screen_cmd(
    cap: Annotated[
        str,
        typer.Option("--cap", "-c", help="Market-cap bucket: lg | md | sm.", show_default=False),
    ],
    top: Annotated[int, typer.Option("--top", "-n", help="How many recommendations.")] = 10,
    horizon: Annotated[
        str, typer.Option("--horizon", "-H", help="short | mid | long")
    ] = "long",
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            "-p",
            help="Scoring profile: composite | value | growth | quality | momentum",
        ),
    ] = "composite",
    sector: Annotated[
        Optional[str],
        typer.Option("--sector", "-s", help="Comma-separated sector whitelist."),
    ] = None,
    exclude: Annotated[
        Optional[str],
        typer.Option("--exclude", help="Comma-separated sector blacklist."),
    ] = None,
    max_risk: Annotated[
        Optional[float],
        typer.Option("--max-risk", help="Maximum acceptable risk %% (0–100)."),
    ] = None,
    api_key: Annotated[
        Optional[str],
        typer.Option(
            "--api-key",
            help="LLM API key. Falls back to SS_LLM_API_KEY env or config file.",
        ),
    ] = None,
    no_llm: Annotated[bool, typer.Option("--no-llm", help="Skip LLM analysis.")] = False,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="rich | json | md")
    ] = "rich",
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Print full LLM thesis per pick."),
    ] = False,
    universe_limit: Annotated[
        Optional[int],
        typer.Option("--universe-limit", help="Cap how many tickers to fetch (debug)."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    configure_logging("DEBUG" if verbose else "INFO")
    try:
        bucket = MarketCapBucket.from_short_code(cap)
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

    snapshot_specs = HasMinimumDataSpec()
    if sector:
        snapshot_specs = snapshot_specs & SectorWhitelistSpec.of(sector.split(","))
    if exclude:
        snapshot_specs = snapshot_specs & SectorBlacklistSpec.of(exclude.split(","))
    rec_spec = MaxRiskSpec(Pct(max_risk)) if max_risk is not None else None

    universe = container.resolve(UniverseRepository)
    if universe.count() == 0:
        typer.echo(
            "Universe is empty. Run `ss universe refresh` once before screening.",
            err=True,
        )
        raise typer.Exit(1)

    scorer = CompositeScoringStrategy.make_default(weights=config.scoring.weights)
    if profile != "composite":
        scorer = CompositeScoringStrategy.make_default(
            weights={profile: 1.0} if profile in {"value", "growth", "quality", "momentum"} else config.scoring.weights
        )

    use_case = ScreenCompaniesUseCase(
        universe=universe,
        fundamentals=container.resolve(FundamentalsProvider),
        prices=container.resolve(PriceProvider),
        news=None,
        llm=None if no_llm else container.resolve(LLMClient),
        scorer=scorer,
    )

    request = ScreenRequest(
        bucket=bucket,
        top=top,
        horizon=horizon_vo,
        profile=profile,
        snapshot_spec=snapshot_specs,
        rec_spec=rec_spec,
        use_llm=not no_llm,
        universe_limit=universe_limit,
    )

    renderer: Renderer = RendererFactory.create(fmt)

    try:
        response = asyncio.run(use_case.execute(request))
    except SSError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    renderer.render_screen(response.recommendations, RenderOpts(explain=explain))

    run_repo = container.resolve(RunRepo)
    run_repo.save_run(
        run_id=f"screen-{bucket.value}-{int(response.duration_s * 1000) % 10**8}",
        command="screen",
        payload={
            "bucket": bucket.value,
            "top": top,
            "horizon": horizon_vo.value,
            "profile": profile,
        },
        recs=list(response.recommendations),
    )


__all__ = ["screen_cmd"]
