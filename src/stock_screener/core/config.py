"""Hierarchical configuration loader.

Precedence (highest first):
    1. Explicit kwargs / CLI flags.
    2. Environment variables (``SS_*``).
    3. ``~/.ss/config.toml``.
    4. Built-in defaults.

Secrets (API keys) are never echoed in ``__repr__``.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

from .errors import ConfigError


def _config_dir() -> Path:
    return Path(user_config_dir("ss", "stock-screener"))


def _config_file() -> Path:
    return _config_dir() / "config.toml"


# --------------------------------------------------------------------------- #
# Sub-configs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class LLMConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    max_rpm: int = 60
    max_tpm: int = 200_000
    timeout_s: float = 60.0

    def __repr__(self) -> str:  # never leak the key
        masked = "***" if self.api_key else None
        return (
            f"LLMConfig(provider={self.provider!r}, model={self.model!r}, "
            f"api_key={masked}, max_rpm={self.max_rpm}, max_tpm={self.max_tpm})"
        )


@dataclass(frozen=True, slots=True)
class ProvidersConfig:
    fundamentals_primary: str = "yfinance"
    fundamentals_fallback: tuple[str, ...] = ("screener_in",)
    prices_primary: str = "yfinance"
    universe_source: str = "nse"
    max_concurrent_requests: int = 8


@dataclass(frozen=True, slots=True)
class CacheConfig:
    backend: str = "sqlite"
    path: Path = field(default_factory=lambda: _config_dir() / "cache.db")
    ttl_listings_days: int = 30
    ttl_fundamentals_days: int = 7
    ttl_prices_hours: int = 24
    ttl_news_hours: int = 1


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    default_profile: str = "composite"
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "value": 0.30,
            "growth": 0.30,
            "quality": 0.30,
            "momentum": 0.10,
        }
    )


@dataclass(frozen=True, slots=True)
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    log_level: str = "INFO"
    config_dir: Path = field(default_factory=_config_dir)

    # ----------------------------- loaders ----------------------------- #
    @classmethod
    def load(cls, *, api_key: str | None = None, overrides: dict[str, Any] | None = None) -> "Config":
        cfg = cls._from_file(_config_file())
        cfg = cfg._merge_env()
        if api_key:
            cfg = replace(cfg, llm=replace(cfg.llm, api_key=api_key))
        if overrides:
            cfg = cfg._merge_dict(overrides)
        cfg._validate()
        return cfg

    @classmethod
    def _from_file(cls, path: Path) -> "Config":
        if not path.exists():
            return cls()
        try:
            data = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
        return cls()._merge_dict(data)

    def _merge_env(self) -> "Config":
        env = os.environ
        llm = self.llm
        if (k := env.get("SS_LLM_API_KEY")) is not None:
            llm = replace(llm, api_key=k)
        if (p := env.get("SS_LLM_PROVIDER")) is not None:
            llm = replace(llm, provider=p)
        if (m := env.get("SS_LLM_MODEL")) is not None:
            llm = replace(llm, model=m)
        log_level = env.get("SS_LOG_LEVEL", self.log_level)
        return replace(self, llm=llm, log_level=log_level)

    def _merge_dict(self, data: dict[str, Any]) -> "Config":
        cfg = self
        if (llm := data.get("llm")) is not None:
            cfg = replace(cfg, llm=_merge_dataclass(cfg.llm, llm))
        if (prov := data.get("providers")) is not None:
            cfg = replace(cfg, providers=_merge_dataclass(cfg.providers, prov))
        if (cache := data.get("cache")) is not None:
            if "path" in cache and isinstance(cache["path"], str):
                cache = {**cache, "path": Path(cache["path"]).expanduser()}
            cfg = replace(cfg, cache=_merge_dataclass(cfg.cache, cache))
        if (sc := data.get("scoring")) is not None:
            cfg = replace(cfg, scoring=_merge_dataclass(cfg.scoring, sc))
        if (lvl := data.get("log_level")) is not None:
            cfg = replace(cfg, log_level=str(lvl))
        return cfg

    def _validate(self) -> None:
        valid_providers = {"openai", "anthropic", "gemini", "ollama", "stub"}
        if self.llm.provider not in valid_providers:
            raise ConfigError(
                f"Unknown LLM provider: {self.llm.provider!r}. "
                f"Choose one of {sorted(valid_providers)}."
            )
        if self.llm.provider != "stub" and not self.llm.api_key:
            # Ollama can be local — but openai/anthropic/gemini all need a key.
            if self.llm.provider != "ollama":
                raise ConfigError(
                    f"LLM provider {self.llm.provider!r} requires an API key. "
                    "Pass --api-key, set SS_LLM_API_KEY or run `ss config set --api-key ...`."
                )
        if not 0 < sum(self.scoring.weights.values()) <= 1.000_001:
            raise ConfigError(
                "Scoring weights must sum to a positive value <= 1.0; got "
                f"{sum(self.scoring.weights.values())!r}."
            )

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.cache.path.parent.mkdir(parents=True, exist_ok=True)


def _merge_dataclass(instance: Any, override: dict[str, Any]) -> Any:
    """Apply only known fields from a mapping onto a frozen dataclass."""
    known = {f for f in instance.__dataclass_fields__}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in override.items() if k in known}
    if not filtered:
        return instance
    return replace(instance, **filtered)


__all__ = ["Config", "LLMConfig", "ProvidersConfig", "CacheConfig", "ScoringConfig"]
