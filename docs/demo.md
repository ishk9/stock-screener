# `ss` — Usage Demo

A practical tour of the **Stock Screener** CLI: every command, every flag, every realistic workflow.

> **Disclaimer:** Educational tool. Output is not investment advice.

---

## 1. Install

```bash
# from a clone
pipx install --editable .
# or, in a regular venv
pip install -e ".[dev,openai]"
```

The console entry-point is `ss`:

```bash
ss --help
```

---

## 2. One-time setup

### 2.1 Provide an LLM API key

Three ways, highest precedence first:

```bash
# 1. per-invocation flag
ss screen --cap lg --api-key "sk-..."

# 2. environment variable (recommended)
export SS_LLM_API_KEY="sk-..."

# 3. persisted in ~/.ss/config.toml
ss config set --api-key "sk-..."
```

### 2.2 Pick an LLM vendor

Default is **OpenAI**. You can switch any time:

```bash
# Anthropic
ss config set --provider anthropic --model claude-3-5-sonnet-latest

# Google Gemini
ss config set --provider gemini --model gemini-1.5-pro

# Local Ollama (no key needed)
ss config set --provider ollama --model llama3.1:8b

# CI / dry-run (no real model)
ss config set --provider stub
```

### 2.3 Build the universe (run once a month)

```bash
ss universe refresh                  # full NSE pull + market-cap enrichment
ss universe refresh --no-enrich      # faster, no m-cap buckets
ss universe refresh --limit 200      # debug mode — just the first 200 tickers
ss universe show --cap lg --limit 25
```

---

## 3. The headline command — `ss screen`

```bash
ss screen --cap lg --top 10 --horizon long
```

### 3.1 Flags at a glance

| Flag | Short | Default | Purpose |
|---|---|---|---|
| `--cap` | `-c` | required | Market-cap bucket: `lg` / `md` / `sm` |
| `--top` | `-n` | 10 | How many recommendations to print |
| `--horizon` | `-H` | `long` | `short` (<6m) / `mid` (6–24m) / `long` (24m+) |
| `--profile` | `-p` | `composite` | Scoring style: `composite` / `value` / `growth` / `quality` / `momentum` |
| `--sector` | `-s` | — | Comma-sep sector whitelist (`IT,Pharma`) |
| `--exclude` | — | — | Comma-sep sector blacklist |
| `--max-risk` | — | — | Cap risk % (0–100) |
| `--min-risk` | — | — | Floor on risk % (filter OUT very-safe picks) |
| `--min-score` | — | — | Only show picks with score ≥ this (0–100) |
| `--max-score` | — | — | Only show picks with score ≤ this (0–100) |
| `--action` | — | — | Only show picks whose call is in `BUY,WAIT,AVOID` (comma-sep) |
| `--api-key` | — | — | One-shot LLM key |
| `--no-llm` | — | off | Quant-only run, skip the LLM analyst |
| `--format` | `-f` | `rich` | `rich` / `json` / `md` |
| `--explain` | — | off | Print full LLM thesis per pick |
| `--universe-limit` | — | — | Truncate universe (debug / cost-control) |
| `--verbose` | `-v` | off | Debug logs to stderr |

Each pick now also carries an explicit **call to action**:

| Action | Meaning |
|---|---|
| **BUY** | Score ≥ 65 and risk ≤ 50 (or HIGH conviction and score ≥ 60). Initiate now. |
| **WAIT** | Decent setup but conditions not actionable yet — keep on watchlist. |
| **AVOID** | Score < 40 or risk ≥ 75 — do not initiate. |

### 3.2 Realistic recipes

#### Conservative large-cap, long-horizon, value tilt
```bash
ss screen --cap lg --top 10 --horizon long --profile value --max-risk 35 --explain
```

#### Aggressive small-cap, growth tilt, exclude PSU & power
```bash
ss screen --cap sm --top 8 --horizon mid --profile growth \
          --exclude "Power,PSU Bank" --max-risk 75
```

#### Sector-focused mid-cap IT pick
```bash
ss screen --cap md --top 5 --sector "IT,Information Technology" \
          --horizon long --explain
```

#### Dividend / quality income basket
```bash
ss screen --cap lg --top 12 --profile quality --horizon long \
          --max-risk 25 --format md > my_picks.md
```

#### Cost-controlled run (no LLM, smaller universe)
```bash
ss screen --cap sm --top 5 --no-llm --universe-limit 200
```

#### Threshold filtering — only the actionable, only BUYs
```bash
ss screen --cap lg --top 20 --min-score 70 --max-risk 40 --action BUY
```

#### Find higher-risk / higher-reward setups (small caps with score ≥ 75 *and* risk ≥ 50)
```bash
ss screen --cap sm --top 10 --min-score 75 --min-risk 50
```

#### Borderline picks for a watchlist (50 ≤ score ≤ 65)
```bash
ss screen --cap md --top 15 --min-score 50 --max-score 65 --action WAIT
```

#### Pipe JSON into another tool
```bash
ss screen --cap lg --top 20 --format json | jq '.[] | {symbol, score, risk_pct}'
```

#### Persist to a Markdown journal
```bash
ss screen --cap md --top 10 --format md --explain >> journal/$(date +%F).md
```

### 3.3 What you get

A ranked table such as:

```
                     Top 10 — Large cap • long horizon
┏━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃  # ┃ Symbol     ┃ Sector       ┃ Score ┃ Convict.  ┃ Risk % ┃ Horizon ┃
┡━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│  1 │ TCS        │ IT           │ 82.4  │ HIGH     │ 18.20  │ long    │
│  2 │ HDFCBANK   │ Banking      │ 79.1  │ HIGH     │ 22.80  │ long    │
│  …                                                                    │
└────┴────────────┴──────────────┴───────┴──────────┴────────┴─────────┘
Not investment advice. For educational purposes only.
```

With `--explain` each pick is followed by a panel: `Thesis`, `Key risks`, `Catalysts`, `Suggested entry / stop / target`.

---

## 4. Single-ticker deep dive — `ss analyse`

```bash
ss analyse RELIANCE
ss analyse TCS.NS --horizon mid --format md > tcs.md
ss analyse BSE:RELIANCE --no-llm --verbose
```

The CLI accepts:
- `RELIANCE`               (default exchange = NSE)
- `RELIANCE.NS` / `TCS.BO` (Yahoo style)
- `NSE:RELIANCE` / `BSE:500325`

---

## 4b. Portfolio management & review — `ss portfolio`

You can persist your held positions and ask `ss` what to do with each one.
Storage is the same SQLite file that powers the cache (no extra setup).

### 4b.1 Sub-commands

| Command | Purpose |
|---|---|
| `ss portfolio add TICKER AVG_PRICE [--qty N] [--bought-on YYYY-MM-DD] [--notes ...]` | Record a holding |
| `ss portfolio remove TICKER` | Delete one holding |
| `ss portfolio show` | List all holdings (no network) |
| `ss portfolio review` | **Run a fresh analysis** and recommend `ADD` / `HOLD` / `TRIM` / `EXIT` per holding |
| `ss portfolio import file.csv [--replace]` | Bulk-load from CSV |
| `ss portfolio clear --yes` | Wipe all positions |

### 4b.2 Action vocabulary (held positions)

| Action | When |
|---|---|
| **ADD** | Strong score (≥ 65) with risk ≤ 55 — average down/up, the thesis is intact |
| **HOLD** | Neutral signal — no urgent action |
| **TRIM** | Up ≥ +50 % with weakening signal — book partial profit |
| **EXIT** | Score < 35, stop-loss breached (-25 % default), or risk ≥ 80 with negative P&L |

### 4b.3 Workflow examples

#### Add a few positions, see them, then review
```bash
ss portfolio add RELIANCE 2450 --qty 10 --bought-on 2024-09-15
ss portfolio add TCS 3680 --qty 5
ss portfolio add HDFCBANK 1480 --qty 20 --notes "core holding"
ss portfolio show
ss portfolio review --explain
```

#### Quick review without LLM (zero token cost)
```bash
ss portfolio review --no-llm
```

#### Mid-horizon review piped to a Markdown journal
```bash
ss portfolio review --horizon mid --format md --explain > "$(date +%F)-portfolio.md"
```

#### Get JSON for a dashboard
```bash
ss portfolio review --format json | jq '.[] | {symbol: .position.symbol.code, action, pnl_pct: .unrealised_pnl_pct}'
```

#### Bulk-load from CSV
`portfolio.csv`:
```
symbol,avg_price,qty,bought_on,notes
RELIANCE,2450,10,2024-09-15,core
TCS,3680,5,2024-08-12,
HDFCBANK,1480,20,,
```
```bash
ss portfolio import portfolio.csv --replace
ss portfolio review --explain
```

### 4b.4 What you get

```
                                Portfolio review
┏━━━━━━━━━━┳━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ Symbol   ┃ Qty┃ Avg Buy ┃ Current ┃   P&L % ┃ Action  ┃  Score ┃ Risk % ┃
┡━━━━━━━━━━╇━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│ RELIANCE │ 10 │ 2450.00 │ 2891.50 │ +18.02% │  ADD    │ 78.4   │  31.2  │
│ TCS      │  5 │ 3680.00 │ 3520.00 │  -4.35% │  HOLD   │ 62.1   │  29.4  │
│ HDFCBANK │ 20 │ 1480.00 │ 1142.00 │ -22.84% │  EXIT   │ 38.6   │  61.0  │
└──────────┴────┴─────────┴─────────┴─────────┴─────────┴────────┴────────┘
Portfolio  cost ₹61,800  value ₹74,055  P&L +12,255 (+19.83%)
```

With `--explain` each line gets a Panel containing the rationale and (if `--no-llm` not set) the full LLM thesis.

---

## 5. Universe management

```bash
ss universe refresh                      # rebuild listings + caps
ss universe show                         # full table (paged)
ss universe show --cap md --limit 50     # only mid-caps, top 50
```

---

## 6. Config inspection

```bash
ss config show                           # effective config (key masked)
ss config set --provider anthropic --model claude-3-5-sonnet-latest
```

The config file lives at `~/Library/Application Support/ss/config.toml` (macOS) or `~/.config/ss/config.toml` (Linux).

---

## 7. Output formats

### 7.1 Rich (default — interactive use)
Color-graded score, conviction badges, panels per pick when `--explain`.

### 7.2 JSON (machine-readable)
```bash
ss screen --cap lg --top 5 --format json
```
Returns an array of `Recommendation` objects suitable for `jq`, dashboards, alerting bots, etc.

### 7.3 Markdown (journaling, sharing)
```bash
ss screen --cap lg --top 10 --format md --explain > picks.md
```

---

## 8. Cost & speed knobs

| Knob | Effect |
|---|---|
| `--top N` | More picks → more LLM calls. The tool always sends `3×N` candidates to the LLM stage. |
| `--no-llm` | Pure-quant run, zero LLM cost. |
| `--universe-limit K` | Cap universe size for cheaper / faster runs. |
| `LLMConfig.max_rpm` / `max_tpm` | Hard rate-limits in `~/.ss/config.toml`. |
| Cache TTLs in config | A re-run within TTL costs zero API calls. |
| `--profile value/growth/...` | Same cost as composite — picks differ. |

A typical large-cap top-10 run with warm cache: **< 60s** and **< $0.05** of OpenAI tokens on `gpt-4o-mini`.

---

## 9. Common workflows

### Daily watchlist
```bash
ss screen --cap lg --top 10 --max-risk 30 --format md --explain \
   > "$HOME/watchlist/$(date +%F).md"
```

### Compare LLM vendors on the same universe
```bash
SS_LLM_PROVIDER=openai    ss screen --cap md --top 10 --format json > openai.json
SS_LLM_PROVIDER=anthropic ss screen --cap md --top 10 --format json > anthropic.json
diff <(jq -r '.[].symbol' openai.json) <(jq -r '.[].symbol' anthropic.json)
```

### Dry-run with the stub LLM (CI)
```bash
ss config set --provider stub
ss screen --cap lg --top 5 --universe-limit 50
```

### Cost-free quant-only run
```bash
ss screen --cap sm --top 20 --no-llm --profile growth
```

### Rebuild everything from scratch
```bash
rm -rf ~/.ss
ss universe refresh --limit 500
ss screen --cap lg --top 10
```

---

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `Universe is empty. Run \`ss universe refresh\`` | Run it once — see §2.3. |
| `LLM provider 'openai' requires an API key` | Set `--api-key`, `SS_LLM_API_KEY`, or `ss config set --api-key`. |
| `error: Unknown market-cap code 'large'` | Use `lg` / `md` / `sm`. |
| Slow first run | Cold cache. Subsequent runs are fast (TTL 7d on fundamentals, 24h on prices). |
| Provider 4xx / rate-limit | Retry with `-v`; the tool already does exponential back-off. |
| Want to wipe the cache | `rm ~/.ss/cache.db` (or your platform's equivalent). |

---

## 11. Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime error (provider down, LLM refusal, persistence) |
| 2 | User error (bad args, missing config) |

---

## 12. Pipelining ideas

```bash
# Slack notification on top large-cap pick
ss screen --cap lg --top 1 --format json |
   jq -r '.[0] | "Today: \(.symbol) score \(.score) risk \(.risk_pct)%"' |
   xargs -I {} curl -X POST -d '{"text":"{}"}' "$SLACK_WEBHOOK"

# Cron — daily report
0 9 * * 1-5 SS_LLM_API_KEY=$SECRET ss screen --cap lg --top 10 \
   --format md --explain > /var/reports/$(date +\%F).md
```

---

## 13. Disclaimer

This tool aggregates publicly available data and uses an LLM to narrate it. It does **not**:
- Constitute investment advice.
- Account for your personal financial situation.
- Place orders or interact with any brokerage.

You alone are responsible for your investment decisions.
