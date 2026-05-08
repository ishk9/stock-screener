"""Production wiring — the only module that knows about both domain and infra.

Builds a fully-decorated object graph from a :class:`Config`. Tests typically
construct partial graphs themselves rather than calling this.
"""

from __future__ import annotations

from datetime import timedelta

from .core.config import Config
from .core.di import Container
from .core.events import EventBus
from .domain.analytics.strategies.composite import CompositeScoringStrategy
from .domain.ports.cache import Cache
from .domain.ports.llm_client import LLMClient
from .domain.ports.market_data import FundamentalsProvider, PriceProvider
from .domain.ports.renderer import Renderer
from .domain.ports.universe_repo import UniverseRepository
from .infra.cache.run_repo import RunRepo
from .infra.cache.sqlite_cache import SqliteCache
from .infra.cache.sqlite_universe_repo import SqliteUniverseRepo
from .infra.llm.factory import LLMClientFactory
from .infra.providers.composite_provider import (
    CompositeFundamentalsProvider,
    CompositePriceProvider,
)
from .infra.providers.decorators import (
    CachingFundamentalsProvider,
    CachingPriceProvider,
    LoggingFundamentalsProvider,
    LoggingPriceProvider,
    RetryingFundamentalsProvider,
    RetryingPriceProvider,
)
from .infra.providers.nse_listings_provider import NseListingsProvider
from .infra.providers.registry import ProviderRegistry, default_registry
from .infra.renderer.factory import RendererFactory


def wire(container: Container, config: Config) -> None:
    """Populate the container with the production object graph."""
    config.ensure_dirs()
    bus = EventBus()
    container.register_instance(EventBus, bus)
    container.register_instance(Config, config)

    cache = SqliteCache(path=config.cache.path)
    container.register_instance(Cache, cache)

    universe_repo = SqliteUniverseRepo(path=config.cache.path)
    container.register_instance(UniverseRepository, universe_repo)

    run_repo = RunRepo(path=config.cache.path)
    container.register_instance(RunRepo, run_repo)

    registry = default_registry
    container.register_instance(ProviderRegistry, registry)

    primary_f = registry.make_fundamentals(config.providers.fundamentals_primary, config.providers)
    fallbacks_f = [
        registry.make_fundamentals(name, config.providers)
        for name in config.providers.fundamentals_fallback
        if name != config.providers.fundamentals_primary
    ]
    fundamentals: FundamentalsProvider = CompositeFundamentalsProvider(primary_f, *fallbacks_f, bus=bus)
    fundamentals = LoggingFundamentalsProvider(fundamentals, bus=bus)
    fundamentals = RetryingFundamentalsProvider(fundamentals)
    fundamentals = CachingFundamentalsProvider(
        fundamentals,
        cache=cache,
        ttl=timedelta(days=config.cache.ttl_fundamentals_days),
    )
    container.register_instance(FundamentalsProvider, fundamentals)

    primary_p = registry.make_price(config.providers.prices_primary, config.providers)
    prices: PriceProvider = CompositePriceProvider(primary_p, bus=bus)
    prices = LoggingPriceProvider(prices, bus=bus)
    prices = RetryingPriceProvider(prices)
    prices = CachingPriceProvider(
        prices, cache=cache, ttl=timedelta(hours=config.cache.ttl_prices_hours)
    )
    container.register_instance(PriceProvider, prices)

    container.register_instance(NseListingsProvider, NseListingsProvider())

    llm: LLMClient = LLMClientFactory.create(config.llm)
    container.register_instance(LLMClient, llm)

    scorer = CompositeScoringStrategy.make_default(weights=config.scoring.weights)
    container.register_instance(CompositeScoringStrategy, scorer)

    renderer: Renderer = RendererFactory.create("rich")
    container.register_instance(Renderer, renderer)


__all__ = ["wire"]
