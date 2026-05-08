"""RefreshUniverseUseCase — pull NSE listings, enrich with market-cap, bucket and persist."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..core.events import EventBus, UniverseRefreshed
from ..core.logging import get_logger
from ..core.result import Err, Ok
from ..domain.entities.company import Company
from ..domain.ports.market_data import FundamentalsProvider
from ..domain.ports.universe_repo import UniverseRepository
from ..domain.value_objects.market_cap import MarketCapBucket
from ..infra.providers.nse_listings_provider import NseListingsProvider

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RefreshRequest:
    enrich_market_cap: bool = True
    max_concurrency: int = 16
    limit: int | None = None  # cap for first-run / debugging


@dataclass(frozen=True, slots=True)
class RefreshResponse:
    count: int


@dataclass
class RefreshUniverseUseCase:
    listings: NseListingsProvider
    fundamentals: FundamentalsProvider
    repo: UniverseRepository
    events: EventBus | None = None

    async def execute(self, request: RefreshRequest) -> RefreshResponse:
        log.info("universe.refresh.start")
        res = await self.listings.fetch_listings()
        if isinstance(res, Err):
            raise res.error
        companies = res.value
        if request.limit is not None:
            companies = companies[: request.limit]

        if request.enrich_market_cap:
            companies = await self._enrich_market_caps(companies, request.max_concurrency)
            companies = self._bucket_by_rank(companies)

        self.repo.upsert_many(companies)
        if self.events:
            self.events.publish(UniverseRefreshed(count=len(companies)))
        log.info("universe.refresh.done", count=len(companies))
        return RefreshResponse(count=len(companies))

    async def _enrich_market_caps(
        self, companies: list[Company], max_concurrency: int
    ) -> list[Company]:
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch(company: Company) -> Company:
            async with sem:
                res = await self.fundamentals.get_fundamentals(company.symbol)
            if isinstance(res, Ok):
                f = res.value
                shares = f.shares_outstanding or 0.0
                # Approximation when we lack a direct m-cap field: shares × latest_price.
                # The fundamentals provider already exposes pe/pb/ev/ebitda but not always raw m-cap;
                # leave the field None when we can't derive it cleanly.
                if shares > 0 and f.eps is not None and f.pe is not None and f.pe > 0:
                    price = f.eps * f.pe
                    market_cap = price * shares
                    return company.model_copy(update={"market_cap_inr": market_cap})
            return company

        results = await asyncio.gather(*(_fetch(c) for c in companies), return_exceptions=False)
        return list(results)

    def _bucket_by_rank(self, companies: list[Company]) -> list[Company]:
        with_caps = [c for c in companies if c.market_cap_inr is not None]
        without = [c for c in companies if c.market_cap_inr is None]
        with_caps.sort(key=lambda c: c.market_cap_inr or 0.0, reverse=True)
        out: list[Company] = []
        for rank, c in enumerate(with_caps, start=1):
            bucket = MarketCapBucket.from_rank(rank)
            out.append(c.model_copy(update={"market_cap_rank": rank, "market_cap_bucket": bucket}))
        # Companies without m-cap default to small cap, no rank.
        for c in without:
            out.append(c.model_copy(update={"market_cap_bucket": MarketCapBucket.SMALL}))
        return out


__all__ = ["RefreshUniverseUseCase", "RefreshRequest", "RefreshResponse"]
