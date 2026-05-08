"""Domain ports — interfaces the application depends on.

Adapters in :mod:`stock_screener.infra` implement these. The domain itself
imports nothing from infra.
"""

from .cache import Cache
from .llm_client import LLMClient, LLMRequest
from .market_data import (
    CorporateActionsProvider,
    FundamentalsProvider,
    NewsProvider,
    PriceProvider,
)
from .portfolio_repo import PortfolioRepository
from .renderer import Renderer
from .universe_repo import UniverseRepository

__all__ = [
    "Cache",
    "CorporateActionsProvider",
    "FundamentalsProvider",
    "LLMClient",
    "LLMRequest",
    "NewsProvider",
    "PortfolioRepository",
    "PriceProvider",
    "Renderer",
    "UniverseRepository",
]
