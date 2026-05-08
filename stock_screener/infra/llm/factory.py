"""Registry-based LLM client factory.

Each provider is registered as a lambda that lazy-imports its concrete
client, so installing a single vendor SDK is enough — the others stay
optional.
"""

from __future__ import annotations

from typing import Callable

from ...core.config import LLMConfig
from ...core.errors import ConfigError
from ...domain.ports.llm_client import LLMClient

_Constructor = Callable[[LLMConfig], LLMClient]


class LLMClientFactory:
    """Registers and constructs ``LLMClient`` adapters by name."""

    _registry: dict[str, _Constructor] = {}

    @classmethod
    def register(cls, name: str, ctor: _Constructor) -> None:
        cls._registry[name] = ctor

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._registry.pop(name, None)

    @classmethod
    def names(cls) -> list[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def create(cls, cfg: LLMConfig) -> LLMClient:
        if cfg.provider not in cls._registry:
            raise ConfigError(
                f"Unknown LLM provider: {cfg.provider!r}. "
                f"Registered: {cls.names()}"
            )
        return cls._registry[cfg.provider](cfg)


def _build_openai(cfg: LLMConfig) -> LLMClient:
    from .openai_client import OpenAIClient

    return OpenAIClient(api_key=cfg.api_key or "", model=cfg.model, timeout_s=cfg.timeout_s)


def _build_anthropic(cfg: LLMConfig) -> LLMClient:
    from .anthropic_client import AnthropicClient

    return AnthropicClient(
        api_key=cfg.api_key or "", model=cfg.model, timeout_s=cfg.timeout_s
    )


def _build_gemini(cfg: LLMConfig) -> LLMClient:
    from .gemini_client import GeminiClient

    return GeminiClient(api_key=cfg.api_key or "", model=cfg.model, timeout_s=cfg.timeout_s)


def _build_stub(_cfg: LLMConfig) -> LLMClient:
    from .stub_client import StubLLMClient

    return StubLLMClient()


LLMClientFactory.register("openai", _build_openai)
LLMClientFactory.register("anthropic", _build_anthropic)
LLMClientFactory.register("gemini", _build_gemini)
LLMClientFactory.register("stub", _build_stub)


__all__ = ["LLMClientFactory"]
