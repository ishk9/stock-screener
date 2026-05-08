"""`ss config ...` — view / set persisted configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import tomli_w
import tomllib
import typer
from rich import print as rprint

from ...core.config import Config

app = typer.Typer(name="config", no_args_is_help=True)


@app.command("show", help="Print current effective configuration.")
def show() -> None:
    cfg = Config.load()
    rprint({
        "llm": {
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
            "api_key": "***" if cfg.llm.api_key else None,
        },
        "providers": {
            "fundamentals_primary": cfg.providers.fundamentals_primary,
            "fundamentals_fallback": list(cfg.providers.fundamentals_fallback),
            "prices_primary": cfg.providers.prices_primary,
        },
        "cache": {
            "backend": cfg.cache.backend,
            "path": str(cfg.cache.path),
        },
        "scoring": {
            "default_profile": cfg.scoring.default_profile,
            "weights": cfg.scoring.weights,
        },
        "log_level": cfg.log_level,
    })


@app.command("set", help="Persist a config field to ~/.ss/config.toml.")
def set_field(
    api_key: Annotated[Optional[str], typer.Option("--api-key")] = None,
    provider: Annotated[Optional[str], typer.Option("--provider")] = None,
    model: Annotated[Optional[str], typer.Option("--model")] = None,
) -> None:
    cfg = Config.load()
    cfg.ensure_dirs()
    path: Path = cfg.config_dir / "config.toml"
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    data.setdefault("llm", {})
    if api_key is not None:
        data["llm"]["api_key"] = api_key
    if provider is not None:
        data["llm"]["provider"] = provider
    if model is not None:
        data["llm"]["model"] = model
    path.write_text(tomli_w.dumps(data))
    typer.echo(f"Wrote {path}")
