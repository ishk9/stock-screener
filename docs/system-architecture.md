# Stock Screener (`ss`) — System Architecture

> AI-powered terminal tool to discover, analyse and recommend Indian-listed companies (NSE/BSE) filtered by market capitalisation, with LLM-driven summaries, risk scoring and suggested investment horizons.

---

## 1. Goals & Non-Goals

### 1.1 Goals
- A single, ergonomic CLI binary `ss` that runs locally on the user's machine.
- Universe coverage: every company listed on **NSE + BSE** (≈ 5,000+ tickers).
- Filterable by market-cap bucket: `lg` (Large), `md` (Mid), `sm` (Small).
- Pull fundamentals, ratios, prices, corporate actions and qualitative news.
- Run a **deterministic quantitative screener** first, then a **non-deterministic LLM analyst** second.
- Output ranked recommendations with: thesis summary, risk %, suggested holding period, target price band, conviction level.
- Accept a user-supplied LLM API key at runtime (no SaaS lock-in).
- Be safe by default: paper-recommendations only, with a clear "not financial advice" disclaimer.

### 1.2 Non-Goals
- Live order execution / brokerage integration.
- Intraday / HFT signals.
- Portfolio management or P&L tracking (future scope).
- A web/GUI front-end.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                CLI (`ss`)                                │
│   ss screen --cap lg --top 10 --horizon long --api-key $OPENAI_KEY      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Application / Orchestrator                        │
│   (Use-cases: ScreenCompanies, AnalyseTicker, ExplainRecommendation)    │
└─────────────────────────────────────────────────────────────────────────┘
        │                │                │                │
        ▼                ▼                ▼                ▼
┌────────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────────┐
│  Universe  │   │  Data        │   │ Analytics  │   │     LLM      │
│  Service   │   │  Providers   │   │  Engine    │   │  Analyst     │
│ (NSE/BSE   │   │ (Fundamentals│   │ (Ratios,   │   │ (Summary,    │
│  listings) │   │  Prices,News)│   │  Scoring)  │   │  Risk, Thesis)│
└────────────┘   └──────────────┘   └────────────┘   └──────────────┘
        │                │                │                │
        └────────────────┴────────────────┴────────────────┘
                                    │
                                    ▼
                       ┌───────────────────────────┐
                       │   Caching & Persistence   │
                       │  (SQLite + on-disk JSON)  │
                       └───────────────────────────┘
                                    │
                                    ▼
                       ┌───────────────────────────┐
                       │    Reporter / Renderer    │
                       │ (Rich tables, JSON, MD)   │
                       └───────────────────────────┘
```

The design is a layered **Hexagonal (Ports & Adapters)** architecture: the core domain is independent of the data sources, the LLM vendor and the rendering surface.

---

## 3. Layered Component View

| Layer | Responsibility | Key Modules |
|---|---|---|
| **Presentation** | Parse CLI args, render output | `cli/`, `renderer/` |
| **Application** | Orchestrate use-cases, coordinate services | `usecases/` |
| **Domain** | Pure business rules (entities, value objects, scoring) | `domain/` |
| **Infrastructure** | I/O: HTTP, DB, file, LLM SDKs | `providers/`, `cache/`, `llm/` |
| **Cross-cutting** | Logging, config, errors, retry, telemetry | `core/` |

**Direction of dependencies**: Presentation → Application → Domain ← Infrastructure. The domain depends on **nothing**.

---

## 4. Component Breakdown

### 4.1 CLI Layer (`cli/`)
- Built on **Typer** (Click under the hood) for typed sub-commands and great UX.
- Sub-commands:
  - `ss screen --cap {lg|md|sm} [--top N] [--horizon short|mid|long] [--sector ...] [--exclude ...] [--max-risk %]`
  - `ss analyse <TICKER>` — deep dive on one company.
  - `ss watchlist add|remove|show`
  - `ss config set --api-key ... --provider openai|anthropic|...`
  - `ss universe refresh` — re-pull NSE/BSE listings.
- Long-running operations stream progress with **Rich** progress bars.

### 4.2 Configuration & Secrets (`core/config`)
- Hierarchical sources (highest precedence wins): CLI flag > env var > `~/.ss/config.toml` > defaults.
- API key passing supported via:
  1. `--api-key` flag.
  2. `SS_LLM_API_KEY` env var.
  3. Encrypted entry in `~/.ss/secrets` (using OS keyring when available).
- Never logged or echoed.

### 4.3 Universe Service (`domain/universe`)
- Maintains the list of tradable Indian equities.
- Sources: NSE bhavcopy / equity master, BSE equity list (with monthly refresh).
- Canonicalises symbols: `RELIANCE.NS`, `TCS.BO`, etc.
- Tags each ticker with: sector, industry, ISIN, listing exchange, market-cap bucket.
- Market-cap bucketing rule (SEBI-aligned, refreshed semi-annually):
  - **Large** = top 100 by m-cap.
  - **Mid** = next 150 (rank 101–250).
  - **Small** = rank 251 and beyond.

### 4.4 Data Providers (`providers/`)
Pluggable adapters behind a stable port `MarketDataProvider`:
- **Fundamentals**: Screener.in scrape (fallback), Tickertape, MoneyControl, EOD Historical Data, Alpha Vantage.
- **Prices / OHLCV**: Yahoo Finance (`yfinance`), NSE API.
- **Corporate Actions / Filings**: BSE/NSE announcements, SEBI EDGAR-equivalent.
- **News & Sentiment**: Google News RSS, Moneycontrol, optionally a paid newswire.
- All adapters return normalised DTOs; rate-limited and retried with exponential back-off.

### 4.5 Caching & Persistence (`cache/`)
- **SQLite** for structured data (companies, fundamentals, runs, recommendations).
- **On-disk JSON / Parquet** for raw provider snapshots.
- TTL policy:
  - Listings: 30 days.
  - Quarterly fundamentals: 7 days.
  - Prices: 1 day (or 15 min if `--live`).
  - News: 1 hour.
- **Idempotency keys** so a re-run within TTL costs zero API calls.

### 4.6 Analytics Engine (`domain/analytics`)
Deterministic, fully unit-tested pure-functional core. Computes:
- **Valuation**: P/E, P/B, EV/EBITDA, P/S, PEG.
- **Profitability**: ROE, ROCE, gross/operating/net margins, margin trend.
- **Growth**: 3y/5y revenue CAGR, EPS CAGR, profit growth.
- **Quality**: Debt/Equity, interest coverage, current ratio, accruals ratio, FCF/PAT, Piotroski F-score, Beneish M-score.
- **Momentum**: 1m/3m/6m/1y returns, distance from 52-week high.
- **Composite Score**: weighted by horizon (short / mid / long).

This produces a **shortlist** that the LLM then narrates — never the other way round. Numbers are *not* delegated to the LLM.

### 4.7 LLM Analyst (`llm/`)
- **Provider-agnostic** via the `LLMClient` port; concrete adapters for OpenAI, Anthropic, Gemini, local Ollama, Bedrock.
- Responsibilities:
  - **Qualitative summary**: business model, moat, recent news, management commentary.
  - **Risk narrative**: enumerates concrete risks (regulatory, leverage, customer concentration, geopolitical).
  - **Investment thesis**: 3–5 bullets aligned with the user's chosen horizon.
  - **Calibrated confidence**: model self-reports a 0–1 confidence; we re-scale.
- Strict **structured output** via JSON-schema function-calling — no free-form parsing.
- All prompts live in versioned templates under `llm/prompts/` and are A/B-trackable.
- Token-budgeting: a context packer trims financial tables to fit the model window.
- **Risk %** is computed by combining quantitative risk (volatility, beta, leverage, drawdown) with the LLM-extracted qualitative risk vector — the LLM never produces the final number alone.

### 4.8 Recommendation Engine (`domain/recommendation`)
Final fusion stage. Inputs: quantitative score, LLM thesis, user constraints (`--max-risk`, `--horizon`, `--sector`). Outputs an ordered list of `Recommendation` objects:

```text
{
  symbol, company, exchange, market_cap_bucket,
  score (0-100),
  conviction (LOW | MEDIUM | HIGH),
  risk_pct (0-100),
  suggested_horizon (SHORT | MID | LONG),
  entry_band, stop_loss, target,
  thesis_summary, key_risks, catalysts,
  data_freshness, citations
}
```

### 4.9 Reporter (`renderer/`)
- Default: Rich tables + colour-coded risk/score columns.
- `--format json` for piping into other tools.
- `--format md` for committing to a journal.
- `--explain` flag prints the full LLM thesis per pick.

---

## 5. Data Flow — `ss screen --cap lg --top 10`

```
1. CLI parses args, loads config + API key.
2. Orchestrator.execute(ScreenRequest):
   2.1 UniverseService.list(MarketCap.LARGE)        → ~100 tickers
   2.2 CacheLayer.hydrate(tickers)                  → fills hot data
   2.3 DataProviderRegistry.fetch_missing(...)      → parallel async I/O
   2.4 AnalyticsEngine.score_all(tickers, horizon)  → deterministic ranking
   2.5 take top-K by score (default K = top × 3)
   2.6 LLMAnalyst.batch_analyse(top_K)              → structured JSON
   2.7 RecommendationEngine.fuse(scores, llm)       → final top N
   2.8 PersistenceService.save_run(run_id, ...)
3. Renderer.render(top_N, format)
4. Exit.
```

Steps 2.3, 2.4 and 2.6 are parallelised with bounded concurrency (`asyncio` + semaphore).

---

## 6. Concurrency & Performance

- Provider calls: `asyncio` + `httpx`, max-concurrency configurable per provider.
- LLM calls: batched and rate-limited per the chosen vendor's TPM/RPM.
- CPU-bound scoring: vectorised with **pandas / numpy**.
- Cold full-universe screen target: **< 90 s on broadband** with warm cache; **< 8 min** cold.
- All I/O is cancellable (Ctrl-C cleans up pending HTTP and writes partial cache).

---

## 7. Observability

- **Structured JSON logs** via `structlog` (rotated under `~/.ss/logs/`).
- `--verbose` exposes provider URLs (with API keys redacted) and LLM token usage.
- Each run gets a UUID and is replayable from the cache.

---

## 8. Reliability & Resilience

- **Retry with jittered exponential back-off** on every external call (Tenacity).
- **Circuit breaker** per provider — stops hammering a flaky data source.
- **Graceful degradation**: if News provider is down, we still rank on fundamentals.
- **Schema validation** on every provider response (Pydantic) — bad data is quarantined, not propagated.
- **Cache fallback**: if all live providers fail, we serve stale data with a clear warning banner.

---

## 9. Security & Privacy

- API keys never persisted in plain text — OS keyring (`keyring` lib) when available.
- LLM prompts are scrubbed of any user PII before sending.
- All third-party SDKs are version-pinned and SBOM-tracked.
- Outbound traffic restricted to the configured providers (allow-list).

---

## 10. Disclaimer & Compliance

- Every output ends with a SEBI-aligned disclaimer: *"Not investment advice. For educational purposes only."*
- No automated order placement. No paid distribution of recommendations.

---

## 11. Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| Language | **Python 3.11+** | Best ecosystem for finance + LLMs |
| CLI | Typer + Rich | Typed commands, beautiful output |
| HTTP | httpx (async) | First-class async, HTTP/2 |
| Data | pandas, numpy, pyarrow | Vectorised analytics |
| Validation | Pydantic v2 | Fast, exhaustive schemas |
| Cache/DB | SQLite + Parquet | Zero-config local persistence |
| LLM SDKs | openai, anthropic, google-genai, litellm | Multi-vendor |
| Retry / CB | tenacity, purgatory | Battle-tested |
| Tests | pytest, hypothesis | Property-based for analytics |
| Packaging | uv / pipx | Fast install, isolated CLI |

---

## 12. Deployment & Distribution

- Distributed as a **pipx-installable** package: `pipx install stock-screener` exposes `ss`.
- Optional self-update: `ss update`.
- Single binary fallback via PyInstaller for non-Python users.
- No server component required — fully local.

---

## 13. Extensibility Hooks

Anything below can be added without touching the core:
- A new data provider → implement `MarketDataProvider`.
- A new LLM vendor → implement `LLMClient`.
- A new market-cap rule (e.g. micro-cap) → register a `MarketCapBucket`.
- A new scoring profile (value, growth, dividend) → register a `ScoringStrategy`.
- A new output format (HTML, PDF) → implement `Renderer`.

---

## 14. Roadmap

| Phase | Scope |
|---|---|
| **v0.1 (MVP)** | NSE universe, fundamentals + prices, large-cap screen, single LLM provider, table output |
| **v0.2** | BSE merge, mid + small cap, news/sentiment, JSON output, cache layer |
| **v0.3** | Multi-LLM, risk model v2, watchlists, persistent run history |
| **v0.4** | Sector tilts, factor profiles (value/growth/quality/momentum) |
| **v1.0** | Backtesting harness, portfolio constructor, alerting |

---

## 15. Out-of-Scope Risks (acknowledged)

- **Hallucinations** — mitigated by structured output + numerical checks done outside the LLM.
- **Survivorship bias** in backtests — addressed via point-in-time universe.
- **Provider TOS** — only providers whose terms allow programmatic use.
- **Indian market microstructure** (T+1 settlement, circuits) — handled by the price layer's metadata.
