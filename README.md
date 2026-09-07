# SignalDesk

Fundamental valuation & research platform for Indian equities ("Alpha Spread for India").
Nifty 250 catalog, daily provider-sourced prices and fundamentals, relative valuation,
fundamental scores, technical indicators, a composite Alpha Score, FinBERT news sentiment,
and evidence-grounded LLM explanations — with an explicit rule: **missing data stays
missing; nothing is fabricated.**

Stack: **FastAPI + PostgreSQL** (async SQLAlchemy, Alembic) backend, **React 19 +
TypeScript + Vite + Tailwind v4** frontend, APScheduler nightly ingestion,
OpenRouter-compatible LLM for narratives (with deterministic fallback).

---

## Features (implemented)

- **Catalog & market data** — Nifty 250 universe (seeded from DB, not hardcoded), 2y daily
  OHLCV, dual providers (yfinance primary, Upstox secondary) merged with gap-fill and
  disagreement logging; primary always wins conflicts.
- **Fundamentals** — snapshot ratios (P/E, P/B, P/S, ROE/ROA, margins, solvency) with
  field-level coalesce on nightly refresh; annual + quarterly income-statement history.
- **Valuation** — relative valuation vs same-industry peers (P/E, P/B, P/S, EV/EBITDA),
  with honest `NO_PEERS` / `INSUFFICIENT_DATA` errors instead of invented answers.
- **Scores & Alpha** — profitability/solvency scores (0–100) and a 40/30/30
  fundamental/technical/sentiment Alpha composite with daily history.
- **News & sentiment** — Google News RSS ingestion, FinBERT scoring, 60-day relevance window.
- **LLM surfaces** — `/alpha/explanation`, `/explain` (5 question types) and `/ask`
  (single-shot Q&A). Prompts carry only allow-listed computed facts; every failure path
  falls back to a deterministic rule-based narrative; `source` marks provenance.
- **Observability** — structured request/job/provider logging with request ids, durable
  `job_runs` history, `/debug/jobs`, `/status` (DB/scheduler/ingestion freshness/LLM),
  staleness flags, uniform error envelope.

## Architecture

```
frontend/   React 19 + Vite (TanStack Query, Tailwind v4, lightweight-charts)
backend/    FastAPI app
  app/routers/       HTTP layer (error envelope convention)
  app/services/      business logic (valuation, scores, alpha, indicators, narratives)
  app/repositories/  SQL only (SQLAlchemy 2.0 async)
  app/providers/     source adapters: yfinance, upstox, merging facade, RSS, FinBERT, OpenRouter
  app/jobs.py        nightly ingestion passes (APScheduler 18:30 Asia/Kolkata) + job recording
  alembic/           migrations
```

Design rules worth knowing: providers never fabricate fields they lack; primary provider
wins disagreements; scheduled jobs record every run (`job_runs`); `/health` is liveness,
`/status` is readiness; every error returns `{error: {code, message, detail, request_id}}`.

## Setup

### Prereqs
- PostgreSQL running locally (databases `signaldesk` and `signaldesk_test`)
- Python 3.12+, Node 20+

### Backend
```powershell
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # if missing: see PROGRESS.md cheatsheet
copy .env.example .env            # then edit
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m app.seed  # seed the Nifty 250 universe (idempotent)
.venv\Scripts\python -m uvicorn app.main:app --reload
```

### Frontend
```powershell
cd frontend
npm install
npm run dev    # http://localhost:5173, proxies /api to the backend
```

## Configuration (`backend/.env`, never committed)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/signaldesk` |
| `CORS_ORIGINS` | comma-separated browser origins (default Vite dev server; empty disables CORS) |
| `UPSTOX_ANALYTICS_TOKEN` | optional; enables the secondary data provider. Absent = yfinance-only |
| `LLM_API_KEY` / `OPENROUTER_API_KEY` | optional; empty = LLM disabled (rule-based explanations always work) |
| `LLM_BASE_URL` / `LLM_MODEL` | OpenAI-compatible endpoint + model id. `LLM_BASE_URL` is trusted config — it receives prompts |
| `LLM_DAILY_CAP` | shared in-process LLM call budget (pre-warm + /ask + /explain) |

## API overview

Under `/api/v1`: `/stocks` (+ `/prices`, `/technicals`, `/fundamentals`, `/scores`,
`/valuation(+ /explanation)`, `/alpha` (+ `/explanation`, `/history`), `/news`,
`/sentiment`, `/peers`, `/performance`, `/technicals/series`, `/financials/history`,
`/profile`, `POST /explain`, `POST /ask`), `/screener`.

Operational (root, unauthenticated — **restrict before public deployment**):
`/health` (liveness), `/status` (readiness: db, scheduler, ingestion freshness, llm),
`/debug/jobs` (last run per job, durations, counts, errors, next scheduled run).

## Testing

```powershell
cd backend;  .venv\Scripts\python -m pytest          # 315 tests, no network, uses signaldesk_test
cd frontend; npm test                                # vitest (65)
             npm run typecheck                       # tsc -b
             npm run build                           # production build
```

## Limitations

- In-process scheduler, caches and LLM budget are single-process; production deployment
  (Phase 8) moves ingestion to CI cron. Data advances only while the process is alive.
- Fundamentals refresh nightly; `updated_at` marks the attempted refresh, not a
  per-field change guarantee.
- No authentication anywhere (including the LLM-spending POST endpoints) — local/
  development deployment only.
- Some provider fields are inherently unavailable (e.g. interest coverage for most
  stocks); the API returns null rather than estimating.

## Roadmap (summary)

- **Semester 1 (done):** equity research core + observability (Phases 1–7).
- **Phase 8:** deployment (static frontend, autosuspend DB, CI cron ingestion, endpoint restriction).
- **Semester 2:** multi-stock comparison, ETFs + mutual funds (research/holdings/overlap),
  DCF, backtesting vs forward returns, PDF reports, service split + Docker + CI/CD.
- **Deferred/exploratory:** portfolio simulation/paper trading, watchlists/auth,
  bull/base/bear scenarios (methodology undefined), ML forecasting.

Full decision log, methodology and roadmap: `PLANNING.md`. Operational status, commands
and gotchas: `PROGRESS.md`.
