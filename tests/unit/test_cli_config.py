"""CLI tests for ``ss config``."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stock_screener.cli.app import app
from stock_screener.core.config import (
    CacheConfig,
    Config,
    LLMConfig,
    ProvidersConfig,
    ScoringConfig,
)


def _make_config(tmp_path: Path, *, api_key: str | None = "sk-test") -> Config:
    return Config(
        llm=LLMConfig(provider="openai", model="gpt-4o-mini", api_key=api_key),
        providers=ProvidersConfig(),
        cache=CacheConfig(path=tmp_path / "cache.db"),
        scoring=ScoringConfig(),
        log_level="INFO",
        config_dir=tmp_path,
    )


@pytest.fixture
def runner(silence_logging: None) -> CliRunner:
    try:
        return CliRunner(mix_stderr=False)  # type: ignore[call-arg]
    except TypeError:
        return CliRunner()


@pytest.fixture
def patched_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    state = {"cfg": _make_config(tmp_path)}

    def _load(*, api_key: str | None = None, overrides: dict | None = None) -> Config:
        from dataclasses import replace

        cfg = state["cfg"]
        path = cfg.config_dir / "config.toml"
        if path.exists():
            data = tomllib.loads(path.read_text())
            llm_data = data.get("llm", {})
            cfg = replace(
                cfg,
                llm=replace(
                    cfg.llm,
                    provider=llm_data.get("provider", cfg.llm.provider),
                    model=llm_data.get("model", cfg.llm.model),
                    api_key=llm_data.get("api_key", cfg.llm.api_key),
                ),
            )
        if api_key:
            cfg = replace(cfg, llm=replace(cfg.llm, api_key=api_key))
        state["cfg"] = cfg
        return cfg

    monkeypatch.setattr(
        "stock_screener.cli.commands.config.Config.load",
        classmethod(lambda cls, **kwargs: _load(**kwargs)),
    )
    return state


def test_config_show_prints_keys(
    runner: CliRunner, patched_config, tmp_path: Path
) -> None:
    res = runner.invoke(app, ["config", "show"])
    assert res.exit_code == 0, res.stderr
    out = res.stdout
    for key in ("provider", "model", "cache", "scoring"):
        assert key in out


def test_config_show_masks_api_key(
    runner: CliRunner, patched_config, tmp_path: Path
) -> None:
    res = runner.invoke(app, ["config", "show"])
    assert res.exit_code == 0, res.stderr
    assert "sk-test" not in res.stdout
    assert "***" in res.stdout


def test_config_set_api_key_writes_toml(
    runner: CliRunner, patched_config, tmp_path: Path
) -> None:
    res = runner.invoke(
        app, ["config", "set", "--api-key", "sk-XXXX"]
    )
    assert res.exit_code == 0, res.stderr
    cfg_file = tmp_path / "config.toml"
    assert cfg_file.exists()
    contents = cfg_file.read_text()
    assert 'api_key = "sk-XXXX"' in contents


def test_config_set_provider_and_model(
    runner: CliRunner, patched_config, tmp_path: Path
) -> None:
    res = runner.invoke(
        app,
        [
            "config",
            "set",
            "--provider",
            "anthropic",
            "--model",
            "claude-3-5-sonnet-latest",
        ],
    )
    assert res.exit_code == 0, res.stderr
    cfg_file = tmp_path / "config.toml"
    data = tomllib.loads(cfg_file.read_text())
    assert data["llm"]["provider"] == "anthropic"
    assert data["llm"]["model"] == "claude-3-5-sonnet-latest"


def test_config_show_after_set_reflects_persisted(
    runner: CliRunner, patched_config, tmp_path: Path
) -> None:
    runner.invoke(
        app, ["config", "set", "--provider", "anthropic", "--model", "claude-3-5"]
    )
    res = runner.invoke(app, ["config", "show"])
    assert res.exit_code == 0, res.stderr
    assert "anthropic" in res.stdout
    assert "claude-3-5" in res.stdout
