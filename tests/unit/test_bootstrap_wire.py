"""Unit tests for ``stock_screener.bootstrap.wire``."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_screener.bootstrap import wire
from stock_screener.core.config import CacheConfig, Config, LLMConfig
from stock_screener.core.di import Container
from stock_screener.core.events import EventBus
from stock_screener.domain.analytics.strategies.composite import (
    CompositeScoringStrategy,
)
from stock_screener.domain.ports.cache import Cache
from stock_screener.domain.ports.llm_client import LLMClient
from stock_screener.domain.ports.market_data import (
    FundamentalsProvider,
    PriceProvider,
)
from stock_screener.domain.ports.portfolio_repo import PortfolioRepository
from stock_screener.domain.ports.renderer import Renderer
from stock_screener.domain.ports.universe_repo import UniverseRepository
from stock_screener.infra.cache.run_repo import RunRepo
from stock_screener.infra.llm.stub_client import StubLLMClient
from stock_screener.infra.providers.composite_provider import (
    CompositeFundamentalsProvider,
)
from stock_screener.infra.providers.decorators import (
    CachingFundamentalsProvider,
    LoggingFundamentalsProvider,
    RetryingFundamentalsProvider,
)
from stock_screener.infra.providers.nse_listings_provider import NseListingsProvider
from stock_screener.infra.providers.registry import ProviderRegistry
from stock_screener.infra.renderer.rich_renderer import RichRenderer


@pytest.fixture
def stub_config(tmp_path: Path) -> Config:
    return Config(
        llm=LLMConfig(provider="stub"),
        cache=CacheConfig(path=tmp_path / "cache.db"),
        config_dir=tmp_path,
    )


@pytest.fixture
def wired_container(stub_config: Config) -> Container:
    container = Container()
    wire(container, stub_config)
    return container


def test_all_expected_ports_are_registered(wired_container: Container) -> None:
    expected_ports: tuple[type, ...] = (
        Cache,
        EventBus,
        Config,
        UniverseRepository,
        PortfolioRepository,
        RunRepo,
        ProviderRegistry,
        FundamentalsProvider,
        PriceProvider,
        NseListingsProvider,
        LLMClient,
        Renderer,
        CompositeScoringStrategy,
    )
    for port in expected_ports:
        assert wired_container.has(port), f"missing binding for {port!r}"


def test_cache_path_parent_dir_is_created(stub_config: Config) -> None:
    container = Container()
    wire(container, stub_config)
    assert stub_config.cache.path.parent.exists()


def test_fundamentals_chain_walks_to_composite(wired_container: Container) -> None:
    f = wired_container.resolve(FundamentalsProvider)
    assert isinstance(f, CachingFundamentalsProvider)
    inner = f._inner
    assert isinstance(inner, RetryingFundamentalsProvider)
    inner = inner._inner
    assert isinstance(inner, LoggingFundamentalsProvider)
    inner = inner._inner
    assert isinstance(inner, CompositeFundamentalsProvider)


def test_llm_client_stub_provider_returns_stub(wired_container: Container) -> None:
    llm = wired_container.resolve(LLMClient)
    assert isinstance(llm, StubLLMClient)


def test_resolve_returns_same_instance(wired_container: Container) -> None:
    a = wired_container.resolve(FundamentalsProvider)
    b = wired_container.resolve(FundamentalsProvider)
    assert a is b
    cache_a = wired_container.resolve(Cache)
    cache_b = wired_container.resolve(Cache)
    assert cache_a is cache_b


def test_renderer_resolves_to_rich(wired_container: Container) -> None:
    renderer = wired_container.resolve(Renderer)
    assert isinstance(renderer, RichRenderer)
