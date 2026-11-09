# SignalDesk

**Fundamental research & valuation platform for Indian equities.**

SignalDesk ingests daily market data and company fundamentals for the Nifty 250
catalog plus a ranked top-1000 universe, computes relative valuation, fundamental
scores, technical indicators, an Altman Z-score, a composite **Alpha Score**, and
FinBERT news sentiment, then serves it all through a FastAPI backend and a React
frontend with grounded LLM explanations on top.

One rule governs every layer: **missing data stays missing nothing is
fabricated.** If a provider doesn't supply a field, the API returns `null` (or an
explicit `NO_PEERS` / `INSUFFICIENT_DATA` error), never an estimate. When the LLM
is unavailable, deterministic rule-based narratives take over.

## Features

- **Equity universe & market data** — Nifty 250 catalog (seeded, not hardcoded),
  ranked top-1000 universe with eligibility rules and audit trail, 2 years of
  daily OHLCV, dual providers (yfinance primary, Upstox optional) merged with
  gap-fill; the primary provider always wins conflicts.
- **Fundamentals** — snapshot ratios (P/E, P/B, P/S, ROE/ROA, margins, solvency)
  with field-level coalesce on refresh, plus annual & quarterly income-statement
  history.
- **Valuation** — relative multiples vs same-industry peers (P/E, P/B, P/S,
  EV/EBITDA) with honest errors instead of invented answers.
- **Scores & Alpha** — profitability/solvency scores (0–100) and a 40/30/30
  fundamental/technical/sentiment Alpha composite with daily history.
- **Technicals & Altman Z** — indicator series (EMA, RSI, ATR, Bollinger bands,
  …) and a bankruptcy-risk Z-score per stock.
- **News & sentiment** — Google News RSS ingestion, FinBERT scoring, 60-day
  relevance window, market-wide news feed.
- **ETFs & mutual funds** — curated ETF surface (kept out of the equity
  screens), fund catalog with NAV history and trailing returns (1m → 3y).
- **Benchmarks dashboard** — index cards with sparklines, read only from stored
  rows — no provider calls on request paths.
- **LLM surfaces** — `/ask` (grounded Q&A) and `/explain` (5 question types).
  Prompts carry only allow-listed computed facts; every failure path falls back
  to a deterministic rule-based narrative; `source` marks provenance.
- **Observability** — structured logging with request ids, durable `job_runs`
  history, `/debug/jobs`, `/status`, staleness flags, and a uniform error
  envelope on every route.

## Architecture

```
frontend/            React 19 + TypeScript + Vite (TanStack Query/Table,
                     Tailwind v4, lightweight-charts, Radix UI)
backend/             FastAPI (Python 3.12)
  app/routers/       HTTP layer (uniform error envelope)
  app/services/      business logic — valuation, scores, alpha, indicators,
                     ranking, narratives (pure, testable decision logic)
  app/repositories/  SQL only (SQLAlchemy 2.0 async)
  app/providers/     source adapters: yfinance, Upstox, NSE master, RSS,
                     FinBERT, OpenRouter — behind a merging facade
  app/jobs.py        ingestion passes (dev: APScheduler 18:30 Asia/Kolkata;
                     prod: GitHub Actions cron is the only scheduler)
  alembic/           migrations
.github/workflows/   CI, nightly ingest, migrations, ranking, backup/restore,
                     storage probes
```

Design rules worth knowing:

- Providers never fabricate fields they lack; the primary provider wins
  disagreements and every conflict is logged.
- Scheduled jobs record every run (`job_runs`); a NaN-guard middleware blocks
  non-finite values from ever reaching the database or the API.
- `/health` is liveness, `/status` is readiness.
- Every error returns `{error: {code, message, detail, request_id}}`.

## Getting started

**Prerequisites:** Python 3.12+, Node 20+, PostgreSQL with two databases
(`signaldesk` and `signaldesk_test`).

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then edit — see Configuration below
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m app.seed    # seed the Nifty 250 catalog (idempotent)
.venv\Scripts\python -m uvicorn app.main:app --reload
```

### Frontend

```powershell
cd frontend
npm install
npm run dev    # http://localhost:5173 — proxies /api to the backend
```

## API overview

All research endpoints live under `/api/v1`:

- `/stocks` — catalog, quotes, profile, prices, technicals (+ series),
  fundamentals, financials history, scores, Altman Z, valuation (+ explanation),
  alpha (+ explanation & history), news, sentiment, peers, performance;
  `POST /stocks/{symbol}/explain`, `POST /stocks/{symbol}/ask`
- `/screener` — filter/sort the ranked universe
- `/etfs` — curated ETF list & returns
- `/funds` — mutual-fund catalog, NAV history, trailing returns
- `/benchmarks`, `/market/news` — dashboard index cards and market-wide news

Operational (root-level, OPS_API_KEY-gated in production):
`/health`, `/status`, `/debug/jobs`.

In development the interactive docs are at `/docs`; they are disabled in
production so the route surface isn't served to scanners.

## Testing & CI

```powershell
cd backend
.venv\Scripts\python -m pytest      # offline suite, uses signaldesk_test
cd ..\frontend
npm test                            # vitest
npm run typecheck                   # tsc -b
npm run build                       # production build
```

GitHub Actions runs the backend suite (Postgres 17 service container) and the
frontend suite on every push/PR to `main`. Production ingestion is driven
entirely by Actions workflows — nightly ingest (13:30 UTC, after market close),
ranking, migrations, and DB backup/restore/probe jobs. Workflows are idempotent:
cron drift is tolerated by upsert-based ingestion.

## Production notes

Deployed as a static frontend (Cloudflare Pages) + FastAPI backend (Render) +
managed Postgres (Neon), with GitHub Actions as the only scheduler. Hardening:
ops endpoints fail closed without `OPS_API_KEY`, per-IP rate limiting, CORS
prefix enforcement, https-only LLM gateway check at startup, API docs disabled,
and secrets only ever in service env vars / Actions secrets.

## Limitations

- Data advances only while ingestion runs; the in-process scheduler (dev only)
  stops with the process. In production, Actions cron drifts by minutes.
- Fundamentals refresh nightly; `updated_at` marks the attempted refresh, not a
  per-field change guarantee.
- Some provider fields are inherently unavailable (e.g. interest coverage for
  most stocks) — the API returns `null` rather than estimating.
- LLM narratives are grounded in computed facts only; they are not investment
  advice.

## License

[MIT](LICENSE)
