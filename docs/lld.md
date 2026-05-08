# Stock Screener (`ss`) — Low-Level Design

> Companion to [`system-architecture.md`](./system-architecture.md). This document fixes the **design patterns, SOLID applications, package layout and key contracts** so engineers can implement without re-deriving the rationale.

---

## 1. Guiding Principles

1. **SOLID, ruthlessly applied** (see §3).
2. **Hexagonal Architecture** — domain at the centre, I/O at the edge.
3. **Composition over inheritance** — patterns wired via DI, not class trees.
4. **Pure functions** for analytics; side-effects only at adapters.
5. **Fail loudly in dev, gracefully in prod** — Pydantic validation everywhere data crosses a boundary.
6. **Every boundary is an interface** — concrete classes are never imported across layers.
7. **The LLM never owns a number** — quantitative answers come from deterministic code; the LLM narrates and reasons.

---

## 2. Package Layout

```
stock_screener/
├── cli/                       # Presentation layer (Typer)
│   ├── app.py                 # Typer entrypoint registered as `ss`
│   ├── commands/
│   │   ├── screen.py
│   │   ├── analyse.py
│   │   ├── universe.py
│   │   └── config.py
│   └── progress.py            # Rich progress wiring
│
├── usecases/                  # Application layer (orchestrators)
│   ├── screen_companies.py
│   ├── analyse_ticker.py
│   └── refresh_universe.py
│
├── domain/                    # Pure business logic — no I/O
│   ├── entities/              # Company, FinancialStatement, PriceSeries
│   ├── value_objects/         # Money, Ratio, MarketCapBucket, Horizon
│   ├── analytics/
│   │   ├── strategies/        # ScoringStrategy implementations
│   │   ├── ratios.py
│   │   └── risk.py
│   ├── recommendation/
│   │   ├── fusion.py          # Quant + LLM fusion
│   │   └── policy.py          # Filtering by user constraints
│   └── ports/                 # ABCs / Protocols (interfaces)
│       ├── market_data.py
│       ├── llm_client.py
│       ├── universe_repo.py
│       ├── cache.py
│       └── renderer.py
│
├── infra/                     # Infrastructure adapters
│   ├── providers/
│   │   ├── nse_provider.py
│   │   ├── bse_provider.py
│   │   ├── yfinance_provider.py
│   │   ├── screener_in_provider.py
│   │   └── composite_provider.py
│   ├── llm/
│   │   ├── openai_client.py
│   │   ├── anthropic_client.py
│   │   ├── gemini_client.py
│   │   └── prompts/           # *.j2 templates, versioned
│   ├── cache/
│   │   ├── sqlite_cache.py
│   │   └── parquet_store.py
│   └── renderer/
│       ├── rich_renderer.py
│       ├── json_renderer.py
│       └── markdown_renderer.py
│
├── core/                      # Cross-cutting
│   ├── config.py
│   ├── logging.py
│   ├── errors.py
│   ├── retry.py
│   ├── circuit_breaker.py
│   ├── di.py                  # Lightweight container
│   └── events.py              # Pub/sub
│
└── tests/
    ├── unit/                  # Domain tests
    ├── integration/           # Adapter tests with VCR
    └── e2e/                   # CLI smoke tests
```

---

## 3. SOLID — How Each Principle Lands

### 3.1 Single Responsibility (SRP)
- `NseListingsParser` only parses NSE bhavcopy; it doesn't fetch, cache or score.
- `RatiosCalculator` computes ratios; it doesn't decide what's "good".
- `ScoreFusionService` merges quant + LLM; it doesn't fetch either.
- A class that requires a paragraph to describe is split.

### 3.2 Open/Closed (OCP)
- New data sources, LLM vendors, scoring strategies and output formats are added by **registering** a new implementation of an existing port — no edits to existing files.
- The DI container (`core/di.py`) reads a registry; users / tests inject their own.

### 3.3 Liskov Substitution (LSP)
- Every `MarketDataProvider` implementation must honour the contract: same return shape, same exception taxonomy, same idempotency guarantees. Verified by a shared **contract test suite** that every adapter inherits.

### 3.4 Interface Segregation (ISP)
- Instead of one fat `IDataSource`, we split into:
  - `FundamentalsProvider`
  - `PriceProvider`
  - `NewsProvider`
  - `CorporateActionsProvider`
- An adapter implements only what it actually supports; the orchestrator depends on the narrow port it needs.

### 3.5 Dependency Inversion (DIP)
- Use-cases depend on **`domain/ports/*`** abstractions only.
- Concrete adapters (`infra/*`) are wired in `core/di.py` at startup.
- Tests inject fakes (`InMemoryCache`, `StubLLMClient`) without monkey-patching.

---

## 4. Design Patterns Catalogue

The patterns below are intentional and load-bearing — not decoration. Each is mapped to a concrete responsibility.

### 4.1 Strategy
**Where**: scoring, market-cap bucketing, risk models, prompt selection.
**Why**: ranking philosophy is plural — value vs growth vs quality vs dividend.
**Shape**:
```python
class ScoringStrategy(Protocol):
    def score(self, snapshot: CompanySnapshot, horizon: Horizon) -> Score: ...

class ValueScoringStrategy: ...
class GrowthScoringStrategy: ...
class QualityScoringStrategy: ...
class CompositeScoringStrategy:  # also a Composite (§4.6)
    def __init__(self, parts: Sequence[tuple[ScoringStrategy, float]]): ...
```
Selected by `--profile value|growth|quality|composite`.

### 4.2 Factory / Abstract Factory
**Where**: building providers, LLM clients, renderers from config.
**Why**: keeps user code declarative — `--llm anthropic` produces an `AnthropicClient` without `if/elif` ladders in callers.
```python
class LLMClientFactory:
    _registry: dict[str, type[LLMClient]] = {}
    @classmethod
    def register(cls, name, impl): cls._registry[name] = impl
    @classmethod
    def create(cls, name, cfg) -> LLMClient: return cls._registry[name](cfg)
```

### 4.3 Adapter
**Where**: every external SDK is wrapped — `yfinance`, `openai`, `anthropic`, BSE/NSE HTTP endpoints.
**Why**: shields the domain from vendor churn and lets us substitute fakes in tests.

### 4.4 Repository
**Where**: `UniverseRepository`, `CompanyRepository`, `RunRepository`.
**Why**: hides whether data lives in SQLite, Parquet or a remote API. Use-cases ask the repo, not a DB.

### 4.5 Facade
**Where**: `MarketDataFacade` exposes a single `get_company_snapshot(ticker)` that internally orchestrates fundamentals + price + news providers and merges them.
**Why**: callers want one call, not four.

### 4.6 Composite
**Where**: `CompositeScoringStrategy`, `CompositeMarketDataProvider` (tries primary → fallback → cache).
**Why**: treats a group of providers/strategies as one — uniform interface.

### 4.7 Decorator
**Where**: applied to providers and LLM clients.
- `CachingProvider(inner)` — cache TTL.
- `RetryingProvider(inner)` — exponential back-off.
- `CircuitBreakerProvider(inner)` — fail-fast on outage.
- `LoggingLLMClient(inner)` — token + latency logs.
- `RedactingLLMClient(inner)` — PII scrub on prompts.
**Why**: cross-cutting concerns stack without polluting the adapter.

### 4.8 Chain of Responsibility
**Where**: the **screening pipeline**.
```
UniverseFilter → MarketCapFilter → SectorFilter → LiquidityFilter
              → QuantScorer       → ShortlistTrimmer
              → LLMAnalyst        → RecommendationFuser
              → ConstraintFilter  → Ranker
```
Each handler reads + mutates a `ScreeningContext`, decides whether to pass it on. Steps can be skipped or re-ordered via config.

### 4.9 Template Method
**Where**: `BaseLLMClient` defines `analyse(snapshot)` as `pack_context → render_prompt → call_model → parse_json → validate`. Sub-classes override only `call_model`.
**Why**: vendor differences are minimal; structure must be identical.

### 4.10 Builder
**Where**: `RecommendationBuilder`, `PromptBuilder`, `ReportBuilder`.
**Why**: outputs are large structured objects assembled from many sources; a fluent builder keeps construction readable and validates invariants on `.build()`.

### 4.11 Command
**Where**: each CLI sub-command (`ScreenCommand`, `AnalyseCommand`) is a `Command` object with `validate()` + `execute()`.
**Why**: enables uniform dry-run, telemetry, and future undo/replay.

### 4.12 Observer / Event Bus
**Where**: progress reporting, telemetry, cache invalidation.
- Publishers: `UniverseRefreshed`, `ProviderFailed`, `LLMCallCompleted`, `RecommendationProduced`.
- Subscribers: progress bar, structured logger, metrics sink.
**Why**: decouples long-running pipelines from the renderer.

### 4.13 Singleton (deliberate, scoped)
**Where**: `Config`, `Logger`, `DIContainer`, `MetricsRegistry` — process-scoped, immutable after bootstrap.
**Why**: there must be exactly one. Implemented via module-level instance, not the GoF anti-pattern.

### 4.14 Specification
**Where**: user constraints — `MaxRiskSpec(0.4)`, `SectorWhitelistSpec({"IT","Pharma"})`, `MarketCapSpec(LARGE)`.
**Why**: combinable (`spec_a & spec_b | spec_c`), testable, declarative; survives serialisation for run replay.

### 4.15 Value Object
**Where**: `Money(amount, currency)`, `Ratio`, `Pct`, `Horizon`, `Symbol`, `MarketCapBucket`, `Score`.
**Why**: type safety + invariants (`Pct` rejects > 100); `__eq__` by value; immutable (`frozen=True`).

### 4.16 Domain Service
**Where**: `RiskScoringService`, `RecommendationFusionService`.
**Why**: behaviour that doesn't naturally belong to any single entity.

### 4.17 Result / Either
**Where**: every adapter returns `Result[T, ProviderError]` instead of raising for expected failures.
**Why**: callers pattern-match outcomes; no surprises mid-pipeline.

### 4.18 Null Object
**Where**: `NullCache`, `NullMetrics` for tests / `--no-cache`.
**Why**: removes `if cache:` checks scattered through code.

### 4.19 Pipe / Pipeline (functional)
**Where**: analytics — `pipe(load, normalise, compute_ratios, score)`.
**Why**: deterministic, testable, parallelisable.

### 4.20 Dependency Injection (Container)
**Where**: a single `Container` builds the object graph at startup based on `Config`.
**Why**: the only place `infra/*` and `domain/*` meet. Swappable for tests via `Container.override(...)`.

---

## 5. Key Contracts (Ports)

```python
# domain/ports/market_data.py
class FundamentalsProvider(Protocol):
    async def get_fundamentals(self, symbol: Symbol) -> Result[Fundamentals, ProviderError]: ...

class PriceProvider(Protocol):
    async def get_prices(self, symbol: Symbol, lookback: timedelta) -> Result[PriceSeries, ProviderError]: ...

# domain/ports/llm_client.py
class LLMClient(Protocol):
    async def analyse(self, prompt: Prompt, schema: type[BaseModel]) -> Result[BaseModel, LLMError]: ...

# domain/ports/cache.py
class Cache(Protocol):
    def get(self, key: str) -> Optional[bytes]: ...
    def set(self, key: str, value: bytes, ttl: timedelta) -> None: ...

# domain/ports/renderer.py
class Renderer(Protocol):
    def render_screen(self, recs: Sequence[Recommendation], opts: RenderOpts) -> None: ...
```

The domain imports **only** these interfaces; adapters implement them in `infra/`.

---

## 6. Error Taxonomy

```
SSError (base)
├── ConfigError
├── ProviderError
│   ├── RateLimitError
│   ├── AuthError
│   ├── DataQualityError
│   └── UnavailableError
├── LLMError
│   ├── LLMRateLimitError
│   ├── LLMSchemaError
│   └── LLMRefusalError
├── CacheError
└── RenderError
```
Every adapter maps vendor exceptions to this hierarchy at the boundary.

---

## 7. Concurrency Model

- **Async-first**: all I/O ports are `async`. Domain functions stay synchronous and pure.
- **Bounded parallelism** via `asyncio.Semaphore` per provider.
- **Trio-style scopes** (`asyncio.TaskGroup` on 3.11+) so a partial failure cancels siblings cleanly.
- The LLM call is the most expensive step — batched per provider's max parallel jobs.

---

## 8. Testing Strategy

| Layer | Test Type | Tools |
|---|---|---|
| Domain (analytics, fusion, specs) | Unit + Property-based | pytest, hypothesis |
| Adapters | Integration with recorded fixtures | pytest, vcrpy, respx |
| LLM clients | Schema contract + golden prompts | pytest, syrupy |
| CLI | E2E smoke | pytest, typer's `CliRunner` |
| Performance | Benchmark on cold/warm cache | pytest-benchmark |

A **shared contract test** (`tests/contracts/test_market_data_contract.py`) is parametrised across every `MarketDataProvider` so LSP can't silently break.

---

## 9. Configuration Schema (excerpt)

```toml
[llm]
provider = "openai"        # openai | anthropic | gemini | ollama
model    = "gpt-4o-mini"
api_key  = "${SS_LLM_API_KEY}"
max_rpm  = 60
max_tpm  = 200_000

[providers.fundamentals]
primary  = "screener_in"
fallback = ["tickertape", "yfinance"]

[cache]
backend = "sqlite"
path    = "~/.ss/cache.db"
ttl_listings_days   = 30
ttl_fundamentals_d  = 7
ttl_prices_h        = 24

[scoring]
default_profile = "composite"
weights = { value = 0.3, growth = 0.3, quality = 0.3, momentum = 0.1 }
```

---

## 10. Observability Hooks

- Every use-case emits `UseCaseStarted`, `UseCaseCompleted`, `UseCaseFailed` via the event bus.
- A `MetricsSubscriber` aggregates: provider latency p50/p95/p99, LLM token spend, cache hit-rate.
- `ss diagnose` prints the last run's full trace tree.

---

## 11. Anti-Patterns We Will Reject

- **God classes** like `StockScreener` that "do everything".
- **Hidden network calls** in `__init__` or property getters.
- **Thread-local globals** instead of explicit DI.
- **Mock-heavy unit tests** that test the mocks, not the code (we use fakes + contract tests).
- **String-typed enums** (`"large"`, `"LARGE"`, `"lg"` floating around) — use `MarketCapBucket`.
- **LLM-produces-the-number** — risk %, target price, score are always computed deterministically and only *narrated* by the LLM.
- **`try/except: pass`** — every catch must map to a typed `SSError` or be re-raised.

---

## 12. Worked Walk-Through — `ss screen --cap lg --top 10 --horizon long`

1. `cli/commands/screen.py` parses args → `ScreenCommand(payload)`.
2. `Container.resolve(ScreenCompaniesUseCase)` returns the wired use-case.
3. Use-case runs the **Chain of Responsibility**:
   1. `UniverseRepository.list(MarketCapSpec(LARGE))` → 100 symbols.
   2. `MarketDataFacade.snapshot_many(symbols)` (parallel, decorated with cache + retry + breaker).
   3. `CompositeScoringStrategy.score_all(snapshots, horizon=LONG)` → ranked list.
   4. Trim to top 30 (3× requested) → candidate set.
   5. `LLMAnalyst.batch_analyse(candidates)` (Template Method per vendor, structured JSON out).
   6. `RecommendationFusionService.fuse(scores, llm_outputs)` → `Recommendation[]`.
   7. `ConstraintFilter` applies `MaxRiskSpec` & user filters.
   8. `Ranker.top(10)`.
4. `RunRepository.save(run_id, recs, citations)`.
5. `RichRenderer.render_screen(recs)` — colour-coded table with risk %, horizon, conviction, summary.
6. Use-case emits `UseCaseCompleted`; CLI exits 0.

---

## 13. Summary Table — Pattern → Concern

| Concern | Pattern(s) |
|---|---|
| Pluggable data sources | Adapter, Factory, Composite, Decorator |
| Pluggable LLM | Adapter, Template Method, Factory |
| Cross-cutting (cache/retry/CB/log) | Decorator, Observer |
| Multi-step screening | Chain of Responsibility, Pipeline |
| User constraints | Specification |
| Output formats | Strategy (Renderer) |
| Object construction | Builder, Factory |
| Lifecycle / wiring | Dependency Injection, Singleton (scoped) |
| Robust error flow | Result/Either, typed error hierarchy |
| Type-safe primitives | Value Object |
| Scoring philosophies | Strategy, Composite |

This LLD is the contract for the implementation phase. Any deviation must be justified in a PR description and reflected back into this document.
