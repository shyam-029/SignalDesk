# SignalDesk — Progress Log

> **Purpose:** The operational counterpart to `PLANNING.md`. This is the file to read FIRST to pick up
> where we left off. Updated after every phase.
> **Rules:** What's done → in progress → next. Command cheatsheet. Known gotchas.
> **Last updated:** 2026-08-19 (Session 12 — Phase 4 complete: technical indicators + Alpha Score)
> **Roadmap audit completed 2026-08-19 — see PLANNING §18 (4-tier product taxonomy).**

---

## 1. Current Status

| Phase | Status |
|---|---|
| 1 — Environment setup | ✅ **COMPLETE** |
| 1 — App scaffold (config, models, migration) | ✅ **COMPLETE** |
| 1 — yfinance provider + Nifty 50 ingestion | ✅ **COMPLETE** |
| 1 — First endpoints + error handling + startup | ✅ **COMPLETE** |
| 1 — pytest suite (providers mocked) | ✅ **COMPLETE** |
| **Phase 1 — Definition of Done (see PLANNING §16)** | ✅ **MET** |
| 2 — SP1: Financials model + provider + ingestion | ✅ **COMPLETE** |
| 2 — SP2: Scoring + valuation services | ✅ **COMPLETE** |
| 2 — SP3: Repositories + routers + screener | ✅ **COMPLETE** |
| **Phase 2 — Relative valuation + fundamental scores** | ✅ **COMPLETE** |
| 2.5 — HARDENING (analysis service, N+1, retry, logging, coverage) | ✅ **COMPLETE** |
| 3 — News RSS ingestion + FinBERT sentiment | ✅ **COMPLETE** |
| 4 — Technical indicators + Alpha Score composite | ✅ **COMPLETE** |
| 5 — Grounded LLM explanation | ⏳ **NEXT UP** |

**One-line status:** Phase 4 COMPLETE — SMA/EMA/RSI/MACD indicators, Alpha Score composite
(40/30/30 renormalized + separate value signal), `alpha_scores` snapshot table, `/alpha` endpoint,
118/118 tests green, coverage 76%. Next: Phase 5 (grounded LLM explanation).

---

## 2. Completed Work

### Session 12 — Phase 4: technical indicators + Alpha Score (2026-08-19)
- [x] `app/services/indicators.py` — pure functions: SMA20, EMA12 (SMA-seeded), RSI14 (Wilder, avgLoss=0→100), MACD 12/26/9 (line/signal/histogram). `score_technicals()` = trend 50% + momentum 30% + reversion 20%, renormalized over available components, bounded 0-100.
- [x] `app/models.py` — `AlphaScore` (symbol, date, fundamental/technical/sentiment/composite Numeric, `components_json` JSONB, updated_at; `UNIQUE(symbol,date)`). Migration `b0f48fb7c939`.
- [x] `app/repositories/prices.py` — added `get_close_series(stock_id, limit)` (chronological closes for indicators).
- [x] `app/repositories/alpha.py` — `get_latest` + `upsert_snapshot` (idempotent ON CONFLICT by symbol+date, refreshes updated_at).
- [x] `app/services/alpha.py` — composite = 40% fundamental + 30% technical + 30% sentiment, weights renormalized over available components; fundamental = mean(profitability, solvency) via `analysis.compute_stock_scores` (reused); sentiment from `news_repo.get_sentiment_summary` mapped -1..+1→0..100; **valuation kept separate** as `value_signal` (via `analysis.compute_stock_valuation`, swallowed NoPeers/Insufficient so alpha never fails).
- [x] `app/routers/alpha.py` — `GET /api/v1/stocks/{symbol}/alpha`; persists a snapshot at compute time.
- [x] Tests: `test_indicators.py` (16) + `test_alpha.py` (11). **Full suite: 118/118 passed.**
- [x] **Live verification:** TCS → composite 59 (fund 98/tech 27/sent 39 → 0.4·98+0.3·27+0.3·39=59.0 ✓), value_signal fairly_valued P/E 16.56 vs 17.31, components explain the low technical (weak trend 31.4 / momentum 3.8). Snapshot persisted.
- [x] Coverage rose to **76%** (from 74%).

### Session 11 — Phase 3: news RSS + FinBERT sentiment (2026-08-19)
- [x] **Deps:** torch (CPU), transformers 5.15, feedparser 6.0.14 added to requirements. FinBERT model `ProsusAI/finbert` downloaded (~420MB, cached by huggingface).
- [x] `app/models.py` — `NewsArticle` (unique `uq_news_articles_url`, timezone-aware `published_at`) + `NewsSentiment` (1:1, unique `uq_news_sentiment_article_id`, score/label/model).
- [x] Migration `ed7bb907ca7c` ("add news tables") generated + applied.
- [x] `app/providers/news_base.py` — `NewsProvider` ABC + `Article` dataclass (mirrors `MarketDataProvider`).
- [x] `app/providers/rss_provider.py` — `GoogleNewsRSSProvider` (feedparser via `asyncio.to_thread`, `NewsProviderError`, query strips `.NS` suffix).
- [x] `app/providers/sentiment.py` — `FinBERTScorer` (lazy, **thread-locked** pipeline singleton; `score_text_async` off the event loop).
- [x] `app/jobs.py` — `ingest_news()`: fetch → `ON CONFLICT DO NOTHING` upsert by URL (race-safe under concurrent symbols) → score unscored articles. `_with_retry` + per-symbol isolation reused. Wired into `_ingest_all`.
- [x] `app/repositories/news.py` — `get_articles` (eager sentiment, newest first) + `get_sentiment_summary` (weighted net score -1..+1).
- [x] `app/routers/news.py` — `GET /stocks/{symbol}/news` + `GET /stocks/{symbol}/sentiment`; registered in main.py.
- [x] `tests/test_news.py` — 7 tests (fake provider + fake scorer, no network): insert+score, idempotency, failure isolation, both endpoints, 404, no-news.
- [x] **Full suite: 91/91 passed.**
- [x] **Live run:** 50/50 symbols, **1,001 articles ingested + all scored** (219 pos / 159 neg / 623 neutral). Re-run fully idempotent (0/0/0). Live endpoints verified (RELIANCE: 20 articles, sentiment score -0.0392/neutral).

### Session 10 — P2.5 Hardening (2026-08-18)
- [x] **N+1 eliminated in `list_stocks`** — new `repositories/prices.py:get_two_latest` (one `ROW_NUMBER()` window query) replaces the per-stock loop. `list_stocks` = 3 queries total. Guarded by query-count test (`test_list_stocks_query_count_is_bounded` asserts ≤5).
- [x] **N+1 eliminated in screener/valuation** — new `repositories/financials.py:get_financials_batch` (single `IN` query) replaces per-peer financials lookup.
- [x] **Analysis service extracted** — `services/analysis.py` centralizes `compute_stock_valuation` / `compute_stock_scores` / `analyze_stock`; `valuation.py` + `scores.py` + `screener.py` routers are now thin. Pure math stays in `valuation.py`/`scores.py`.
- [x] **`financials.updated_at` refreshed on upsert** — `jobs.py` upsert `set_` now includes `func.now()`. Test asserts it moves on re-ingest.
- [x] **Retry-with-backoff** — `jobs.py:_with_retry` wraps provider fetches (prices + financials), 2 retries, exponential backoff, isolates on final failure (D19 preserved). Tests: transient-fails-then-succeeds (3 calls) + always-fails (1 error, no crash).
- [x] **Request-id structured logging** — `app/logging_utils.py` contextvar + ASGI middleware; every request logs `request_id/method/path/status/duration_ms`; `X-Request-ID` response header; `request_id` added to error envelope.
- [x] **Missing tests added** (`tests/test_hardening.py`, 8): EV_EBITDA/PB/PS via HTTP, industry-NULL→sector fallback, no-financials `/fundamentals`, query-count guard, `updated_at` refresh, retry behavior.
- [x] **Coverage baseline** — `pytest-cov` added; **74% overall** (84 tests). Low spots intentional: `seed.py` 0% (ops script, needs network), `yfinance_provider.py` 20% (providers mocked per §12).
- [x] **Measured results recorded** — live: `GET /stocks` (50 rows) ~489ms, `GET /screener` (full 50) ~467ms (first-call incl. pool warmup). `list_stocks` query count bounded at 3 (was ~2N+1).
- [x] **Full suite: 84/84 passed.**

### Session 9 — Phase 2 SP3: repositories + routers + screener (2026-08-18)
- [x] `app/seed.py` — added `backfill_industry()` (batched, idempotent, per-symbol isolation). **Ran: 49/50 industry populated** (TATAMOTORS.NS 404 → sector fallback). Industry groups: 6 banks, 5 IT, 5 auto, etc.
- [x] `app/repositories/stocks.py` — `get_stock`, `get_peers` (industry → sector fallback), `list_all_symbols`.
- [x] `app/repositories/financials.py` — `get_financials_row`, `to_key_ratios`, `get_financials` (ORM→`Fundamentals`).
- [x] `app/errors.py` + `app/main.py` — new handlers: `NoPeersError`→409 `NO_PEERS`, `InsufficientDataError`→422 `INSUFFICIENT_DATA`.
- [x] Routers: `fundamentals.py`, `scores.py`, `valuation.py` (+explanation), `screener.py`; `common.py` (symbol normalize/resolve).
- [x] Route registration verified — 8 API paths in OpenAPI spec.
- [x] Tests: `test_repositories.py` (7) + `test_analysis_api.py` (11). **Full suite: 76/76 passed.**
- [x] **Live smoke test vs real DB:** TCS valuation → P/E 16.56 vs 4 IT peers (median 17.31, fairly valued); TCS scores (profitability 97, solvency 100); screener surfaces 16 undervalued stocks.

### Session 8 — Phase 2 SP2: scoring + valuation + explanation services (2026-08-18)
- [x] `app/services/scores.py` — §8b piecewise-linear scoring: `_linear()` helper, `profitability_score()`, `solvency_score()`, `ComponentScore`/`Component`; weight renormalization + missing/negative handling.
- [x] `app/services/valuation.py` — `compute_multiple()` (PE/EV_EBITDA/PB/PS), `relative_valuation()` (peer median, margin, ±5% bands), domain exceptions `NoPeersError`/`InsufficientDataError` defined in the service layer (per approved design).
- [x] `app/services/explanation.py` — rule-based `profitability_explanation`/`solvency_explanation`/`valuation_explanation` from real components.
- [x] Tests: `test_scores.py` (16), `test_valuation.py` (17), `test_explanation.py` (7) — 44 new, all pure/unit, no DB/network.
- [x] **Full suite: 60/60 passed.**

### Session 7 — Phase 2 SP1: financials model + provider + ingestion (2026-08-18)
- [x] `app/models.py` — added `Financials` model (one row/stock, `UNIQUE(stock_id)` `uq_financials_stock_id`; valuation + profitability + solvency columns, `updated_at`).
- [x] Migration `5f7fd30113b1` ("add financials table") generated + applied; verified in Postgres.
- [x] `app/providers/base.py` — added `Fundamentals` dataclass (raw provider values) + abstract `get_fundamentals()`.
- [x] `app/providers/yfinance_provider.py` — implemented `get_fundamentals()` mapping yfinance `info`; `_as_float()` helper guards NaN/inf/string values → None.
- [x] Verified provider: `RELIANCE.NS` (P/E 23.9, EV 21T, EBITDA 1.8T) + `TCS.NS` (ROE 47.7%).
- [x] `app/jobs.py` — added `ingest_financials()` (batched, per-symbol isolation, upsert on `uq_financials_stock_id`) + `_ingest_all()` (prices then financials) wired into scheduler.
- [x] `tests/test_financials.py` — 5 tests: interface compliance, fake-provider values, upsert, idempotency, failure isolation.
- [x] Real ingestion: **50/50 rows**, re-run idempotent (stays 50). Prod prices/stocks untouched.
- [x] **Full suite: 20/20 passed** (~6s, no network).
- [x] **Data insight:** yfinance `info` often omits `return_on_equity`/`interest_coverage` per symbol → scoring renormalization (drop missing, reweight) is essential.

### Session 6 — pytest suite (2026-08-18)
- [x] Created `signaldesk_test` database (isolated from prod `signaldesk`).
- [x] `backend/pytest.ini` — `asyncio_mode=auto`, `pythonpath=.`, `testpaths=tests`.
- [x] `tests/conftest.py` — function-scoped test engine, per-test schema rebuild (`drop_all`/`create_all`), `app.dependency_overrides[get_session]` → test factory, httpx ASGI client, `seeded` fixture.
- [x] `tests/test_stocks_api.py` — 11 tests: health, list (default/sector/pagination/last_price/change), price history (bare symbol/suffix/range), 404 + 422 error envelopes.
- [x] `tests/test_providers.py` — 4 tests: fake provider OHLCV mapping, `MarketDataError` raise, interface compliance, `ingest_universe` failure isolation (D19).
- [x] **Result: 15 passed, 0 failed** in ~6s. No network calls (fake provider used; yfinance only instantiated).
- [x] Confirmed prod `signaldesk` untouched (24,499 bars / 50 stocks unchanged).

### Session 5 — API endpoints + error handling + startup (2026-08-18)
- [x] `app/errors.py` — `NotFoundError`(404), `ValidationError`(422), error-envelope builders, and handlers.
- [x] `app/routers/stocks.py` — `GET /api/v1/stocks` (pagination, sector filter, `last_price`/`change_pct` from latest two bars) + `GET /api/v1/stocks/{symbol}/prices` (range filter, symbol normalization, resample=1d only).
- [x] `app/main.py` — FastAPI app, registered handlers, included router under `/api/v1`, `/health`, scheduler via **lifespan**.
- [x] Verified all endpoints + error envelopes via httpx ASGI (8 checks passed).
- [x] Confirmed Swagger spec (`/openapi.json`) lists all 3 endpoints.
- [x] Confirmed the 5 DoD-required stocks each have 500 bars.

### Session 4 — yfinance provider + Nifty 50 ingestion (2026-08-18)
- [x] `app/providers/base.py` — `MarketDataProvider` ABC with `OHLCV`/`StockProfile` dataclasses (D16 swappable sources).
- [x] `app/providers/yfinance_provider.py` — yfinance implementation, async via `asyncio.to_thread`, raises `MarketDataError`.
- [x] Verified provider returns real OHLCV + profile for `RELIANCE.NS`.
- [x] `app/data/nifty50.py` — 50 Nifty 50 constituents (`.NS` suffix + name + sector). Fixed a duplicate (`HINDALCO` ×2 → `UPL`).
- [x] `app/seed.py` — idempotent seed → `stocks` (50), `universes` (nifty50), `stock_universe` (50 links). Re-run adds 0.
- [x] `app/jobs.py` — `ingest_universe()` (reads universe from DB, batches via `asyncio.gather`, per-symbol isolation, Postgres upsert) + APScheduler `start_scheduler()`.
- [x] Ingested **24,499 daily price bars** across 49 stocks (~500 trading days each, 2y period).
- [x] **Idempotency verified:** re-run → count unchanged (24,499 → 24,499).
- [x] **Failure isolation verified:** fake provider raising on `RELIANCE.NS` → logged, run continued (`errors: 1`).
- [x] Scheduler start/stop verified.

### Session 3 — App scaffold (2026-08-18)
- [x] `app/__init__.py` — marks `app` as an importable package.
- [x] `.env.example` (committed template) + `.env` (real values, git-ignored).
- [x] `app/config.py` — pydantic-settings `Settings`; requires `APP_ENV` + `DATABASE_URL`; optional keys default empty.
- [x] `app/db.py` — async engine, `async_sessionmaker`, `Base`, `get_session` dependency.
- [x] `app/models.py` — `Stock`, `Universe`, `stock_universe` (many-to-many), `DailyPrice` (Numeric(16,4), `UNIQUE(stock_id,date)`).
- [x] Alembic initialized; `env.py` made **async**; initial migration `8bf8964e941a` generated + applied.
- [x] Verified in Postgres: 4 tables present; `uq_daily_prices_stock_date` unique constraint confirmed.
- [x] End-to-end smoke test: insert stock+universe, link them, insert daily price, read back via relationship, FK-safe rollback. **Passed.**
- [x] `.gitignore` + `git init` at `signaldesk/` (no commit). `.env` confirmed git-ignored; `.env.example` tracked.
- [x] Idempotency: re-running `alembic upgrade head` is a no-op.

### Session 2 — Environment setup (2026-08-18)
- [x] Checked system: Python 3.12.10, Node v24.13.1, git 2.53, winget available.
- [x] PostgreSQL **17.11** installed (binaries zip — EDB installer CDN blocked automated download).
- [x] Initialized cluster with `initdb` (superuser `postgres`, password `postgres`, scram-sha-256).
- [x] Started server via `pg_ctl` (currently running, PID 29732).
- [x] Created `signaldesk` database.
- [x] Created project tree at `Desktop/Projects/signaldesk/backend/` with `app/` subpackages.
- [x] Created `.venv` virtualenv (Python 3.12.10).
- [x] Wrote `backend/requirements.txt` and installed all deps.
- [x] Verified all imports: fastapi, uvicorn, sqlalchemy, asyncpg, alembic, pydantic_settings,
      apscheduler, yfinance, pandas, numpy, httpx, pytest.
- [x] **Data source verified:** `yfinance` returns `RELIANCE.NS` prices + sector + P/E.

### Session 1 — Planning (2026-08-17)
- [x] Full product, scope, architecture, and roadmap decisions recorded in `PLANNING.md` (D1–D15).

---

## 3. In Progress / Next Steps

### Phase 5: Grounded LLM explanation (start here)
1. LLM provider abstraction (OpenAI/Claude) — prompt **only with computed facts** (scores, components, valuation, sentiment) so it narrates, never hallucinates.
2. Wire into the `/alpha` (and optionally `/scores`, `/valuation`) responses as an `explanation` field.
3. Mock the LLM in tests; cap/cache calls; log cost.
4. Keep the rule-based explanations as the always-available fallback.
5. API tests (LLM mocked, no network).

### Note on test DB
Tests use dedicated `signaldesk_test`; `conftest.py` handles schema rebuild + dependency override. Never hit the real `signaldesk` DB.

---

## 4. Command Cheatsheet

```powershell
# --- PostgreSQL ---
# Start server (if not running)
& "C:\Users\shyam\PostgreSQL\bin\pg_ctl.exe" -D "C:\Users\shyam\PostgreSQL\data" -l "C:\Users\shyam\PostgreSQL\data\server.log" start
# Status
& "C:\Users\shyam\PostgreSQL\bin\pg_ctl.exe" -D "C:\Users\shyam\PostgreSQL\data" status
# psql
$env:PGPASSWORD="postgres"; & "C:\Users\shyam\PostgreSQL\bin\psql.exe" -h localhost -U postgres signaldesk

# --- Python / venv ---
cd C:\Users\shyam\Desktop\Projects\signaldesk\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # install deps
.\.venv\Scripts\python.exe -m pytest                            # run tests

# --- Alembic (configured for async) ---
cd C:\Users\shyam\Desktop\Projects\signaldesk\backend
.\.venv\Scripts\alembic.exe revision --autogenerate -m "message"   # generate from models
.\.venv\Scripts\alembic.exe upgrade head                            # apply (idempotent)
.\.venv\Scripts\alembic.exe current                                # show applied revision
.\.venv\Scripts\alembic.exe downgrade -1                           # roll back one revision

# --- Run the API server ---
cd C:\Users\shyam\Desktop\Projects\signaldesk\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload      # dev server (Swagger at /docs)

# --- Seed + ingest ---
cd C:\Users\shyam\Desktop\Projects\signaldesk\backend
.\.venv\Scripts\python.exe -m app.seed                              # seed Nifty 50 universe (idempotent)
.\.venv\Scripts\python.exe -c "import asyncio; from app.jobs import ingest_universe; asyncio.run(ingest_universe())"  # run price ingestion
.\.venv\Scripts\python.exe -c "import asyncio; from app.jobs import ingest_financials; asyncio.run(ingest_financials())"  # run financials ingestion
.\.venv\Scripts\python.exe -c "import asyncio; from app.jobs import ingest_news; asyncio.run(ingest_news())"  # run news + sentiment (slow: FinBERT)

# --- Tests ---
cd C:\Users\shyam\Desktop\Projects\signaldesk\backend
.\.venv\Scripts\python.exe -m pytest -v                            # run full suite (test DB, no network)
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term    # coverage report
```

---

## 5. Environment Reference

| Item | Value |
|---|---|
| Project root | `C:\Users\shyam\Desktop\Projects\signaldesk` |
| Backend | `backend/` (venv at `backend/.venv`) |
| Postgres binaries | `C:\Users\shyam\PostgreSQL\bin` |
| Postgres data dir | `C:\Users\shyam\PostgreSQL\data` |
| Postgres superuser | `postgres` / `postgres` (dev only) |
| Database | `signaldesk` |
| DB connection (expected) | `postgresql+asyncpg://postgres:postgres@localhost:5432/signaldesk` |
| Planning doc | `C:\Users\shyam\Desktop\Projects\PLANNING.md` |

---

## 6. Known Gotchas & Decisions Made

- **PostgreSQL is 17.11, not 16** — decided to keep 17 (newer). Documented in PLANNING (D20).
- **EDB automated downloads are geo/network-blocked** (403 via CloudFront) — must use the
  `sbp.enterprisedb.com/getfile.jsp?fileid=...` tokenized binaries links if reinstall needed.
- **pip install timed out once** at 10 min during "Installing collected packages" — the download cache
  was warm, so a re-run finished in seconds. If interrupted, just re-run the same install command.
- **Redis intentionally not installed** — only needed at the P1 caching phase. Defer.
- **Docker not installed** — not needed until Semester 2.
- `pip` writes notices to stderr; PowerShell may show red "error" lines that are not errors.
- **Alembic env.py is async** — never switch it back to the sync default or migrations will fail with asyncpg.
- **Delete rows in FK-safe order** — when deleting a stock that's linked in `stock_universe`, delete the
  association rows *first* (child/parent order), or Postgres raises a `ForeignKeyViolationError`.
- **Cleaning test data:** `TRUNCATE daily_prices, stock_universe, stocks, universes RESTART IDENTITY CASCADE;`
- **Initial migration is `8bf8964e941a`** ("initial schema").
- **Never lazy-load relationships in async code** (`MissingGreenlet`). Use `selectinload()` or query the
  association table directly. Hit in `seed.py` — fixed by querying `stock_universe` directly.
- **`TATAMOTORS.NS` returned no data from yfinance** (transient Yahoo issue) — gracefully skipped by
  ingestion (D19 isolation). Not a code bug; may resolve on a later run.
- **`INSERT ... ON CONFLICT DO UPDATE`** (via `pg_insert`) is how `daily_prices` stays idempotent. If the
  unique constraint name changes, update the `constraint=` argument in `jobs.py`.
- **pytest-asyncio event-loop affinity:** asyncpg connections are bound to the event loop that created
  them; pytest-asyncio gives each test its own loop, so the test engine fixture MUST be **function-scoped**
  (session-scoped async engine → "another operation is in progress" errors). Hit in the first test run.
- **Dependency override is how tests redirect the DB** — `app.dependency_overrides[get_session]`; never
  touch the prod engine. Tests must also monkeypatch `app.jobs.SessionLocal` if they call `ingest_universe`.
- **Test DB `signaldesk_test`** — created via `createdb`; schema rebuilt per-test via
  `Base.metadata.drop_all/create_all` (no Alembic needed in tests).
- **Postgres `Numeric` returns `Decimal`** — comparing ORM values in tests must use `Decimal(...)`, not float
  (`Decimal('0.1500') == 0.15` is `False`). Hit in `test_financials.py`.
- **yfinance `info` omits many metrics per symbol** (e.g. `return_on_equity`, `interest_coverage` often
  missing; `TATAMOTORS.NS` intermittently 404s) — scoring MUST handle missing components via renormalization.
- **New migration `5f7fd30113b1`** ("add financials table"); financials upsert targets `uq_financials_stock_id`.
- **NULL classifier in SQL → no rows** — `column == None` is a SQL NULL comparison (never true). When falling back
  to `sector`, must compare against `stock.sector` (a real value), not `None`. Hit in `repositories/stocks.py`.
- **Industry was NULL in seed** — backfilled 49/50 via `seed.backfill_industry()`. Re-run if the catalog widens.
- **Screener is O(n²) over peers** (fine for 50–500 stocks; revisit if scaling to the full market).
- **FastAPI 0.141 mounts included routers as `_IncludedRouter`** (path shows `None` when iterating
  `app.routes`) — the real paths still work; check `/openapi.json` to confirm route registration.
- **`range` param shadows Python's builtin `range`** in `stocks.py` (intentional for the API contract).
- **`resample` is 1d-only in v1** (D-flag); weekly/monthly aggregation deferred.
- **SQLAlchemy async engines don't support `before_cursor_execute` events** — attach listeners to
  `engine.sync_engine` instead (query-count tests). Hit in `test_hardening.py`.
- **Batch methods live in repositories** (`get_two_latest`, `get_financials_batch`) — the N+1 guards
  depend on them; keep per-stock loops out of routers.
- **Analysis logic lives in `services/analysis.py`** — routers must not re-implement the valuation/
  scoring flow (audit finding). Pure math stays in `valuation.py`/`scores.py`.
- **Request-id contextvar** — the access log formatter in `main.py` references `request_id`/`method`/
  `path`/`status`/`duration_ms`; `current_request_id()` is also available to error envelope builders.
- **Retry wrapper `_with_retry`** — only `MarketDataError` is retried (transient); other exceptions
  propagate immediately.
- **FinBERT is heavy + thread-sensitive** — the model loads lazily behind a `threading.Lock` (concurrent
  first imports of `transformers.pipeline` fail under `asyncio.to_thread`). First live ingest is slow;
  model is cached after. Scoring only NEW articles (already-scored ones are skipped).
- **`published_at` must be timezone-aware** (`DateTime(timezone=True)`) — naive vs aware datetimes crash
  asyncpg. Hit in first news tests.
- **Race-safe upsert by URL** — `ON CONFLICT DO NOTHING` on `uq_news_articles_url`, NOT check-then-insert:
  the same Google News article is fetched for multiple symbols concurrently (hit 6 unique-violation
  errors before the fix).
- **Google News RSS strips the exchange suffix** — query uses bare symbol ("RELIANCE"), because RSS
  feeds don't accept "RELIANCE.NS".
- **News migration is `ed7bb907ca7c`**; test DB drops/recreates schema, so tests need no FinBERT load.
- **Alpha migration is `b0f48fb7c939`**; `alpha_scores` snapshot upsert targets `uq_alpha_scores_symbol_date`.
- **Technical-score formulas are heuristics** (product-defined), not validated predictive models — trend 50 / momentum 30 / reversion 20. Treat as explainable signals, not alpha guarantees.
- **Valuation is deliberately separate** from the Alpha composite (40/30/30) — blending multiples would double-count fundamentals. `value_signal` surfaces it prominently instead.
- **`components` vs `weights` in the /alpha response are separate dicts** — pydantic rejects a nested dict in a `dict[str,float]` (hit in the first alpha test run).
- **`get_close_series` returns oldest-first** (reverses the DESC query) — feed indicators chronological closes.

---

*Append progress after every phase. When a phase hits its Definition of Done, mark it complete here.*