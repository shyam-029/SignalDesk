# SignalDesk - Project Planning & Architecture Log

> **Purpose:** Living document. Records every product, technical, and scope decision for the project.
> **Owner:** Shyam (3rd-year CS student)
> **Timeline:** 2 semesters (~8 months) before recruiter season.
> **Status:** **Phase 6.5 COMPLETE** (experience overhaul + parts E/F/G + Part D + review round:
> Nifty 250 universe, refreshed data, valuation fallback, retroactive alpha, research UX fixes).
> Phase 7 (observability) next.
>
> **Companion file:** `PROGRESS.md` - operational status, what's done/in-progress/next, command
> cheatsheet, and gotchas. **Read PROGRESS.md first to pick up where we left off.**

---

**Documentation system (2 files):** `PLANNING.md` = the plan (what/why). `PROGRESS.md` = the status
(what's done / next). Both updated at the end of every phase.

---

## Working Agreement (teaching mode)

I'm learning as I build this - treat every implementation step as a teaching moment, not just execution.

For every file you create or edit:

1. Before writing code, briefly explain the concept/pattern being used and why it's the right choice here (2-4 sentences max, not a lecture).
2. After writing code, add a short comment block at the top of non-trivial functions explaining what they do and why.
3. If you use a library/pattern I likely haven't used before (SQLAlchemy relationships, Pydantic validators, async/await, etc.), flag it explicitly: "New concept: X - here's what it does".
4. Never silently make an architectural decision - state the alternatives you considered and why you picked this one.
5. If a file is long or complex, build it in smaller chunks and pause between chunks so I can ask questions.

I'd rather move slower and understand everything than move fast and have a codebase I can't explain.

---

## Table of Contents

- **Part A - Product**
  - 1. Overview & Vision
  - 2. Current Scope (feature tiers)
  - 3. Universe & Scalability Strategy
- **Part B - Architecture & Data**
  - 4. Tech Stack
  - 5. Architecture (modular monolith)
  - 6. Database Schema (planned)
  - 7. Data Sources
  - 8. Valuation Feature - Relative (Multiples) Valuation
- **Part C - Engineering Standards**
  - 9. API Contract (v1 endpoints)
  - 10. Environment & Secrets Handling
  - 11. Error Handling Convention
  - 12. Testing Strategy
  - 13. Failsafes Summary
- **Part D - Delivery**
  - 14. Roadmap (2 semesters)
  - 15. Scope Cuts & Flags
  - 16. Definition of Done - Phase 1
  - 17. Decision Log

---

# Part A - Product

## 1. Overview & Vision

A **fundamental valuation & analysis platform for the Indian equity market** - an "Alpha Spread for India."
Focus is on **analyzing the value** of stocks (undervalued / overvalued signal), not on fancy price-history
visuals. Primary users: retail investors comparing whether a stock is fairly valued.

### Core differentiator
Most Indian apps (Groww, Zerodha, etc.) show prices, charts, and holdings but do **not synthesize**
fundamentals + valuation + sentiment into a single defensible signal. We build the analyzer.

For each stock, produce:
- **Valuation signal** - "undervalued by X% / overvalued by X%" using **relative (multiples) valuation** (v1)
- **Fundamental scores** - profitability score, solvency score (ROE, ROIC, margins, D/E, interest coverage, etc.)
- **Rule-based explanation** of *why* the score is what it is (no trained ML model in v1)
- Company profile / overview generated from financial data

---

## 2. Current Scope (feature tiers)

### Core (P0)
- Stock universe: **Nifty 50** for Phase 1, designed to scale to **Nifty 500** (see §3)
- Price ingestion (OHLCV) + PostgreSQL storage
- **Relative valuation** (price vs peer multiples)
- **Fundamental analysis** (profitability + solvency scores)
- **Rule-based explanation** of scores
- REST API (FastAPI) + Swagger docs

### Secondary (P1)
- Technical indicators (SMA / RSI / MACD) - feed the Alpha Score
- Redis caching for hot endpoints (quotes, scores)
- React + Vite + TypeScript frontend (shadcn/ui, TradingView Lightweight Charts)
- News ingestion (RSS) + FinBERT sentiment scoring

### Stretch (P2) / Semester 2
- LLM-generated explanation narrative (shipped - grounded `/alpha` narrative, Phase 5)
- NL screener (LLM function calling)
- Three.js holdings graph
- DCF valuation (Semester 2 upgrade)
- MF tracker + holdings overlap (**CORE PRODUCT VISION** - deferred to Semester 2, not cut; see §18)
- Live prices (Finnhub WebSocket), watchlists/auth, backtest page

---

## 3. Universe & Scalability Strategy

**End-goal universe:** Nifty 500 scale (Nifty 50 → Nifty 200 → Nifty 500 ladder of large/mid caps).

### Core principle: the universe is data, not code
Never hardcode the symbol list. Universe membership lives in database tables so scaling to Nifty 500 is
adding rows, not editing code.

### Schema support
```
universes       (id, name)               -- "nifty50", "nifty200", "nifty500"
stock_universe  (universe_id, stock_id)  -- membership (many-to-many)
```

### Consequences
- **Ingestion** reads the active universe from the DB, never a constant.
- **Peer selection** for relative valuation is keyed off `industry` in the catalog, **independent of
  universe** - so peer groups automatically enrich as the catalog grows, without touching valuation code.
- **Ingestion must be batched + resumable** from day one: one failed symbol never aborts a run.
- **Provider abstraction** (see §5) is the escape hatch if yfinance coverage degrades as the catalog widens.
- Phase 1 seeds `stocks` + `stock_universe` with the Nifty 50.

---

# Part B - Architecture & Data

## 4. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python + FastAPI** | Known language; async, type hints, Pydantic validation, auto Swagger docs |
| Database | **PostgreSQL 17** + SQLAlchemy 2.0 + Alembic | Industry-standard SQL; typed ORM; migrations |
| Cache | **Redis** | Cache hot endpoints (quotes, scores) with TTL + explicit invalidation |
| Scheduler | APScheduler | Background ingestion/scoring jobs |
| ML | FinBERT (HuggingFace) | Free, local sentiment scoring |
| LLM | OpenRouter via raw httpx (OpenAI-compatible; `LLMProvider` ABC) | Score-explanation narrative (Phase 5) + NL screener (STRETCH); configurable free model, empty = disabled; rule-based fallback |
| Frontend | React + Vite + TypeScript, shadcn/ui, Tailwind, Framer Motion | Transferable stack; professional components |
| Charts | TradingView Lightweight Charts | Finance-native, free, looks real |
| 3D | Three.js / react-three-fiber | Holdings graph (stretch) |
| Tests | pytest + httpx | API + service tests, mock providers |
| Deploy | Render or Railway + managed Postgres | Free tier; live URL |

---

## 5. Architecture (modular monolith, one process)

```
Frontend: React + Vite + TS + shadcn/ui
   │ REST / JSON  (Swagger at /docs)
FastAPI
   ├─ routers/          HTTP layer (validation, params, status codes)
   ├─ services/         business logic (valuation, fundamentals, indicators, scoring)
   ├─ repositories/     SQL only (SQLAlchemy)
   └─ providers/        data-source adapters (yfinance, RSS, finbert, llm)
            │
            ▼
   PostgreSQL: stocks · daily_prices · fundamentals · valuations · news · alpha_scores
            ▲
   APScheduler: daily price refresh, news fetch, sentiment re-score
```

**Layering rule:** each layer has one job; services are testable without DB/network;
providers are swappable behind an interface.

---

## 6. Database Schema (implemented)

> Implemented in migrations `8bf8964e941a` (initial) + `5f7fd30113b1` (financials). `daily_prices` uses
> a surrogate `id` PK + a unique constraint (D24). Association table `stock_universe` has a composite PK
> (D26). `financials` is a point-in-time snapshot, one row per stock (D32).

```
stocks            (id, symbol, name, sector, industry)          -- growing catalog
universes         (id, name)                                    -- "nifty50", "nifty500"
stock_universe    (universe_id, stock_id)                       -- membership (many-to-many, composite PK)
daily_prices      (id, stock_id, date, open, high, low, close, volume)  -- UNIQUE(stock_id, date); Numeric(16,4) prices
financials        (id, stock_id, market_cap, trailing_pe, enterprise_value, ebitda, price_to_book,
                   price_to_sales, return_on_equity, return_on_assets, operating_margin, profit_margin,
                   debt_to_equity, interest_coverage, current_ratio, updated_at)  -- UNIQUE(stock_id) snapshot
news_articles     (id, symbol, source, title, url, published_at, content)  -- UNIQUE(url); tz-aware published_at
news_sentiment    (id, article_id, score, label, model)                  -- UNIQUE(article_id) 1:1
valuation         (stock_id, date, method, intrinsic_value, current_price, margin, status)
news_articles     (id, symbol, source, title, url, published_at, content)
news_sentiment    (article_id, score, label, model)
alpha_scores      (symbol, date, fundamental, technical, sentiment, composite,
                   components_json JSONB, updated_at)           -- UNIQUE(symbol, date) snapshot
financial_periods (id, stock_id, period_end, period_type, revenue, net_income,
                   operating_margin, net_margin, eps, source, ingested_at)
                                                  -- UNIQUE(stock_id, period_end, period_type); Part E
mutual_funds      (id, name, amfi_code)               -- stretch
mf_nav_history    (fund_id, date, nav)                -- stretch
mf_holdings       (fund_id, stock_name, pct_aum, date) -- stretch
```

---

## 7. Data Sources

| Data | Source | Cost | Notes |
|---|---|---|---|
| Indian stock prices (OHLCV) | yfinance `.NS` suffix | Free | e.g. `RELIANCE.NS`; no key |
| **Financial statements** (income, balance sheet, cash flow, key ratios) | **yfinance** | **Free** | Recommended free option; covers Indian stocks |
| **Secondary market/fundamentals source** | **Upstox v2 API** | **Free** (Upstox account) | Part F: manual "Analytics Token" (Bearer) in backend/.env; read-only candles + fundamentals; merged as SECONDARY behind yfinance (D58/D59) |
| Mutual fund NAV | AMFI CSV | Free | Official, structured |
| Mutual fund holdings | Fund house sites (HTML/Excel/PDF) | Free | Excel/CSV first, PDF later |
| News (Indian) | RSS (ET, Moneycontrol, Mint) + Google News RSS per symbol | Free | No key |
| Sentiment | FinBERT (HuggingFace) | Free | Runs locally |

### Paid alternatives (for reference only - not chosen)
- **Financial Modeling Prep** (~$20-30/mo) - strongest fundamentals API for Indian + global stocks.
- **Alpha Vantage Premium** (~$50-100/mo) - broader data, higher request caps.
- **EODHD** (~$20-30/mo) - fundamentals + historical data.
- **Bloomberg / Refinitiv** - institutional-grade, thousands of $/yr. Out of reach, not needed.

> **Decision:** Use **yfinance for fundamentals** (free, no key, covers Indian stocks). Re-evaluate only if
> data gaps appear (e.g., some Indian financials missing in yfinance).

---

## 8. Valuation Feature - Relative (Multiples) Valuation (v1)

**Method:** Compare a stock's current valuation multiple to peer/industry averages.

Inputs per stock (from yfinance financials + price):
- Market cap
- P/E (price-to-earnings)
- EV/EBITDA (enterprise value / earnings before interest, tax, depreciation, amortization)
- P/B (price-to-book)
- P/S (price-to-sales)

Process:
1. Compute current multiple for target stock.
2. Compute the same multiple for **peer set = same industry peers from the full stocks catalog**
   (universe-independent - peer groups enrich automatically as the catalog grows).
3. Compare target multiple vs peer average → margin.
   - target P/E < peer average P/E → **undervalued**
   - target P/E > peer average P/E → **overvalued**
4. Output: `undervalued by X%` / `overvalued by X%` / `fairly valued`.

**Why relative first (not DCF):**
- Simpler and more transparent → easier to make defensible in an interview.
- Directly produces the "undervalued by X%" headline Alpha Spread shows.
- Robust with free data; DCF is highly assumption-sensitive (WACC, growth, terminal value) and harder
  to defend as a beginner.
- DCF is the Semester 2 upgrade (matches the Alpha Spread arc).

---

## 8b. Fundamental Score Methodology (approved 2026-08-18)

Fixed-threshold piecewise-linear mapping (no peer-relative normalization):

```
score = 100 × clamp((value - F) / (C - F), 0, 1)      # higher = better
score = 100 × clamp((F - value) / (F - C), 0, 1)      # lower = better (F=floor 0pts, C=ceiling 100pts)
```

| Metric | Direction | Floor (0) | Ceiling (100) | Rule |
|---|---|---|---|---|
| ROE | higher | 0% | 20% | ≤0→0; 0-20→`100·(v/20)`; ≥20→100 |
| ROA | higher | 0% | 12% | ≤0→0; 0-12→`100·(v/12)`; ≥12→100 |
| Operating margin | higher | 0% | 25% | ≤0→0; 0-25→`100·(v/25)`; ≥25→100 |
| Net margin | higher | 0% | 20% | ≤0→0; 0-20→`100·(v/20)`; ≥20→100 |
| D/E | lower | 200% | 50% | ≤50→100; 50-200→`100·(200-v)/150`; ≥200→0 |
| Interest coverage | higher | 1× | 5× | ≤1→0; 1-5→`100·(v-1)/4`; ≥5→100 |
| Current ratio | higher | 0.5× | 2× | ≤0.5→0; 0.5-2→`100·(v-0.5)/1.5`; ≥2→100 |

**Weights:** profitability = ROE 40% / ROA 20% / op-margin 20% / net-margin 20%.
Solvency = D/E 50% / interest-coverage 30% / current-ratio 20%.
**Missing values:** drop the component and renormalize remaining weights; all-missing → score `None`
(+ `insufficient_data: true`). **Negative:** ROE/ROA/margins clamp to 0; negative D/E (net cash) clamps
to 100; negative interest-coverage clamps to 0. ROE/ROA/margins stored as decimals, normalized to percent
in the service. Output: `ComponentScore{score, components:[{name,value,score}], available}`.

---

# Part C - Engineering Standards

## 9. API Contract (v1 endpoints)

Base path: `/api/v1`. All responses JSON. Swagger docs auto-generated at `/docs`.

### Stocks
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/v1/stocks` | `?sector=&page=1&limit=50` | `{ items: [StockSummary], total, page, limit }` |
| GET | `/api/v1/stocks/{symbol}` | - | `StockDetail` (profile + quote block + market_cap; fields null when absent) |
| GET | `/api/v1/stocks/{symbol}/quote` | - | *(subsumed by StockDetail.quote - not a separate endpoint)* |
| GET | `/api/v1/stocks/{symbol}/prices` | `?range=1y&resample=1d` | `{ symbol, range, items: [OHLCV] }` |
| GET | `/api/v1/stocks/{symbol}/technicals` | - | `Technicals` (SMA20, EMA12, RSI14, MACD{line,signal,histogram}, sub-scores, score, closes_used, insufficient_data) |

### Fundamentals & Valuation (core)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/v1/stocks/{symbol}/fundamentals` | `?periods=4` | `{ symbol, key_ratios, income, balance_sheet, cash_flow }` |
| GET | `/api/v1/stocks/{symbol}/scores` | - | `ScoreCard` (profitability, solvency + per-component breakdown) |
| GET | `/api/v1/stocks/{symbol}/valuation` | - | `Valuation` (method, peers, current_multiple, peer_avg, margin, status) |
| GET | `/api/v1/stocks/{symbol}/valuation/explanation` | - | `Explanation` (rule-based text) |
| GET | `/api/v1/screener` | `?undervalued=true&min_roic=&page=` | `{ items: [ScreenResult], total }` |

### News & Sentiment (secondary)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/v1/stocks/{symbol}/news` | `?limit=20` | `{ items: [NewsArticle] }` |
| GET | `/api/v1/stocks/{symbol}/sentiment` | - | `Sentiment` (score, label, window) |

### Alpha Score (composite)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/v1/stocks/{symbol}/alpha` | - | `Alpha` (composite, fundamental, technical, sentiment, components, weights, value_signal, explanation, insufficient_data) |
| POST | `/api/v1/stocks/{symbol}/explain` | `{question_type}` | `Explanation` (grounded contextual explanation; types: alpha/technical/valuation/fundamental/sentiment; rule-based fallback; TTL cache; shared daily cap) |

### Historical research (Phase 6.5 Part E)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/v1/stocks/{symbol}/performance` | - | `Performance` (as_of, bars_used, windows{1w,1m,3m,6mo,1y,2y}{change_pct,change_abs,start_close,end_close,start_date}, high_52w, low_52w, volatility_1y_pct, insufficient_data) |
| GET | `/api/v1/stocks/{symbol}/alpha/history` | `?limit=180` | `{symbol, items:[{date,composite,fundamental,technical,sentiment,components}], insufficient_data}` |
| GET | `/api/v1/stocks/{symbol}/technicals/series` | `?limit=250` | `{symbol, items:[{date,close,sma20,ema12,rsi14,macd,macd_signal,macd_histogram}], insufficient_data}` |
| GET | `/api/v1/stocks/{symbol}/peers` | - | `{symbol, classifier, count, items:[{symbol,name,sector,industry,last_price,change_pct,trailing_pe,return_on_equity,profit_margin,debt_to_equity}]}` |
| GET | `/api/v1/stocks/{symbol}/financials/history` | `?period_type=annual\|quarterly` | `{symbol, items:[{period_end,period_type,revenue,net_income,operating_margin,net_margin,eps,source,ingested_at}], insufficient_data}` |

### Health / Meta
| Method | Path | Response |
|---|---|---|
| GET | `/health` | `{ status: "ok" }` |

**CORS:** browser origins come from `CORS_ORIGINS` (comma-separated; default `http://localhost:5173`; empty disables). The Vite dev server also proxies `/api` → the API, so CORS is only exercised on direct/production access.

### Key shapes
```
Valuation: {
  symbol, method: "relative",
  peers: ["TCS.NS", ...],
  metric: "P/E",
  current: 28.4, peer_median: 24.1,
  margin_pct: -15.1,           // negative = undervalued
  status: "undervalued" | "overvalued" | "fairly_valued",
  computed_at
}
ScoreCard: {
  symbol, profitability: 64, solvency: 81,      // 0-100
  components: { roe: 92, roic: 85, margin: 70, de_ratio: 88, ... },
  explanation: "..."                            // rule-based text
}
OHLCV: { date, open, high, low, close, volume }
StockSummary: { symbol, name, sector, last_price, change_pct }
```

---

## 10. Environment & Secrets Handling

- **`.env`** at `backend/` root - **git-ignored**, never committed. Holds all secrets.
- **`.env.example`** - committed, with placeholder values and comments, so new devs know what's needed.
- **`.gitignore`** at `signaldesk/` repo root - at minimum: `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.DS_Store`.
- **`config.py`** uses **pydantic-settings**: a `Settings` class reads `.env`, type-coerces, validates presence of required secrets at startup.
- Required keys (only these are required now):
  ```
  APP_ENV=development              # development | production
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/signaldesk
  ```
- Optional keys (empty/placeholder until their phase): `REDIS_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `FINNHUB_API_KEY`.
- **Rule:** no secret ever hardcoded in source; no secret in tests (use `.env.test` / fixtures).
- LLM key is the only paid secret; keep it out of any committed file and out of logs.

---

## 11. Error Handling Convention

**Single consistent error envelope** - every error returns:
```json
{ "error": { "code": "RESOURCE_NOT_FOUND", "message": "Stock RELIANCE.NS not found", "detail": {}, "request_id": "abc123" } }
```

**Custom exception classes** (in `app/errors.py`):
- `NotFoundError` → 404
- `ValidationError` → 422
- `ProviderError` → 502/503 (upstream data source failed)
- `NoPeersError` → 409 (peer set empty for valuation)
- `RateLimitError` → 429

**Registered via FastAPI exception handlers** - routers never catch-and-format inline; they raise, handlers format.

**Provider failure failsafes:**
1. ✅ **Retry with exponential backoff** - implemented as `_with_retry` (2 retries, backoff) in `jobs.py`; covers price + financials fetches.
2. **Fallback to cached/stale data** - if we have a prior snapshot in Postgres, serve it with a `stale: true` flag in the response rather than failing. *(Deferred - staleness visibility planned with observability, Phase 7.)*
3. If no data at all → raise `ProviderError` → clean 502.
4. **Empty peer set** (relative valuation) → `NoPeersError` (409) with message telling the client to use a broader peer group; never silently return a misleading "fairly valued."

**Logging:** structured logs (`JSON`/key-value) via `logging`; include `symbol`, `request_id`, `error.code`; never log secrets. Central exception middleware attaches a `request_id` for traceability.

---

## 12. Testing Strategy

**Priority order (test deepest, most-pure logic first):**
1. **Services** - valuation math, fundamental score computation, explanation assembly. Pure functions, no I/O. *Highest value, test first.*
2. **Repositories** - SQL queries against a **test database** (dedicated `signaldesk_test` schema, created/dropped per run).
3. **Routers/API** - via `httpx` ASGI client; **providers always mocked** (no real network calls).
4. **Providers** - thin tests, mocked HTTP responses (e.g., recorded yfinance JSON fixtures).

**Key conventions:**
- Fixtures for sample financials, sample price series, sample peer sets.
- Parametrize valuation edge cases (negative earnings → exclude P/E for that stock; empty peer set).
- Test the **error envelope** (each custom exception → correct status + body).
- Mock the LLM in tests - never call it.
- Run: `pytest` from `backend/`. Fast, no network required.
- CI (Semester 2): same suite on GitHub Actions.

---

## 13. Failsafes Summary

| Risk | Failsafe |
|---|---|
| yfinance down / returns nothing | Retry w/ backoff → stale-data fallback → clean 502 |
| Empty peer set for valuation | `NoPeersError` (409), explicit message, never silent wrong answer |
| Negative/zero earnings | Exclude that metric (P/E) from valuation for that stock; note it |
| Partial ingestion failure | Per-symbol error isolation - one bad symbol doesn't fail the whole run |
| Secret leaked to repo | `.gitignore` + `.env` + `config.py` startup validation; no secrets in tests/logs |
| LLM key cost runaway | Single-purpose calls, mock in tests, in-process TTL cache + `llm_daily_cap`, cost logging, rule-based fallback |
| Rate limit from free APIs | Backoff + scheduler throttling; provider abstraction to swap source |
| DB migration drift | Alembic migrations versioned; CI checks `alembic upgrade head` |

---

# Part D - Delivery

## 14. Roadmap (2 semesters)

### Semester 1 (16 weeks) - ship the complete product
| Phase | Weeks | Deliverable |
|---|---|---|
| 1 | 1-3 | FastAPI + Postgres + schema + yfinance provider + Nifty 50 ingestion (universe seeded from DB, not hardcoded) |
| 2 | 4-5 | **Relative valuation + fundamental scores (profitability/solvency) + rule-based explanation** |
| 3 | 6-7 | News RSS ingestion + FinBERT sentiment |
| 4 | 8-9 | Technical indicators + Alpha Score composite |
| 5 | 10-11 | ✅ LLM explanation narrative + tests (DONE) |
| 6 | 12-13 | React dashboard + charts |
| 7 | 14-15 | Observability (structured logging, stale-data flags, /debug/jobs) - Redis and Three.js moved to conditional/stretch, see §18 |
| 8 | 16 | Deploy per D79: static frontend + sleep-tolerant API + autosuspend Postgres (Neon/Supabase) + GitHub Actions cron for ingestion (replaces in-process scheduler for production) + polish + README |
### Semester 2 - the distributed progression
1. Split monolith → two services (API server + background worker)
2. Add message queue (RabbitMQ - beginner-friendly Kafka)
3. Docker + docker-compose (Postgres, Redis, RabbitMQ, both services)
4. CI/CD (GitHub Actions: lint + test + auto-deploy)
5. Monitoring (structured logging + dashboards)
6. Fill stretch: **DCF valuation**, live prices, watchlists/auth, backtest page

---

## 15. Scope Cuts & Flags (unrealistic for now)

| Item | Status | Reason |
|---|---|---|
| Trained ML "explains why" model | **CUT** (v1) | Needs compute + money; replaced by rule-based explanation |
| Groww-style distributed infra (Kafka, CockroachDB, cells, Kubernetes) | **CUT** (v1) | Solves a scale problem we don't have; Semester 2 introduces the concept properly (service split + RabbitMQ) |
| Full backtest page (Alpha Spread style) | **DEFER** | Multi-month effort; needs robust valuation history |
| PDF holdings parsing | **DEFER** | Hard, variable formats; start Excel/CSV |
| Real-time/live prices | **DEFER** | Historical is enough for valuation |
| Derivatives (F&O) | **CUT** | Different data model + providers |
| Cassandra | **CUT** | Wrong tool; not a scraper; relational fits Postgres |

---

## 16. Definition of Done - Phase 1

> **STATUS: MET** (2026-08-18). All 8 items below verified.

## 16b. Definition of Done - Phase 5 (grounded LLM explanation)

> **STATUS: MET** (2026-08-21). All items verified.

## 16c. Definition of Done - Phase 6 (production frontend)

> **STATUS: MET** (2026-09-04). All items verified.

1. `frontend/` builds with the locked stack (Vite/React/TS/Tailwind v4/Radix/TanStack/Framer/LW-Charts) - `tsc -b` zero errors, `vite build` succeeds.
2. All five pages implemented and consuming ONLY existing/new backend endpoints: landing, markets, screener, stock research, methodology. No auth, no chatbot, no fake data.
3. Stock research page shows: profile/quote header, Alpha + components + weights + grounded explanation, all four valuation multiples with peer medians + relative positioning + expandable inputs, fundamentals with per-ratio scores, Lightweight Charts price history (1M-2Y), Technical Positioning (aggregate verdict + SMA/EMA/RSI/MACD readings), news + net sentiment, methodology.
4. Every non-obvious metric has an information affordance (METRIC_INFO/InfoDot); DataState handles loading/empty/insufficient/stale/error/unknown symbol.
5. Semantic color only on analytical conclusions; valuation state independent of Alpha; raw metrics neutral.
6. Backend suite green with the 4 additions (155/155, zero-network tests); frontend tests 38/38.
7. Live integration verified (uvicorn + Vite: CORS, preflight, deep link, real endpoints).
8. PROGRESS.md + PLANNING.md updated; git commit + push.

## 16d. Definition of Done - Phase 6.5 (experience overhaul)

> **STATUS: MET** (2026-09-05). All items verified.

1. Copy discipline holds site-wide: zero em dashes and zero AI-tell wording in
   user-visible strings and comments; the missing-value placeholder is "-";
   disclaimers normalize to "Generated from SignalDesk data. Not investment advice."
2. Typography: Instrument Sans (body/UI), IBM Plex Mono (data, weight floor 500,
   no 400 face loaded), Libre Caslon Text (display) retained; no data/UI text
   below 12px anywhere, including chart canvas text.
3. Palette: light mode graded to the approved reference concept (cool white
   #f8f9ff family, navy ink #0b1c30, petrol identity #006781); dark mode keeps
   the approved Warm Ink + Gold theme untouched; dark-first default with the
   stored preference always winning.
4. Dimension accents (jade=fundamentals, amber=valuation, coral=technicals,
   teal=sentiment) mark only which dimension speaks; raw metrics stay neutral.
5. Landing: market pulse marquee (all 50 constituents, real /stocks data,
   honest DataStates), interactive candle field (illustrative OHLC readout),
   numbers-to-signal diagram, clickable framework cards, fifty-bar universe
   field, scroll rail, glass panels, section rhythm, keyword highlights.
6. Motion is transform/opacity only, honors prefers-reduced-motion everywhere
   (Reveal, marquee, rail), and no raster images or blend modes ship (zero
   remote requests).
7. Frontend tests 43/43 (5 new), tsc clean, production build OK; live
   uvicorn+Vite integration re-verified.
8. PROGRESS.md + PLANNING.md updated; git commit + push.

Phase 5 is complete only when all of the following pass:

1. `/alpha` returns a populated `explanation` - LLM-narrated when key+model+provider work, rule-based otherwise.
2. Every number in the LLM prompt comes from the `_alpha_facts()` allow-list (explicit serialization, not `AlphaResult.__dict__`); prompt carries no free-text fields → no injection path.
3. `LLMResult` carries `text`/`tokens_used`/`model`; cost logged from it, `None`-safe.
4. `LLM_MODEL` configurable via env; empty default = disabled; no model hard-coded in code; `.env.example` documents the example model + changeability.
5. Prompt enforces the output contract (short, factual, no recommendation, no guaranteed returns); tests verify the instructions.
6. LLM mocked in tests; suite passes zero-network; coverage measured.
7. `PROGRESS.md` + `PLANNING.md` updated; Git commit + push done.

Phase 1 is **complete** only when all of the following pass:

1. `GET /api/v1/stocks` returns the **full Nifty 50 universe** (50 stocks with name + sector).
2. `GET /api/v1/stocks/{symbol}/prices` returns **real OHLCV history** for at least 5 real stocks
   (`RELIANCE.NS`, `TCS.NS`, `HDFCBANK.NS`, `INFY.NS`, `ICICIBANK.NS`).
3. Data is persisted in PostgreSQL - rows exist in `stocks`, `universes`, `stock_universe`, `daily_prices`.
4. **Idempotent re-run** - running the ingestion job twice produces no duplicate rows.
5. Swagger `/docs` renders every Phase 1 endpoint.
6. `pytest` passes with providers mocked (no network dependency).
7. `.env.example` + `.gitignore` are in place; no secrets in source.
8. `GET /health` returns `200 {status:"ok"}`.

---

## 17. Decision Log

Chronological record of decisions. Append as time progresses.

### 2026-08-17 - Session 1 (planning kickoff)
- **D1.** Product focus: **fundamental valuation analyzer for Indian equities** (Alpha Spread-style), not a charting app.
- **D2.** Market: **India only**. Stocks + ETFs; derivatives explicitly out.
- **D3.** First valuation method: **Relative (multiples) valuation**. DCF deferred to Semester 2.
- **D4.** Valuation + fundamentals are the **core** feature. MF tracker and news/Alpha Score demoted to secondary/stretch.
- **D5.** Financial data source: **yfinance** (free). Paid fallbacks noted (FMP ~$20-30/mo) but not chosen.
- **D6.** Explanation feature: **rule-based** (concatenate real score components), not a trained model.
- **D7.** Tech stack locked: FastAPI, PostgreSQL+SQLAlchemy+Alembic, Redis, APScheduler, FinBERT,
  React+Vite+TS+shadcn/ui, pytest, Render/Railway.
- **D8.** LLM (gpt-4o-mini/Claude Haiku) for explanation narrative + NL screener; ~$5 budget.
- **D9.** 2-semester plan: S1 ship product, S2 distributed progression (service split, RabbitMQ, Docker, CI/CD, monitoring).
- **D10.** Documentation established at `Desktop/Projects/PLANNING.md`.
- **D11.** API contract locked: `GET /api/v1/...` endpoint list + response shapes (§9). Core = valuation/scores/explanation endpoints.
- **D12.** Secrets via `.env` (git-ignored) + `.env.example` + pydantic-settings; startup validation; `.gitignore` rules (§10).
- **D13.** Error handling: single `{error:{code,message,detail}}` envelope; custom exceptions; retry→stale-fallback→clean-502 failsafe chain (§11).
- **D14.** Testing order: services → repositories → routers (providers always mocked); no network in tests (§12).
- **D15.** Phase 1 Definition of Done defined with concrete success checks (§16).

### 2026-08-18 - Session 2 (scope + environment)
- **D16.** **Universe is data, not code**: `universes` + `stock_universe` tables; ingestion reads universe from DB (§3, §6).
- **D17.** End-goal universe: **Nifty 500 scale** (Nifty 50 → Nifty 200 → Nifty 500 ladder).
- **D18.** Peer selection for relative valuation is **industry-keyed and universe-independent** - peer groups enrich as catalog grows.
- **D19.** Ingestion must be **batched + resumable** from day one; one failed symbol never aborts a run.
- **D20.** PostgreSQL **17.11** installed locally (binaries zip; EDB installer/CDN was blocked for automated downloads). Server running via `pg_ctl`, data dir `C:\Users\shyam\PostgreSQL\data`. DB `signaldesk` created. Redis deferred (only needed at P1 caching phase).
- **D21.** **Two-file documentation system:** `PLANNING.md` (plan/why) + `PROGRESS.md` (status/what's next/cheatsheet/gotchas). Both updated at end of every phase. `PROGRESS.md` is read first to resume work.

---

### 2026-08-18 - Session 3 (App scaffold executed)
- **D22.** **`.env`/`.env.example` live in `backend/`** (where `alembic`/`uvicorn` run), not repo root. `.gitignore` lives at `signaldesk/` root. (Clarifies §10.)
- **D23.** **Only `DATABASE_URL` + `APP_ENV` are required at startup.** `REDIS_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `FINNHUB_API_KEY` are optional/empty placeholders until their phases. `config.py` uses pydantic-settings with `env_ignore_empty=True`. (Clarifies §10.)
- **D24.** **`daily_prices` uses a surrogate `id` PK + `UNIQUE(stock_id, date)`** (constraint named `uq_daily_prices_stock_date`), not a composite PK. Matches §6. Prices are `Numeric(16,4)`.
- **D25.** **Alembic is async-configured** (`env.py` uses `asyncio.run` + `connection.run_sync`, reusing `app.db` engine/metadata). No `psycopg2` sync driver needed.
- **D26.** **`stocks`/`universes` use a many-to-many association table** `stock_universe` (composite PK) with `relationship()` back-references on both models.
- **D27.** **Git repo initialized** at `signaldesk/` with `.gitignore` (ignores `.env`, `.venv`, caches). No commit made yet.

### 2026-08-18 - Session 4 (provider + ingestion)
- **D28.** **Provider abstraction implemented:** `MarketDataProvider` ABC + `OHLCV`/`StockProfile` dataclasses; `YFinanceProvider` uses `asyncio.to_thread` (yfinance is sync) and raises `MarketDataError`. Ingestion depends on the interface, never yfinance directly.
- **D29.** **Seed + ingestion approach:** static `app/data/nifty50.py` seed (one-time; DB owns universe after). Ingestion reads symbols from the DB, batches via `asyncio.gather` (batch 5), upserts with Postgres `INSERT ... ON CONFLICT DO UPDATE` on `uq_daily_prices_stock_date`. APScheduler daily at 18:30. Verified idempotent (24,499 bars stable) + per-symbol failure isolation.

### 2026-08-18 - Session 5 (API endpoints)
- **D30.** **API sub-phase implemented:** `app/errors.py` (error envelope, `NotFoundError`/`ValidationError`), `app/routers/stocks.py` (list + price history), `app/main.py` (app assembly, `/health`, scheduler wired via **lifespan**). Symbol normalization (bare or `.NS`); `resample` 1d-only in v1; `range` filter full. All endpoints + error envelopes verified via httpx.

### 2026-08-18 - Session 6 (pytest suite → Phase 1 complete)
- **D31.** **Test strategy implemented per §12:** dedicated `signaldesk_test` DB; `tests/conftest.py` uses a **function-scoped** async engine (pytest-asyncio event-loop affinity - session-scoped async engine caused "another operation is in progress"), per-test schema rebuild via `Base.metadata.drop_all/create_all`, and `app.dependency_overrides[get_session]` to redirect requests to the test DB. Providers mocked (`FakeProvider`); `YFinanceProvider` never called. **Phase 1 Definition of Done is MET** - 15/15 tests pass with no network; prod DB untouched.

### 2026-08-18 - Session 7 (Phase 2 SP1: financials)
- **D32.** **`financials` implemented as a point-in-time snapshot** (one row per stock, `UNIQUE(stock_id)` `uq_financials_stock_id`), not per-period (§6's "per reporting period" deferred). Migration `5f7fd30113b1`. Provider gains `Fundamentals` dataclass + abstract `get_fundamentals()`; yfinance maps `info` fields with `_as_float()` NaN/string guard. `ingest_financials()` mirrors price ingestion (batch, isolation, upsert). Real run: 50/50 rows, idempotent. **Scoring must renormalize for missing fields** - yfinance `info` frequently omits ROE/interest-coverage per symbol.

### 2026-08-18 - Session 8 (Phase 2 SP2: services)
- **D33.** **Scoring/valuation/explanation services implemented (pure, no I/O).** `services/scores.py` implements §8b via a single `_linear()` helper + weight renormalization; `services/valuation.py` has `compute_multiple()` + `relative_valuation()` (median, margin, ±5% bands) with domain exceptions `NoPeersError`/`InsufficientDataError` **defined in the service layer** (decoupled from FastAPI; routers map them to the envelope). `services/explanation.py` builds rule-based text from actual components. 44 new unit tests (60 total) pass.

### 2026-08-18 - Session 9 (Phase 2 SP3: repositories + routers → Phase 2 complete)
- **D34.** **Repositories + routers implemented; Phase 2 complete.** Peer selection by `industry` (sector fallback when NULL); `industry` backfilled 49/50 via `seed.backfill_industry()` (TATAMOTORS.NS 404 → sector). New handlers `NoPeersError`→409 `NO_PEERS`, `InsufficientDataError`→422 `INSUFFICIENT_DATA` (reuse §11 envelope). Endpoints live: `/fundamentals` (key_ratios only - statements not stored), `/scores`, `/valuation` (+ `/valuation/explanation`, `?metric=` PE default), `/screener` (`status` + `min_profitability`/`min_solvency` - no ROIC in data). 76/76 tests; verified live vs real DB.

### 2026-08-18 - Session 10 (P2.5 Hardening)
- **D35.** **Hardening phase complete (audit-driven).** (1) `services/analysis.py` centralizes valuation/scores/screener orchestration - routers thin, pure math unchanged. (2) N+1 eliminated: `repositories/prices.py:get_two_latest` (window query; `list_stocks` = 3 queries, guarded ≤5 by test) + `repositories/financials.py:get_financials_batch` (`IN` query for peers). (3) `financials.updated_at` refreshed on upsert. (4) `_with_retry` retry-with-backoff on provider fetches (MarketDataError only, 2 retries, isolation preserved). (5) Request-id structured logging (`app/logging_utils.py` contextvar + ASGI middleware; `X-Request-ID` header; `request_id` in error envelope). (6) 8 new hardening tests (EV_EBITDA/PB/PS, sector fallback, no-financials, query-count, updated_at, retry). Coverage baseline **74%** (84 tests). No Redis/Docker/CI/queues/Prometheus added.

### 2026-08-19 - Session 11 (Phase 3: news + FinBERT sentiment)
- **D36.** **News + sentiment implemented.** `NewsArticle` (unique URL) + `NewsSentiment` (1:1) tables (migration `ed7bb907ca7c`). `NewsProvider` ABC + `GoogleNewsRSSProvider` (feedparser, bare-symbol query). `FinBERTScorer` (lazy, thread-locked pipeline - concurrent `transformers.pipeline` first-imports fail without the lock). `ingest_news()`: race-safe `ON CONFLICT DO NOTHING` upsert by URL + score-unscored; reuses `_with_retry`/D19 isolation. Endpoints `/news` + `/sentiment`. **Live: 1,001 articles ingested+scored (219 pos/159 neg/623 neutral), fully idempotent.** 91/91 tests (7 new, network-free). `published_at` must be `DateTime(timezone=True)`.

### 2026-08-19 - Session 12 (Phase 4: indicators + Alpha Score)
- **D37.** **Technical indicators + Alpha Score implemented.** `services/indicators.py` (pure: SMA20, EMA12, RSI14-Wilder, MACD 12/26/9; `score_technicals` = trend 50/momentum 30/reversion 20, renormalized, 0-100 - heuristics, not predictive models). `services/alpha.py`: **composite = 40% fundamental + 30% technical + 30% sentiment, weights renormalized over available components; valuation kept separate as `value_signal`** (avoids double-counting fundamentals; approved decision). Fundamental reused from `analysis.compute_stock_scores`; sentiment from news summary (-1..+1 → 0..100); insufficient → `composite:null, insufficient_data:true`. `alpha_scores` table (`UNIQUE(symbol,date)`, `components_json` JSONB, migration `b0f48fb7c939`); snapshot upserted at compute time (history for later backtesting). `GET /stocks/{symbol}/alpha`. **118/118 tests (27 new); coverage 76%.** Live TCS: composite 59 (0.4·98+0.3·27+0.3·39) with value_signal fairly_valued.

### 2026-08-19 - Session 13 (roadmap audit)
- **D38.** **Product roadmap audited + classified into 4 tiers.** ETFs and Mutual
  Funds (incl. holdings/overlap) are **CORE PRODUCT VISION** - deferred from the
  MVP, never dropped. New §18 "Long-Term Product Vision + Future Roadmap"
  anchors every feature with tier/phase/priority/dependencies. §14 Phase 7
  corrected to Observability (Redis→S2 conditional; Three.js→gated on MF).
  Overlooked capabilities tracked: aggregate `/overview` endpoint (P6),
  per-period financials, stale-data flags (P7), 429 handling, screener
  precompute. MVP roadmap unchanged; Phase 5 (grounded LLM) is next.

### 2026-08-21 - Session 14 (Phase 5: grounded LLM explanation)
- **D39.** **Grounded LLM explanation implemented on `/alpha` only**, per the approved REV 2 plan.
  - **Provider:** OpenRouter via **raw async httpx** (OpenAI-compatible `chat/completions`) behind an `LLMProvider` ABC. **No OpenAI/Anthropic SDKs.** `LLMResult` carries `text`, `tokens_used` (None-safe), `model` so cost logging needs no separate usage reconstruction.
  - **`LLM_MODEL` is configurable; empty string is the code default = LLM disabled.** No model ID is hard-coded in source; `.env.example` documents a sample (free) model and warns that free OpenRouter models rotate. Model unavailability degrades to the rule-based fallback (non-fatal by design).
  - **Security boundary:** `_alpha_facts()` is an explicit **allow-list** (explicit field serialization, never `AlphaResult.__dict__`/`asdict`), so a future free-text field cannot become an injection path. `value_signal` is limited to structured `metric`/`status`/`margin_pct` - its free-text `explanation` never reaches the prompt.
  - **Output contract enforced in the system prompt** (short ≤3 sentences, no invented numbers, no investment advice, no guaranteed future-return claims, "not investment advice" tag). **No second model polices output** - the prompt boundary + tests are the guardrail.
  - **Fallback chain (all → rule-based `_alpha_narrative()`):** no key → no model → provider `LLMError` (network/non-2xx/malformed) → budget exhausted. `/alpha` never fails and always returns a populated `explanation`.
  - **In-process TTL cache** (24h, keyed `(symbol, date)`) + **in-process daily cap** (`llm_daily_cap`, default 100) + structured `llm_usage tokens= model=` cost logging. **Redis stays deferred.**
  - **Placement:** narrative lives in `services/llm_narrative.py`, not `explanation.py`, to avoid the import cycle `alpha → analysis → explanation → alpha`.
  - **Tests:** `tests/test_llm.py` (15) - allow-list boundary, grounding, output contract, all fallback paths, budget cap, TTL cache, cost logging, and OpenRouter success/non-2xx/malformed/invalid-JSON via mocked httpx (zero network). **133/133 tests; coverage 78%** (from 76%; `llm_narrative.py` 95%). Live `/alpha` verified via the rule-based path (no key configured).
  - **Deferred (intentional):** LLM on `/scores` + `/valuation` (reuse the ABC later), NL screener (STRETCH), Redis/persistent telemetry, storing explanations in `alpha_scores` (no migration this phase).

### 2026-09-04 - Session 15 (Phase 6: production frontend + backend gaps)

- **D40.** **Four smallest-coherent backend additions** (frontend-driven, no refactors):
  (1) CORS from `CORS_ORIGINS` config; (2) `GET /stocks/{symbol}` fills the §9 contract gap with a
  quote block whose fields are **null when data is absent** (the list endpoint's `0.0` sentinel was
  not copied - nulls drive honest UI states); (3) `GET /stocks/{symbol}/technicals` exposes raw
  SMA20/EMA12/RSI14/MACD by **reusing** `services/indicators.py` (no duplicated math - `/alpha`
  only exposed sub-scores); (4) `POST /stocks/{symbol}/explain` for 5 fixed question types.
- **D41.** **`/explain` reuses the Phase 5 LLM architecture exactly**: per-type fact allow-lists
  (`_ALLOWED_FACT_KEYS`) as a second boundary on top of explicit fact-gathering in the router;
  alpha facts reuse `llm_narrative._alpha_facts()` verbatim; same output contract; rule-based
  fallback on every path; own TTL cache keyed `(symbol, question_type, date)`; **one shared daily
  cap** via new public `budget_ok()`/`register_llm_call()` in `llm_narrative.py`. No free-text
  questions → not a chatbot. Metric definitions ("Explain this metric") are static frontend
  registry content (METRIC_INFO), not LLM calls.
- **D42.** **Frontend stack locked:** Vite + React 19 + TypeScript strict, Tailwind v4, shadcn-style
  Radix primitives, TanStack Query (server state) + TanStack Table, React Router lazy routes,
  Framer Motion, Lightweight Charts v5, lucide-react, @fontsource (Libre Caslon Text / Hanken
  Grotesk / JetBrains Mono). Dev transport = Vite proxy `/api` → :8000; `VITE_API_BASE` override
  uses the CORS middleware.
- **D43.** **Design tokens, not templates:** light "Warm Paper + Cobalt" default; dark "Deep Ink +
  Jade" as a genuine alternate token system (class toggle). Semantic band colors
  (80/60/40/20 → strong/positive/moderate/weak/veryweak) are consumed ONLY by analytical
  conclusions (Alpha, component scores, verdicts, valuation state, technical positioning); raw
  metrics stay neutral; valuation carries its OWN state, never inheriting Alpha's color.
- **D44.** **Information system:** METRIC_INFO registry (30+ entries: label, short tooltip,
  popover methodology, optional expandable context) rendered through InfoDot/MetricRow - every
  non-obvious metric on the research page has an affordance, and the registry doubles as a
  completeness checklist (guarded by a test).
- **D45.** **DataState discipline:** loading/empty/insufficient/stale(as-of)/error+retry/unknown-symbol
  states everywhere; 404/NO_PEERS/INSUFFICIENT_DATA never retried; missing data renders honest
  states - the frontend never fills gaps with fake or estimated values, and never recomputes
  backend math (EV/EBITDA comes only from the valuation endpoint).
- **D46.** **Stock detail composition:** one focused API call per section (detail, alpha,
  valuation×4 metrics, scores, fundamentals, prices, technicals, news, sentiment) - cached by
  TanStack Query; all four multiples (P/E, EV/EBITDA, P/B, P/S) show their own peer medians;
  valuation verdict + relative-position marker per selected metric; expandable EV/EBITDA/market-cap
  inputs kept secondary. Technical Positioning wording (Bearish etc.) is presentation logic
  client-side over aggregate sub-scores - the stock itself is never labeled bearish/bullish.
- **D47.** **Markets scales by API pagination** (server page/limit; one 25-row page in the DOM),
  ready for Nifty 500; screener exposes exactly the backend's filters (status, min
  profitability/solvency).
- **D48.** **Landing is an editorial argument on real data**: hero sparkline + product preview +
  universe strip read the live API (with honest error states), the Alpha-states demo (82/59/34) is
  explicitly labeled as design-system examples, ETF/MF coverage is presented as roadmap - no fake
  capabilities, testimonials, or pricing. Motion communicates (reveals, count-ups, convergence),
  never decorates.
- **Verified:** backend 155/155 (22 new zero-network tests); frontend tsc clean, vitest 38/38,
  vite build OK; live uvicorn+Vite integration (CORS headers, preflight, real RELIANCE
  detail/technicals/explain/valuation/alpha/screener, 422 bad question type, 404 unknown symbol,
  deep-link SPA fallback). Design-reference folders git-ignored.

---

### 2026-09-05 - Session 16 (Phase 6.5: experience overhaul)

- **D49.** **Copy discipline is a hard rule**: no em dashes and no AI-tell
  wording ("grounded", "deliberately", "defensible", "honest", "quiet",
  "unglamorous" and similar) anywhere user-visible or in comments; the
  null placeholder is "-" (standard financial convention, and it keeps the
  no-em-dash guarantee); explanation disclaimers normalize to "Generated from
  SignalDesk data. Not investment advice."; the landing "Grounded" section was
  renamed ExplainerSection (single definition + import) so the banned word is
  gone from identifiers too.
- **D50.** **Typography floor**: body/UI is Instrument Sans, data is IBM Plex
  Mono with ONLY weights 500/600/700 loaded (no 400 face exists, so any
  implicit 400 request, including the chart canvas, resolves to the 500 face
  per CSS font matching); Libre Caslon Text stays for display; 12px minimum
  for every data/UI text (54 sub-12px instances removed); `.num` carries a
  500 weight floor; `.label-caps` is 12px/600. Weights were tuned per role,
  not bumped globally (body prose stays 400).
- **D51.** **Dimension accents**: jade=fundamentals, amber=valuation,
  coral=technicals, teal=sentiment, exposed as Tailwind `accent-*` tokens.
  Accents appear only where they communicate which dimension is speaking
  (framework cards, hero chips, structure rows, universe bars, flow lines);
  raw metrics and market colors stay neutral/green-red.
- **D52.** **Two approved themes, one token shape**: light "Cloud White +
  Petrol" graded from the approved reference concept (bg #f8f9ff, cards #fff,
  ink #0b1c30, identity #006781, borders #ccd5e6/#b7c5de, navy primary
  buttons); dark "Warm Ink + Gold" (bg #131110, ink #f2ede0, identity
  #e3b34c) is unchanged by the light regrade. The `--cobalt` token carries
  the identity in both themes so interactive color re-skins as one. Dark is
  the first-visit default; a stored preference always wins.
- **D53.** **No photographs**: stock imagery was tried and rejected in review
  (artificial placement, blend-mode compositing cost). The landing uses
  authored SVG plates instead (CandleField, UniverseGrid), explicitly labeled
  "Illustrative"; the bundle ships zero raster images and zero blend modes.
- **D54.** **Landing interactivity and motion budget**: MarketPulse is a
  continuous marquee of ALL 50 real constituents (CSS transform, pauses on
  hover, reduced-motion renders a static scrollable row); CandleField is
  hover/tap interactive with an illustrative OHLC readout; framework cards
  are selectable (accent border + dim logic); metric chips spring-hop on
  hover; ScrollPulse is a uniform-sine right rail whose dot travels the exact
  arc length of the path with scroll. Glass (blur) is limited to three small
  panels; washes are static radial gradients; everything animates with
  opacity/transform only and respects prefers-reduced-motion.
- **D55.** **Charts stay interactive in both themes**: the Lightweight Charts
  crosshair uses dashed faint lines with petrol axis labels (the previous
  rule-colored hairlines were invisible in light mode, making hover feedback
  look broken); canvas text is IBM Plex Mono at 12px.
- **Verified:** tsc clean; vitest 43/43 (5 new pickTopMovers tests); vite
  build OK; zero raster images in dist; pulse math verified against the live
  /stocks response; pushed as 3efb78d on main.

---

### 2026-09-05 - Session 17 (Phase 6.5 parts E/F/G: historical financials, dual providers, news)

- **D56.** **Historical financial data model**: `financial_periods` table
  (migration `a844177fa25e`) keyed UNIQUE(stock_id, period_end, period_type);
  every metric nullable; `source` records yfinance/upstox/merged. Missing
  history is contractual: nulls and `insufficient_data` flags, never
  interpolated or fabricated. Margins are computed backend-side from the
  same period's figures. `get_financial_history()` is an optional provider
  capability (ABC default raises NotImplementedError; callers treat that as
  "no history available", not a failure).
- **D57.** **Five research endpoints** (router `history.py`, read-only over
  the DB): `GET /stocks/{symbol}/performance` (windowed returns + 52w range),
  `/alpha/history` (stored snapshots, oldest first), `/technicals/series`
  (SMA20/EMA12/RSI14/MACD per stored bar via new series variants in
  `services/indicators.py`, pinned equal to the scalar functions by tests),
  `/peers` (reuses the industry-keyed peer repository so it can never
  disagree with valuation), `/financials/history`. The backend owns all
  math; the frontend renders.
- **D58.** **Upstox integration (verified against official docs before
  implementation)**: the "Analytics Token" is a manually generated access
  token used as `Authorization: Bearer` for read-only v2 APIs (historical
  candles, fundamentals income-statement/key-ratios/profile); no interactive
  OAuth. The token lives only in `backend/.env` via
  `settings.upstox_analytics_token`, is never logged or sent to the
  frontend, and `.env.example` carries an empty placeholder. Symbols map to
  Upstox instrument keys through the official NSE instruments master
  (`assets.upstox.com`, segment NSE_EQ, cached per process). Income
  statements arrive in crore and are converted to rupees so units match
  yfinance; unparseable period labels are skipped, unknown units refused.
- **D59.** **MergingProvider and provider selection**: yfinance stays
  PRIMARY (free, no key, proven); Upstox is the SECONDARY gap-filler.
  Prices merge newest-window-first with primary winning same-date
  collisions, secondary gap-filling missing dates, and per-bar source
  attribution on `OHLCV.source`. Fundamentals coalesce field-by-field;
  material disagreement (> 5% relative) keeps the primary and logs both
  values (never credentials). Financial history coalesces per
  (period_type, period_end) with per-row source. `build_default_market_provider()`
  returns yfinance-only when no token is configured; any secondary failure
  degrades to primary-only for that call. All merge logic is pure and
  tested without providers.
- **D60.** **News relevance and freshness**: the primary search query is the
  company's full name from the catalog; the bare-symbol query is a fallback
  only when the name search yields no usable results. BOTH result sets pass
  the same filter: bare-symbol mention (>= 4 chars, word-bounded) OR all
  distinctive name tokens (corporate suffixes stripped). This blocks
  generic nouns and unrelated symbol matches at the cost of occasional
  false negatives ("SBI" without the full name), an accepted precision-over-
  recall trade. The ~30-day freshness window applies at ingestion and
  display; undated articles cannot be proven stale and are kept; sentiment
  processing is unchanged.
- **Data-quality findings (real 8-stock check: RELIANCE, TCS, INFY,
  APOLLOHOSP, HDFCBANK, ICICIBANK, SBIN, LT):** daily bars agree exactly
  across providers; Upstox fills ROE/ROA gaps yfinance omits (RELIANCE,
  APOLLOHOSP, LT); yfinance `.info` defects confirmed (INFY P/S 225.5x and
  EBITDA off by ~10x); Upstox P/E differs up to ~15% (trailing basis
  differences - primary wins and logs); Upstox provides no market cap, P/S,
  EV, or EBITDA absolutes, so those fields cannot be filled from it.
- **Verified:** backend pytest **232/232** (77 new, zero network); migration
  applied (`alembic current` = a844177fa25e); real ingestion 50/50 symbols,
  228 periods, 0 errors through the merged provider; real 8-stock provider
  quality check performed; backend starts, `/health` ok; `git ls-files
  backend/.env` empty.

---

### 2026-09-06 - Session 18 (Phase 6.5 Part D: stock research page expansion)

- **D61.** **Collapsible research sections without a redesign**: the stock
  page keeps the approved visual language; Valuation, Fundamentals,
  Technicals, News and Methodology gain a `CollapsibleSection` shell whose
  header row is the toggle, while Alpha (plus its new history chart) and the
  primary price chart stay open. Collapsed content stays mounted (hidden via
  CSS) so queries keep the same caching behavior and collapsed summaries are
  always data-backed. Summaries are presentation strings from pure, tested
  builders (`lib/summaries.ts`) fed by the same query data the sections
  render: a section with insufficient data shows no summary and never
  invents one.
- **D62.** **Backend owns the new math**: `/performance` gained
  `volatility_1y_pct` (sample stdev of daily simple returns x sqrt(252),
  null under three closes) and `/peers` gained ROE/profit margin/D/E from
  the already-batched financials snapshot - the two smallest-coherent
  additions that let the frontend render performance strips and peer tables
  without recomputing anything client-side. Frontend additions (performance
  strip, alpha history chart, indicator series charts, peer table,
  multi-year financial charts) are pure consumers of Part E endpoints via
  the shared `TimeSeriesChart` (Lightweight Charts; null gaps render as
  whitespace points, never interpolations).
- **D63.** **Missing-data rendering contract on the research page**: a
  missing performance window, peer cell or financial period renders "-" with
  the DataState system carrying loading/empty/insufficient/stale/error and
  unknown-symbol states; a rendered zero is always a real zero; insufficient
  sections (e.g. TATAMOTORS with no bars) show explicit insufficient notes.
- **Verified:** backend pytest **234/234**; frontend tsc clean, vitest
  **59/59**, `vite build` OK; live smoke of all five Part E endpoints
  (RELIANCE data-rich incl. an honestly missing 2Y window anchor,
  TATAMOTORS insufficient on every endpoint, unknown symbol 404 envelope);
  production preview deep link + API proxy verified; git diff reviewed.

---

### 2026-09-06 - Session 19 (review round: Nifty 250, data refresh, research UX)

- **D64.** **Universe expansion to the official Nifty 250**: constituents
  sourced from the NSE indices lists (nifty50 + nifty100 + midcap150 =
  250 symbols, downloaded 2026-09-06) and committed as seed data;
  `seed.py` maintains the nifty50/nifty100/nifty250 ladder idempotently
  (prunes dropped constituents, normalizes names/sectors to the NSE
  taxonomy) and ingestion runs against nifty250. The universe remains data,
  not code (D16) - the seed file is a one-time bootstrap.
- **D65.** **Valuation multiple fallback**: when the stored snapshot cannot
  produce a multiple, the pre-computed ratio comes from Upstox key ratios
  (P/E, P/B, EV/EBITDA) with a 1-hour in-process cache; applied to the
  target and peers. This removes the "Cannot compute EV_EBITDA" failure
  class (yfinance `info` omits EBITDA for many NBFCs) without inventing
  values: the ratio is real provider data, its provenance logged.
- **D66.** **Upstox fundamentals enrichment + quarterly history**:
  `get_fundamentals` derives operating margin, net margin, current ratio
  and debt/equity from the Upstox income-statement and balance-sheet APIs
  (converted to the snapshot's decimal/percent conventions) so solvency
  components exist where yfinance is sparse; `get_financial_history`
  gained a period_type parameter and the job stores annual + quarterly.
- **D67.** **Retroactive alpha history**: a backfill job computes a daily
  snapshot for every stored trading day using the closes up to that date.
  Fundamental and sentiment are point-in-time metrics with no history, so
  historical composites renormalize to technical only - the same rule the
  live score uses; backfilled rows never overwrite full live snapshots
  (conditional bulk upsert on `fundamental IS NULL`). The graph is real
  indicator math on real stored prices, ~500 points per stock.
- **D68.** **News widened (precision trade-down, product decision)**:
  60-day freshness window, relevance relaxed to any-distinctive-token, and
  the symbol query merges into the results whenever the name search yields
  fewer than 8 usable articles (dedup by URL). Known cost: titles matching
  only one generic-ish token can pass; accepted to keep the research page
  supplied with at least 8 articles.
- **D69.** **Logos without remote assets**: company marks are deterministic
  monogram discs (symbol-hash into the accent palette) so rows can carry a
  visual identity with zero network requests and zero 250-asset maintenance;
  real logo CDN integration is deliberately deferred.
- **D70.** **Auto-refresh limitation (future scope)**: the daily ingestion
  scheduler runs inside the backend process; data only advances while that
  process is alive. Unattended daily updates require a deployed worker or
  OS-level scheduler - tracked for the deployment phase, not solved
  client-side or with a fake cron.
- **D71.** (2026-09-06, Session 20) **Alpha history is a real blend, never a
  technical-only collapse**: the retroactive backfill holds each stock's
  latest known fundamental and sentiment scores constant across the window
  (they are slow-moving point-in-time metrics with no stored history) and
  computes the true 40/30/30 composite per day, then REPLACES the symbol's
  stored snapshots so formula changes propagate. Live /alpha requests rebuild
  today's snapshot on the next page view.
- **D72.** (2026-09-06, Session 20) **Technical score calibration**: sub-score
  sensitivity softened (trend: ±20% vs SMA20 spans 0-100; momentum: ±2%
  MACD-histogram/price spans 0-100) and the composite is an EMA(5) of the
  daily raw scores (`score_technicals_series`). The scalar
  `score_technicals` is the last entry of the series, so live scores and the
  backfill are one math. Rationale: a research signal should drift, not
  sawtooth with single-day indicator noise.
- **D73.** (2026-09-06, Session 20) **Research-page visual system**: every
  chart carries a single vertical date tracker (no horizontal price line or
  axis bubble - values live in the readouts); technical series default to
  250 bars (one trading year) for legibility; sections alternate on a
  `--section-alt` background token (light: slightly darker cool white, dark:
  lighter warm ink) with `.glass` reserved for small/medium panels (alpha
  history, evidence, explanation, peers, performance).
- **D74.** (2026-09-06, Session 20) **Peers table interaction**: six sortable
  metric columns (price, 1D, P/E, ROE, net margin, D/E; nulls sort last in
  both directions), three peers visible by default with a show-all/show-less
  footer toggle.
- **D75.** (2026-09-06, Session 20, Part H) **`POST /stocks/{symbol}/ask` -
  grounded single-shot ask, evidence-only architecture**: the backend builds
  an explicit allow-listed evidence object (company, quote, alpha + value
  signal, technicals, P/E valuation, fundamentals, performance + volatility,
  sentiment, last five annual periods, methodology) and double-filters it
  (`filter_evidence`, top level + one nested level). The user question is
  untrusted input: sanitized, 500-char capped (raw length), scope-classified
  (clearly off-topic → no LLM spend), and embedded in the prompt as a quoted
  data string while the system prompt forbids instruction-following from it,
  advice, invented facts, and external-source claims. Strict JSON output
  contract `{"answer", "evidence", "confidence"}` validated in the backend;
  malformed output falls back to a deterministic rule-based answer built from
  the same evidence. Single-shot only: no conversation memory, no thread.
- **D76.** (2026-09-06, Session 20, Part H) **Ask operations**: 15-minute
  in-process TTL cache per (symbol, question); the SHARED Phase 5 daily cap
  (`llm_narrative.budget_ok/register_llm_call` - one counter across /alpha,
  /explain and /ask); model availability verified against the OpenRouter
  catalog (10-min memo) before the first real request; OpenRouter's
  workspace prompt-injection guardrail is the provider-side layer (never
  recreated in-app) and a 403 from it maps to a safe generic `ASK_BLOCKED`
  error with no guardrail internals exposed. `LLM_API_KEY` is primary with
  `OPENROUTER_API_KEY` accepted as an alias (the alias wiring was required -
  the dev .env only set the latter, silently disabling the LLM).
- **Verified (Session 20):** backend pytest **259/259** (was 238 before Part
  H's 21 ask tests; alpha/indicator suites updated for the new score math);
  frontend tsc clean, vitest **59/59**, `vite build` OK; alpha history
  recomputed in the dev DB (119,707 snapshots, all real blends; RELIANCE
  average daily composite delta ~0.25 pts, range 51-60); ONE real OpenRouter
  request (`POST /stocks/RELIANCE/ask`) returned 200 with `source: "model"`,
  grounded answer (Alpha 54; P/E 23.92 vs peer median 7.87) and a 5-item
  evidence list, model `minimax/minimax-m3:free` (availability verified
  first). `git ls-files backend/.env` returns nothing; no secrets in the diff.
- **D77.** (2026-09-06, Session 20 follow-up) **Charts never build at zero
  width; even grid backgrounds**: chart components (PriceChart,
  TimeSeriesChart) gate creation on a real container width (ResizeObserver
  gate + rebuild on visibility) because collapsible sections keep content
  mounted with `hidden` - a chart created at width 0 renders squished/offset.
  Vertical grid lines are disabled everywhere: the time scale's calendar
  ticks sit at uneven trading-day distances, so horizontal-only reference
  lines keep the background regular; the hover date tracker remains.
- **D78.** (2026-09-06, Session 20 follow-up) **Financials history views**:
  quarterly results are the default view of the historical financials chart.
  Larger buckets are BACKEND-derived (the frontend never aggregates):
  `group=half_yearly` sums two consecutive fiscal quarters and
  `group=three_yearly` sums three consecutive fiscal years on
  `/financials/history`. Revenue/net income are summed over periods that
  carry them, net margin is recomputed from the sums, operating margin is
  revenue-weighted, EPS is never summed across periods, and every grouped
  row declares `aggregated_from`. Yearly view = stored annual rows; missing
  granularities show an honest insufficient state.
- **Verified (Session 20 follow-up):** backend pytest **262/262** (3 new
  grouping tests), frontend tsc clean, vitest **59/59**, build OK; live
  checks: `POST /stocks/BEL/ask` ("should i buy it") → 200 grounded
  advice-refusing model answer after the stale backend was restarted, and
  `GET /stocks/BEL/financials/history?period_type=quarterly&group=half_yearly`
  → correct fiscal-half buckets.
### 2026-09-06 - Session 22 (deployment cost strategy)
- **D79.** **Deployment decouples ingestion from the API process to avoid paying for
  always-on hosting.** The in-process APScheduler (D29) only advances data while
  `uvicorn` is alive (D70) - naive deployment would require a paid always-on web
  service tier (~$5-7/mo) plus a persistent Postgres instance (~$5-10/mo) just to
  keep that scheduler reliable, roughly $10-15/mo total. Instead:
  - **Frontend:** static hosting (Vercel/Netlify/Cloudflare Pages) - free tier,
    no meaningful limits at this scale.
  - **Backend API:** can run on a free tier that sleeps between requests, because
    it is no longer responsible for scheduling - a cold start on an occasional
    user request is an acceptable tradeoff, not a data-freshness problem.
  - **Database:** an autosuspend/serverless-Postgres free tier (Neon or Supabase)
    rather than an always-on managed instance - wakes on query, costs nothing idle.
  - **Ingestion trigger:** a scheduled GitHub Actions workflow (free on public
    repos) replaces the in-process APScheduler as the thing that fires daily -
    it calls the existing `python -m app.jobs ingest` entrypoint (or an internal
    ingestion endpoint) on a cron schedule, independent of whether the API
    process happens to be awake. This is strictly more reliable than the
    in-process scheduler, not just cheaper.
  - **Net cost: $0/month** for hosting; optional ~$10-15/year only if a custom
    domain is wanted. LLM cost stays $0 on free OpenRouter models, unchanged.
  - **Relationship to Semester 2:** this is a lightweight preview of the
    already-planned "split monolith -> API server + background worker" item
    (§14 Semester 2) - it proves the decoupling concept now, cheaply, without
    RabbitMQ/Docker; the full distributed version remains the Semester 2 upgrade,
    not replaced by this.
  - **Consequence for Phase 7 (Observability):** `stale: true` flag work (already
    planned, §14) becomes more important under this model, not less - a
    sleep-tolerant API + externally-triggered ingestion means the frontend must
    be able to honestly tell the user how old the data is, since "the process
    has been running" is no longer a safe assumption to make silently.

- **D80.** (2026-09-06, Part I) **Header stock search is client-side over
  the real catalog**: the site header gains a search box that matches ticker
  (with or without ".NS") AND company name against the cached /stocks
  response (250 constituents, no separate search endpoint, nothing
  fabricated). Ranking: symbol-prefix > symbol-substring > name-prefix >
  name-substring; keyboard navigation (arrows/Enter/Escape) and monogram
  results, deep-linking to the research page. Pure matcher lives in
  `lib/search.ts` (unit-tested).
- **D81.** (2026-09-06, Part I) **No carried-forward component history**:
  alpha backfill rows store ONLY the composite (latest-known blend, D71) and
  the real technical score; fundamental/sentiment are NOT written for dates
  that never had live snapshots - a flat carried-forward line would present
  today's values as daily observations. Component lines appear in the alpha
  history chart only as genuine /alpha snapshots accumulate.
- **Part I verification (2026-09-06, Phase 6.5 close-out):** backend pytest
  **262/262**; frontend tsc clean, vitest **65/65** (8 files, incl. 6 new
  search-matcher tests), `vite build` OK; E2E smoke against the live dev
  server + real stored data **47/47** (catalog, detail, valuation,
  fundamentals, technicals + series, news/sentiment, alpha + history,
  performance, peers, financials incl. grouped views, real LLM ask +
  explain, insufficient-data behavior, unknown-symbol envelope, 422
  envelopes, SPA deep-link routing, vite proxy with preserved error
  envelope). Data-quality audit: 250/250 stocks priced to 2026-09-04 (last
  trading day), 0 malformed/duplicate bars, stored net margins match
  NI/revenue exactly (drift 0.00000), alpha composites all bounded, the one
  literal-zero ratio (BSE D/E 0.00) is genuine, the all-null snapshot
  (TATAMOTORS - provider data gap post-demerger) stays honestly null, no
  carried-forward component history remains (0 rows). Security: frontend has
  zero references to Upstox/OpenRouter/LLM model/API keys (only public
  VITE_API_BASE), backend/.env untracked and ignored, no mock data in
  production paths.

---

*Append new decisions below with date + ID (D21, D22, ...).*

---

## 18. Long-Term Product Vision + Future Roadmap

> Added 2026-08-19 (roadmap audit). Defines the 4-tier product taxonomy and
> anchors every feature so nothing is dropped casually.

### Tiers
1. **CORE PRODUCT VISION** - the product's long-term identity (2-4+ semesters).
2. **CORE MVP / Semester 1** - built now; drives the differentiator.
3. **SEMESTER 2** - distributed + expansion with real justification.
4. **STRETCH / OPTIONAL** - useful but time-gated; safe to defer.

### Core investment coverage (product vision)
- **Indian stocks** (Nifty 50 → 200 → 500): CORE MVP, shipped Phases 1-4.
- **ETFs**: CORE VISION (S2). Same OHLCV model + `.NS` symbols; ETF fields (AUM/TER).
- **Mutual funds (NAV)**: CORE VISION (S2). AMFI CSV → `mutual_funds`/`mf_nav_history`.
- **MF holdings / overlap analysis**: CORE VISION (S2→S3). Fund-house Excel/CSV/PDF →
  `mf_holdings`; overlap service; Three.js graph is its visualization.
- **Derivatives (F&O)**: DROP (D2).

### Research layer
- Historical financial trends (STRETCH; requires per-period `financials` - not yet stored)
- Structured risk engine (STRETCH)
- Bull vs Bear thesis (STRETCH; grounded LLM, post-P5)
- "What should I pay attention to?" summary (STRETCH; grounded LLM)
- Earnings/event timeline (STRETCH; needs a new event provider)
- Scenario/stress testing (STRETCH)
- **Grounded LLM narrative**: CORE MVP - Phase 5.

### Valuation / analysis
- Relative valuation: CORE MVP (done). DCF: S2. Alpha Score: CORE MVP (done).
  Backtesting: STRETCH (needs alpha/valuation history). Live prices: S2 (Finnhub WS).

### Product
- Research pages (P6 - SHIPPED), Screener (backend + UI P6 - SHIPPED), NL screener (STRETCH),
  Watchlists + Auth (STRETCH, S2). Aggregate `/overview` endpoint (P6 tracked item) - not needed
  for the landing preview; deferred to P7 consideration.

### Engineering
- Observability (P7), Deployment (P8), Redis (STRETCH, only if measured load
  justifies), API/worker split + RabbitMQ + Docker + CI/CD + Monitoring (S2),
  industry indexes (S2, before Nifty-500).

### Deltas from this audit
- §14 Phase 7 becomes **Observability** (Redis deferred to S2 conditional;
  Three.js gated on MF).
- §2 reframes the MF tracker as CORE PRODUCT VISION deferred (not "demoted").
- Overlooked items tracked: aggregate `/overview` endpoint (P6), per-period
  financials, stale-data flags (P7), 429 rate-limit, screener precompute job.
