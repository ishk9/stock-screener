"""Unit tests for ``stock_screener.core.config``."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_screener.core import config as config_mod
from stock_screener.core.config import Config, LLMConfig
from stock_screener.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect config file/dir lookups to ``tmp_path`` and clear SS_* env."""
    cfg_dir = tmp_path / "ss-config"
    monkeypatch.setattr(config_mod, "_config_dir", lambda: cfg_dir)
    monkeypatch.setattr(config_mod, "_config_file", lambda: cfg_dir / "config.toml")
    for var in ("SS_LLM_API_KEY", "SS_LLM_PROVIDER", "SS_LLM_MODEL", "SS_LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)


def test_load_defaults_without_api_key_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="requires an API key"):
        Config.load()


def test_load_with_explicit_api_key_validates() -> None:
    cfg = Config.load(api_key="sk-XXX")
    assert cfg.llm.provider == "openai"
    assert cfg.llm.model == "gpt-4o-mini"
    assert cfg.llm.api_key == "sk-XXX"


def test_env_api_key_picked_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SS_LLM_API_KEY", "k")
    cfg = Config.load()
    assert cfg.llm.api_key == "k"


def test_env_provider_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SS_LLM_API_KEY", "k")
    cfg = Config.load()
    assert cfg.llm.provider == "anthropic"
    assert cfg.llm.api_key == "k"


def test_env_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SS_LLM_MODEL", "gpt-4o")
    cfg = Config.load(api_key="sk-XXX")
    assert cfg.llm.model == "gpt-4o"


def test_env_log_level_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SS_LOG_LEVEL", "DEBUG")
    cfg = Config.load(api_key="sk-XXX")
    assert cfg.log_level == "DEBUG"


def test_overrides_win_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SS_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SS_LLM_MODEL", "claude-x")
    cfg = Config.load(
        api_key="sk-XXX",
        overrides={"llm": {"provider": "openai", "model": "gpt-override"}},
    )
    assert cfg.llm.provider == "openai"
    assert cfg.llm.model == "gpt-override"


def test_missing_config_file_returns_defaults() -> None:
    cfg = Config.load(api_key="sk-XXX")
    assert cfg.llm.provider == "openai"


def test_malformed_toml_raises_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad = tmp_path / "config.toml"
    bad.write_text("this is = not [valid toml\n")
    monkeypatch.setattr(config_mod, "_config_file", lambda: bad)

    with pytest.raises(ConfigError, match="Invalid TOML"):
        Config.load(api_key="sk-XXX")


def test_llm_config_repr_does_not_leak_api_key() -> None:
    secret = "sk-supersecret-XXXXXXXXXXXX"
    cfg = LLMConfig(api_key=secret)
    rendered = repr(cfg)
    assert secret not in rendered
    assert "sk-" not in rendered
    assert "***" in rendered


def test_provider_stub_does_not_require_api_key() -> None:
    cfg = Config.load(overrides={"llm": {"provider": "stub"}})
    assert cfg.llm.provider == "stub"
    assert cfg.llm.api_key is None


def test_provider_ollama_does_not_require_api_key() -> None:
    cfg = Config.load(overrides={"llm": {"provider": "ollama"}})
    assert cfg.llm.provider == "ollama"
    assert cfg.llm.api_key is None


def test_unknown_provider_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="Unknown LLM provider"):
        Config.load(api_key="sk-XXX", overrides={"llm": {"provider": "nope"}})


def test_scoring_weights_above_one_raises() -> None:
    bad_weights = {"value": 0.5, "growth": 0.5, "quality": 0.5, "momentum": 0.5}
    with pytest.raises(ConfigError, match="Scoring weights"):
        Config.load(api_key="sk-XXX", overrides={"scoring": {"weights": bad_weights}})
