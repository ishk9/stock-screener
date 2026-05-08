# Stock Screener (`ss`)

AI-powered terminal tool that screens Indian-listed companies (NSE / BSE) by market-cap bucket and produces ranked, LLM-explained investment ideas — with risk %, suggested holding period and a written thesis.

> **Disclaimer:** Educational tool. Not investment advice.

---

## Quick start

```bash
pipx install stock-screener            # or: pip install -e ".[dev,openai]"
export SS_LLM_API_KEY=sk-...           # your OpenAI / Anthropic / Gemini key
ss universe refresh                    # one-time: pull NSE/BSE universe
ss screen --cap lg --top 10 --horizon long
```

See [`docs/demo.md`](docs/demo.md) for the full command tour.

## What's inside

- **HLD**: [`docs/system-architecture.md`](docs/system-architecture.md)
- **LLD**: [`docs/lld.md`](docs/lld.md)
- **Demo**: [`docs/demo.md`](docs/demo.md)

## Status

v0.1 — MVP: NSE+BSE universe, fundamentals + prices via free providers, large/mid/small cap screen, multi-vendor LLM analyst (OpenAI default), Rich/JSON/Markdown output.

## License

MIT
