# SignalDesk - Semester 2 Progress Tracker

> **Purpose:** The operational companion to `SEMESTER2_PLAN.md`. Read this file FIRST to resume work, then the plan for the what/why.
> **Rules:** Current state, then active milestone, then next task. Checklists per milestone. Verification results. Risks and pending human decisions stay visible until closed.
> **Last updated:** 2026-09-10 (M2 started in parallel with M1-T7: M2-T1 storage guardrails + M2-T8 enriched peers COMPLETE; ingestion path untouched, T7 baseline uncontaminated; see Work Log 2026-09-10).
> **Companion:** `SEMESTER2_PLAN.md` (sections cited as Plan 1-30). Semester 1 record: `PLANNING.md` / `PROGRESS.md`, frozen, unmodified.

---

## 1. Current State

| Item | State |
|---|---|
| Repo / branch / HEAD | `C:\Users\shyam\Desktop\Projects\signaldesk`, `main`, `4121c19` (M1 complete, clean tree at M2 start) |
| Semester 1 | COMPLETE (Phases 1-8). Backend 348/348 (zero-network), frontend 72/72, tsc clean, build OK |
| Semester 2 plan | COMPLETE (`SEMESTER2_PLAN.md`, 30 sections + appendices) |
| Semester 2 implementation | IN PROGRESS (M1 complete incl. ETF/fund/Z-score slices + production; **M2-T1, M2-T8 done**; T7 observing) |
| Active milestone | **M1-T7 (observation gate) running in parallel with M2** |
| Next concrete task | M1-T7: nightly cron green one full week (first firing 2026-09-10 ~13:30 UTC). M2 continues with T2 (statements schema + yfinance primary) behind the `enable_m2_passes` flag |

## 2. Milestone Board

| Milestone | Status | Depends on | Definition of done |
|---|---|---|---|
| M1 - Scale-Up and Ship It | COMPLETE except T7 observation | - | Plan 24/M1 |
| M2 - Statements and Depth | IN PROGRESS (T1, T8 done) | M1 | Plan 24/M2 |
| M3 - Accounts and Workspace | NOT STARTED | M1 (parallel with M2) | Plan 24/M3 |
| M4 - Fund Data Backbone | NOT STARTED | M1 | Plan 24/M4 |
| M5 - Fund Research Experience | NOT STARTED | M4 | Plan 24/M5 |
| M6 - ETF Layer | NOT STARTED | M2 + M5 | Plan 24/M6 |
| M7 - Scenario and Forecast Lab | NOT STARTED | M4/M5 | Plan 24/M7 |
| M8 - Research Synthesis and Close | NOT STARTED | All | Plan 27 |

## 3. Active Milestone Checklist (M1)

- [x] M1-T1: `.github/workflows/ci.yml` runs backend pytest (348 baseline), frontend vitest/tsc/build on every push
- [x] M1-T2: top-1000 ranking job implements eligibility rules E1-E12 (Plan 7) with per-symbol audit reasons
- [x] M1-T3: measured top-1000 ingestion (local, same chunked architecture; 20-symbol timed slice + full-universe score pass; benchmark + storage measured; see Work Log 2026-09-08)
- [x] M1-T4: storage measured (104 MB live DB; projected ~230-330 MB at full top-1000 scale, under the 0.5 GB cap; see Work Log 2026-09-08)
- [x] M1-T5: production deploy per Plan 21 (Pages + Render + Neon + cron); `/health` and `/status/full` smoke green (2026-09-09; see Work Log)
- [x] M1-T6: benchmark index ingestion (`^NSEI`, `^NSEBANK`, `^CNXIT`, `^CRSLDX`) live (own tables, measured 1.8-3.8s / 0.6 MB)
- [ ] M1-T7: nightly cron green one full week; zero-cost itemized and verified (first cron firing 2026-09-10). M2 work runs in parallel WITHOUT touching the ingestion path (see Work Log 2026-09-10)
- [ ] News breadth gate: news stays core-500 until the M1-T3 benchmark proves headroom (tiered decision)

### M2 checklist (started 2026-09-10)

- [x] M2-T1: storage guardrails - canary test (worst-case 90-day projection vs the 512 MB cap), retention pass (alpha depth 1y outside top 250) shipped INERT behind the 450 MB gate, CLI `prune-alpha`, weekly db-probe schedule (read-only, separate workflow)
- [x] M2-T8: enriched peers - `get_peers` capped at 15 (mcap_rank ASC NULLS LAST, symbol ASC), is_etf/inactive excluded, PeerSummary extended (P/B, P/S, EV/EBITDA, mcap, rank, ROA, op margin, revenue CAGR 3y, 1y return), zero-provider read paths regression-proven
- [ ] M2-T2: statements schema + yfinance primary (income columns, BS Plan 5.4 fields, cash_flow_periods) - ingestion lands behind `enable_m2_passes`
- [ ] M2-T3: Upstox secondary statement adapters
- [ ] M2-T4: statement read APIs + top-1000 backfill
- [ ] M2-T5: dividends; M2-T6: earnings/events
- [ ] M2-T7: risk engine
- [ ] M2-T9: sector indexes + sector-relative medians
- [ ] M2-T10: Alpha v2 (Quality 40 / Growth 20 / Solvency 25 / Distress 15, owner-confirmed)
- [ ] M2-T11: screener precompute
- [ ] M2-T12: frontend sections; M2-T13: pipeline integration + DoD

## 4. Upcoming Milestone Checklists (brief; detail in Plan 24)

- M2: statements/dividends/earnings/risk endpoints + pages; enriched peers; sector indexes; Alpha v2 specified, implemented, snapshotted; screener precompute live.
- M3: auth routes + sessions; workspace schema/endpoints/pages; scoping + adversarial auth tests green; auth rate bucket enforced.
- M4: AMFI NAV + catalog ingestion; curated universe (~800) with documented cut rule; NAV backfill; nightly metric precompute.
- M5: fund detail/screener/compare; holdings Excel-first ingestion; overlap engine with exact definitions; three-pair hand-reproducible DoD.
- M6: ETF flags + metadata + screener + detail; tracking difference where free index data exists.
- M7: bootstrap/block-bootstrap + goal simulator + walk-forward backtests; leakage + calibration suites; five-state labeling; Alpha hit-rate backtest.
- M8: stock comparator; PDF reports; LLM-on-funds on-demand; methodology pages; final DoD audit.

## 5. Verification and Test Results

- Semester 1 freeze (2026-09-08 @ `968a44d`): backend pytest **348/348**, frontend vitest **72/72**, `tsc -b` clean, `vite build` OK. Coverage about 78 percent.
- M1-T1 CI (2026-09-08 @ `9dfd182`): two consecutive green runs (push `34211797445` + `workflow_dispatch` re-run `34212950591`). Backend job: `alembic upgrade head` clean through all 7 migrations to `c1d2e3f4a5b6`, pytest **348 passed** (33.70s / 33.29s). Frontend job: vitest **72 passed** (9 files), `tsc -b` clean, `vite build` OK (4.55s / 4.53s). No env diffs found; zero-network suite ran unchanged against the `postgres:17` service.
- M1-T2 ranking (2026-09-08 @ `4f08d91`, CI run `34222965567` green): backend **384 passed** (348 existing + 36 new ranking tests, zero regressions), frontend **72/72** + tsc clean + build OK. Migration `c1d2e3f4a5b6` -> `d4e5f6a7b8c9` (head) applied cleanly locally AND in CI on fresh `postgres:17`. Real manual runs (`python -m app.jobs rank`, dev DB): two consecutive runs each ~9.5 min, **identical results** (ranked_in 1000, ranked_out 1416, excluded 7289, errors 0; 9705 audit rows; Upstox secondary 429s degraded to yfinance-primary as designed). Same-day re-run idempotent (one cycle row, audit rebuilt). "Why isn't X in the top 1000" verified live: NIFTYBEES -> `etf`, EMBASSY -> `not_ordinary_equity` (series RR), TATAMOTORS -> `renamed` (shadow of TMPV), ZUARI -> `ranked_out` rank 1471, RELIANCE -> rank 1 (mcap Rs 1.75e13).

## 6. Known Risks and Blockers

- **Neon 0.5 GB storage hard cap** (exceeding suspends compute): mitigated by Plan 22 budget + retention + canary; first cut defined (alpha backfill depth outside top 250).
- **Actions 6-hour job cap** at full 1000-symbol breadth: M1-T3 benchmark is the gate; ingestion is chunked with continuation.
- **Upstox manual token expires**: human renewal required; yfinance-only fallback designed in; owner TBD (Plan 29).
- **Yahoo throttling** at 1000 symbols: chunked, rate-limit-aware ingestion; retry/backoff already in `jobs.py`.
- **OpenRouter free = 50 requests/day** (under 10 USD all-time credits): LLM on-demand only, ~45/day ceiling, rule-based default (Plan 18).
- **Render free cold starts** (~30-60s) and 512 MB RAM: FinBERT stays out of the API image; static shell + skeletons absorb cold starts.
- **Free OpenRouter model IDs rotate**: availability probe + fallback already exist (`/ask` pattern).
- **Yahoo market cap gaps** for some small caps: ranking rule E7 excludes with audit reason, never estimates.
- **MF holdings formats heterogeneous**: Excel-first, monthly cadence accepted; the riskiest data dependency (Plan 8.4, 13).

## 7. Data-Source, Runtime and Storage Findings (verified 2026-09-08)

- Neon Free: 0 USD permanent, no card; 0.5 GB/project hard; 100 CU-hours/month; scale-to-zero 5 min; 5 GB egress. (Official pricing page.)
- Render Hobby: free web 512 MB/0.1 CPU with spindown; **free Postgres 30-day limit: rejected as DB**. 500 build-min/month. (Official pricing page.)
- Cloudflare Pages Free: 500 builds/month, 20k files, 25 MiB/file, effectively unlimited static bandwidth. (Official limits page.)
- OpenRouter free variants: 20 req/min; 50 req/day (<10 USD credits); 1000/day after one-time 10 USD purchase (optional, outside strict zero-cost plan). (Official limits page.)
- GitHub Actions: free unlimited standard minutes on public repos; 6h/job cap.
- Supabase Free kept as DB fallback (500 MB, 7-day idle pause).
- Upstox supplies no market cap (Semester 1 data-quality finding): ranking depends on Yahoo mcap alone (Plan 7, rule E6 limitation).
- **NSE `EQUITY_L.csv` archive URL is dead** (HTTP 404, verified 2026-09-08 via httpx and curl with and without site cookies/Referer). Ranking reads the Upstox NSE instruments master instead (same public no-auth endpoint `upstox_provider` already uses); its `instrument_type` carries the NSE series codes verbatim (EQ/BE/BZ/RR/IV/SG/N*), so E1-E5 semantics are unchanged. Recorded as the approved M1-T2 deviation ("or equivalent" clause).
- **Provisional curated ETF list is incomplete** (15 majors only): remaining NSE ETFs sit inside EQ series and rank in until M6 ships `etf_metadata` (M1-T2 decision 1).
- **Stale-stock recovery path is narrow**: E9/E10-deactivated stocks leave the ranked universe, so nightly ingestion (universe-driven) never refreshes them; reactivation requires bars to reappear via `repair_catalog_gaps` or a manual pass. Revisit if a real suspension case appears.
- No legitimate free NSE real-time feed; no free transcript source; exchange shareholding scraping is terms-gray (not committed without review).
- Storage estimate at full scale roughly 320-450 MB vs 0.5 GB cap (Plan 22). Runtime estimate roughly 2.5-4.5 h vs 6h cap (Plan 22). Both UNCONFIRMED until M1-T3/T4 measure them.

## 8. Deployment Status

DEPLOYED 2026-09-09 (Plan 21 topology, all free tiers):
- **API:** Render free web service, https://signaldesk-31gt.onrender.com (APP_ENV=production, docs gated off, ops auth fail-closed).
- **Frontend:** Cloudflare Pages (static build, VITE_API_BASE pointed at the Render API).
- **Database:** Neon free Postgres (`neondb`, owner `neondb_owner`), connected via the `DATABASE_URL` Actions secret and Render env var; schema at alembic head.
- **Cron/CI:** GitHub Actions - `ingest.yml` nightly 13:30 UTC (19:00 IST, after close), `rank.yml` monthly 04:00 UTC on the 1st (+ workflow_dispatch), `migrate.yml`, `backup.yml`, `ci.yml` on push; `restore.yml` (Plan 28 restore) and `db-probe.yml` (storage monitoring) are manual runbook tools.
- Production data: full top-1000 with 1.23M price rows, 461k alpha rows, 22 funds, 16 ETFs, 10 benchmarks (2026-09-09); DB 383 MB of the 512 MB Neon cap.
Runbook: Plan 28. Remaining human decisions in section 9 (cost snapshot confirmation pending owner check of the four billing dashboards).

## 9. Human Decisions Still Pending

- Custom domain (~10 USD/year, optional, outside zero-cost plan).
- One-time 10 USD OpenRouter top-up (optional, outside the plan).
- Email verification / password-reset flows now or later (v1: neither; admin-assisted recovery).
- Fund-universe curation cut rule (proposed: top by AUM per category to ~800).
- MF holdings automation level (manual monthly download vs semi-automated fetch + review).
- Upstox token renewal owner and cadence (or drop to yfinance-only).
- News breadth step-up 500 to 1000 after M1 benchmark.
- Legal-review pass on disclaimers, simulation wording, ownership-data collection.

## 10. Operational Gotchas (durable, carried from Semester 1)

- **PostgreSQL on Windows `0xC0000142`:** if backends die on connect while port 5432 listens, suspect antivirus/VSS interference with the log file; stable launch is `postgres.exe -D <data>` directly (not `pg_ctl -l` with a shared server.log). Full incident in git history of `PROGRESS.md`.
- **"Internal Server Error" on the whole site with frontend dev server up = dead backend, not an app bug:** Vite's `/api` proxy answers literal HTTP 500 (upstream unreachable) when nothing listens on `127.0.0.1:8000`. Signature: 5173 listening, 8000 not, 500 on every `/api/*` request, empty short body. Fix: start the backend (`uvicorn app.main:app --port 8000` from `backend/`) before judging any app regression. Verified 2026-09-08 (see Work Log).
- **Stale uvicorn serves old code** (new routes 404 without envelope): restart backend after pulling changes.
- **Do not rewrite .md files with PowerShell text processing** (PS 5.1 mangles UTF-8): use the file editor; restore via `git checkout -- <file>`.
- Charts must gate on real container width (ResizeObserver): collapsible sections keep content mounted at width 0.
- Postgres `Numeric` returns `Decimal`: compare with `Decimal(...)` in tests, not float.
- `published_at` must be timezone-aware; race-safe upserts via `ON CONFLICT DO NOTHING` on URL/unique anchors.
- Test engine must be function-scoped (pytest-asyncio loop affinity); redirect DB via `app.dependency_overrides[get_session]`; never touch prod engine.
- Alembic env is async: never switch it back to sync. Migration head at S1 freeze: `c1d3...` chain ending with job-runs migration (verify with `alembic current` before new work).
- FinBERT loads lazily behind a thread lock and is heavy (~420 MB): ingestion-runtime only, never in the API image.
- `OPENROUTER_API_KEY` is an alias for `LLM_API_KEY`; empty model disables LLM by design.
- Scoring must renormalize over missing fields; nulls stay null; no emulator math in the frontend.
- Copy discipline is a hard rule for anything user-visible (no em dashes, no AI-tell wording, "-" null placeholder, normalized disclaimer).
- **`pool_pre_ping=True` on the app engine (app/db.py) is REQUIRED for Neon, not cosmetic:** ingestion passes open short-lived sessions then spend 10-30 min on provider fetches; Neon closes the idle pooled connection and the next checkout dies with `asyncpg.InterfaceError: connection is closed`. Removing it as a "simplification" re-breaks rank/ingest after long fetch phases (rank.yml 34347351526 incident, 2026-09-09).
- **Workflow green is not pass health: judge ingestion by `job_runs` status.** `partial` exits 0 by design (D19 per-symbol isolation); the CLI exits non-zero only on `failed` (commit 6aa8070). Before that commit even a failed pass exited 0 and GitHub painted the run green (rank run 34345215106 was a silent failure) - rank.yml now also prints the last `job_runs` rows so this is visible in the run log.
- **Neon connection string forms:** the console copy-paste is libpq (`?sslmode=require&channel_binding=require`); asyncpg rejects those parameter NAMES. `app.db.asyncpg_ready_url` normalizes both forms (and bare `postgresql://`) everywhere; the pooler and direct endpoints accept the same credentials (verified by the rank.yml connectivity matrix), so host-form confusion is not a credential problem.

## 11. Work Log

- 2026-09-08: Semester 2 master plan written (`SEMESTER2_PLAN.md`, 30 sections); this tracker created. No application code changed. Semester 1 `PLANNING.md`/`PROGRESS.md` left untouched. No commit, no push.
- 2026-09-08: **M1-T1 done** @ `9dfd182` - added `.github/workflows/ci.yml` (two parallel jobs, push/PR to `main` + `workflow_dispatch`; backend: Python 3.12, `postgres:17` service on localhost:5432 with `signaldesk_test` DB matching conftest, pip cache, `alembic upgrade head` then pytest; frontend: Node 22, npm cache, `npm ci`, `npm test`, `npm run typecheck`, `npm run build`). Run 1 (push, `34211797445`) and run 2 (`workflow_dispatch` re-run, `34212950591`) both green: backend 348/348 with migrations to head `c1d2e3f4a5b6`; frontend 72/72, tsc clean, build OK. No flakiness observed; no env diffs found; no application/test code touched. Known cosmetic issue only: GitHub annotations warn that `actions/*` v4/v5 Node 20 targets are force-run on Node 24 (deprecation notice from GitHub, not a failure; revisit when actions v5/v6 replacements stabilize).
- 2026-09-08: **M1-T2 done** @ `4f08d91` (CI `34222965567` green) - top-1000 universe ranking per Plan 7. New: `services/ranking.py` (pure E1-E12 logic), `repositories/ranking.py`, `providers/nse_master.py`, `data/ranking_exclusions.py` (curated ETF/REIT lists), migration `d4e5f6a7b8c9` (2 tables: `ranking_cycles`, `ranking_audit` + 8 additive `stocks` columns: isin, active, delisted_reason, delisted_at, mcap_rank, mcap_asof, restrict_flag, is_etf; no `active` collision existed). Job pass `rank_universe` via `python -m app.jobs rank` + `rank.yml` (`workflow_dispatch` ONLY, no cron - monthly schedule deferred to M1-T5). Nightly ingestion still reads `nifty250` (cutover is M1-T3). **Approved decisions 1-8 implemented as specified.**
  **Deviation 1 (pre-authorized "or equivalent" clause):** NSE `EQUITY_L.csv` returns HTTP 404 (dead URL, verified httpx + curl); the ranking reads the Upstox NSE instruments master instead - same endpoint `upstox_provider` already uses, no key, and its `instrument_type` field carries the NSE series codes verbatim, so E1-E5 semantics are unchanged (E4 actually improved: REIT/InvIT/SGB excluded structurally, curated list remains for ETFs).
  **Deviation 2 (found by the real run, fixed in this commit):** first real run exposed a rename-shadow gap - the catalog held both TATAMOTORS.NS (old seed) and TMPV.NS (current symbol); TMPV ranked while TATAMOTORS was wrongly deactivated as `absent_from_master`. Fixed: an absent catalog row whose alias target is ranked under its newer symbol now audits `renamed` (same live entity, never deactivated); second real run healed the row (active=True) and confirmed idempotency (1 cycle row, 9705 audit rows, identical counts both runs).
  Verification: backend **384 passed** (36 new tests), frontend **72/72**, tsc clean, build OK; migration applied cleanly locally and in CI; real run: 1000 ranked in / 1416 ranked out / 7289 excluded / 0 errors, `top1000` membership exactly 1000, nifty250 universe untouched; "why isn't X" query verified on real audit data.
- 2026-09-08: **Website 500 diagnosed and resolved (no application change)** - gate clearance before M1-T3/T4/T6. Diagnosis path per protocol: (1) port scan: frontend dev server (5173) listening, backend (8000) NOT; (2) reproduced the exact reported error at the frontend origin - `GET localhost:5173/api/v1/*` -> HTTP 500 "Internal Server Error" with an empty body; (3) root cause: **Vite's /api proxy returns a literal 500 when its upstream (127.0.0.1:8000) has no listener** - the backend process simply was not running (environment/stale-process class, matching the §10 gotcha family); (4) started uvicorn from current M1-T2 code; (5) verified: the user's own browser flows in the access log all 200 (`/stocks`, `/stocks/{s}/technicals|scores|news|sentiment|valuation|alpha|alpha/explanation` incl. a real OpenRouter call falling back to rule-based per design); direct API sweep all 200 (`/health`, `/status`, `/stocks?limit=200` over the ~2200-row post-ranking catalog, `/stocks/TMPV` + technicals/performance/peers/alpha/history for a ranking-created symbol, `/screener`, `/financials/history`; `/stocks/NEWIPO` correctly 404s with the error envelope - unknown-symbol semantics, not a crash); zero `status=500` lines in the backend log; the exact original failing request through the proxy now returns **HTTP 200, 28,846 bytes**. **Verdict: environment-only, NOT M1-T2, no code changed** - M1-T2 data/schema state explicitly cleared (ranking-created rows serve 200 across detail/technical/performance/peers/alpha surfaces). Backend full suite re-run post-resolution: **384 passed**. Frontend code untouched (last CI run `34223448384` green). Gotcha added to §10 for future recognition of the Vite-proxy-500 signature. **Gate for T3/T4/T6: CLEARED.**

---

- 2026-09-09: **M1-T5 done - production deployment live** (Plan 21; Render API https://signaldesk-31gt.onrender.com + Cloudflare Pages frontend + Neon free Postgres + GitHub Actions crons). What actually happened, in sequence, with the failures left in:
  1. **Infra stood up earlier in the round:** Render service live, Pages deployed, Actions secrets (`DATABASE_URL`, `OPS_API_KEY`) configured. The in-process APScheduler duplicate-nightly-job bug in production was found and fixed (scheduler now starts with NO jobs in production; Actions cron is the only scheduler, per D79).
  2. **The DATABASE_URL credential rounds (several failed dispatches 10:06-10:39 UTC):** rejected libpq kwargs (asyncpg refuses `sslmode`/`channel_binding` as parameter names; fixed permanently by `app.db.asyncpg_ready_url` normalization + `test_db_url.py`), wrong username (`postgres` vs `neondb_owner`), pooler-vs-direct host confusion, and repeated dashboard copy-paste corruption. Diagnostics added to rank.yml along the way (safe credential fingerprint, direct-vs-pooler connectivity matrix, Render `/status/full` probe, URL shape diagnostics). Resolution: correct connection string stored once in the Actions secret; both Neon host forms verified by the connectivity matrix step.
  3. **Silent-failure finding (important):** rank run 34345215106 (11:22 UTC) showed workflow SUCCESS but its log carries `job_fail job=rank_universe status=failed duration_ms=698372` - at that commit the CLI exited 0 even on a failed pass, so GitHub painted it green. Fix (commit 6aa8070): CLI exits non-zero on `status=failed` (`partial` stays exit 0 by D19 design), rank.yml prints the last `job_runs` rows. Verified in code (`app/jobs.py` exit gate) and by the next run (34347351526) correctly showing FAILURE. The silent-green class of failure is permanently closed.
  4. **Stale-connection failure:** run 34347351526 (14m40s) failed with `asyncpg.InterfaceError: connection is closed` on the first write-phase query (`SELECT ranking_cycles`): the module-global engine's pool handed the job a connection that idled ~12 min during the throttled Yahoo mcap phase and Neon closed it. Earlier DB queries in the same run succeeded, so credentials were already healthy. Fix: `pool_pre_ping=True` on the app engine (commit 7fd1d14, regression comment in db.py). Backend suite 445/445.
  5. **Production data population via restore (the local-snapshot path):** production Neon was essentially empty (catalog + one degraded ranking cycle; RELIANCE `/prices` returned 0 rows). To avoid re-typing or exposing the secret: `pg_dump -Fc` of the dev DB (39.5 MB, regex-scanned credential-free), uploaded as a THROWAWAY release asset, one-off `.github/workflows/restore.yml` restored it server-side using the `DATABASE_URL` secret (`--clean --if-exists --no-owner`, schema-qualified verification; note psql needed schema-qualified names + explicit pg client 17 install). Verified restored state: 1,230,732 daily_prices, 453,696 alpha_scores, 9,705 ranking_audit, 2,923 stocks, top1000 exactly 1000 members (healthy 2026-09-08 cycle). Asset deleted after use; `restore.yml` kept as a Plan 28 runbook tool.
  6. **Yahoo 429 storm (the next real blocker, distinct from credentials):** first completed production rank (34350500127, 16m13s, green) still DEGRADED the data: `ranked_in 728, errors 2051` - 2,051 of ~2,779 fresh mcap fetches 429'd through the old 0.5s/1.0s retries and E7 honestly excluded them (`no_mcap`); live universe total dropped to 728 and RELIANCE's mcap went blank until the next cycle. Fix: paced backoff 5s/15s/30s + 25% jitter in `_fetch_one_mcap` and a 2.0s inter-batch sleep (commit 8d85f80). Re-dispatch 34361637724: **`ranked_in 1000, excluded 8705, errors 2` in 26m53s** (63 min headroom vs the 90-min job timeout). Live verification: universe total 1000, RELIANCE mcap Rs 17.52L Cr, TMPV rename-shadow resolves.
  7. **Full nightly ingest dispatched** (34364916265): success in 2h27m; per-pass: prices 1000/1000 (463,464 bars, 0 errors), financials 999/1000 (DCBBANK yfinance JSON parse), financial_periods 1000/1000, balance_sheets 1000/1000, profiles 999/1000, benchmarks 10/10, etfs 16/16, funds 21/21, repair_catalog_gaps 17, backfill_alpha_history 452,429 recomputed 0 errors, record_live_alpha_snapshots 1000, news 995/1000. `nightly_ingestion` job_runs status = `partial` (3 isolated symbol failures, D19 design; healed by the next nightly). 330-min timeout ample vs 2h27m.
  8. **Smoke checklist green (real outputs):** `/health` ok; `/status` ok; `/status/full` verified green via the rank.yml probe step (OPS key); `/stocks` total 1000; RELIANCE detail (mcap Rs 17.52L Cr), technicals (trend 44.1), alpha composite 53.0, valuation P/E with peer median, news latest 2026-09-08, sentiment -0.046 neutral (57 articles), performance windows + 52w range; screener total 1000; funds 22 with full NAV history (Axis Large Cap NAV 69.25, 6m +2.29%, history 2023-08-31 to 2026-09-08); ETFs 16; benchmarks 10 (NIFTY 50 close 23,431.5 as-of 2026-09-09 with 90d sparkline); market news fresh to 16:46Z today.
  9. **Production storage measured** (`db-probe.yml`, kept as a monitoring tool): **383 MB of the 512 MB Neon cap (75%)**; largest: daily_prices 199 MB (1.23M rows), alpha_scores 126 MB (461k rows), news_articles 30 MB. Growth ~0.6-1 MB/day; headroom holds well past 90 days; first cut unchanged (alpha depth outside top 250, Plan 22).
  10. **Day-0 cost snapshot:** PENDING OWNER CONFIRMATION - the four billing dashboards (Neon, Render, Cloudflare, GitHub) must be visually checked for "no payment method on file" by the owner; all four services were verified free-tier by Plan 21 Appendix A and no card was entered during setup, but the dashboard check is a human step this session cannot perform.
  Suites this round: backend 445/445 (then 446/446 with the pacing test), frontend 73/73 unchanged (no frontend changes). Commits: 7fd1d14 (pool_pre_ping), b1f603d/85b7dfa (restore.yml), 8d85f80 (paced mcap backoff), 7773865/56911c6/2b42521/3d19d23 (db-probe.yml).

---

- 2026-09-10: **M2-T1 + M2-T8 done - storage guardrails + enriched peers** (M2 build starts in parallel with M1-T7 per the M2 plan section 17 interaction rules).
  1. **T7 protection confirmed first:** the nightly ingestion path is UNTOUCHED by this round - `git diff backend/app/jobs.py` shows only additive changes (imports, one new gated function, one CLI branch); the `_ingest_passes` tuple, pass ordering, and every existing pass's fetch/parse logic are byte-identical. `ingest.yml`/`rank.yml` untouched. The T7 cron baseline (first fire 2026-09-10 ~13:30 UTC) is uncontaminated.
  2. **M2-T1 canary** (`app/services/storage.py` + `tests/test_storage_canary.py`): pure projection/gate math pinning the measured production facts (Neon cap 512,000,000 bytes; baseline 383 MB @ 2026-09-09 db-probe; growth band 0.6-1.0 MB/day). The CI canary asserts the worst-case 90-day projection (383 + 1.0x90 = 473 MB) stays under the cap - it goes red when a baseline refresh crosses the cap, making the retention cut due. Gate semantics: fires at >= 450 MB, never below.
  3. **M2-T1 retention pass** (`jobs.prune_alpha_history_outside_top250` + CLI `python -m app.jobs prune-alpha`): alpha backfill depth cut to 1y outside the top-250 keep-set (mcap_rank), per Plan 22. Shipped INERT by owner decision: it measures `pg_database_size` (read-only) and deletes NOTHING below the 450 MB gate (test proves fired=False + 0 rows at real sizes); batched short-transaction deletes; idempotent (re-run deletes 0); never scheduled; recorded in `job_runs` when invoked. Settings: `storage_cut_threshold_mb=450`, `storage_cut_keep_top=250`, `storage_cut_depth_days=366`.
  4. **enable_m2_passes flag (T7-week protection, confirmed decision):** added `settings.enable_m2_passes` (default **False**; no pre-existing flag under another name - grep-verified). Nothing scheduled reads it yet; M2-T2+ wire new ingestion passes through it and the owner flips it after T7 clears. Default pinned by test.
  5. **Weekly db-probe schedule:** `db-probe.yml` gains a Monday 06:00 UTC cron (+ concurrency group, workflow_dispatch kept). SAFE for T7 by construction: the workflow contains only read-only psql metadata queries, shares nothing with ingest.yml (different workflow, different concurrency group), and its slot avoids both the nightly (13:30 UTC) and monthly rank (04:00 UTC on the 1st). Fresh numbers feed the canary baseline + gate decision.
  6. **M2-T8 enriched peers** (owner decision: cap 15): `get_peers` now orders `mcap_rank ASC NULLS LAST, symbol ASC` and caps at `PEER_CAP=15`, excludes `is_etf` and `active=False` rows (ranked_out rows stay active and eligible; D18 universe-independence preserved). Industry-first / sector-fallback / NULL-cohort-returns-empty behavior unchanged with its regression tests.
  7. **PeerSummary extended** (Plan 5.14): `price_to_book, price_to_sales, ev_ebitda, market_cap, mcap_rank, return_on_assets, operating_margin, revenue_cagr_3y, return_1y_pct`. New batched read helpers (no N+1): `prices.get_return_1y` (each stock anchored on its own latest bar; null when history < window, never partial-window annualized) and `financial_periods.get_annual_revenue` (only periods carrying revenue). `revenue_cagr_3y` = CAGR over exactly three fiscal-year slots via the existing FY bucketing; null unless both endpoints exist and the base is positive. Frontend untouched (additive response fields; UI lands in M2-T12).
  8. **Valuation peer-set change (deliberate, documented):** the cap changes medians only for industries with >15 same-industry stocks; existing valuation/peers/analysis tests pass unchanged (all peer assertions were membership- or single-peer-based). New tests pin cap/order/tiebreak/ETF-inactive exclusion, honest CAGR/return nulls, and the no-provider read paths.
  9. **Fan-out regression extended:** the M1-T3 no-network test (`test_alpha_unclassified_stock_answers_fast_no_network`) now also covers `/peers` + `/valuation` on the unclassified stock, and a new test proves the enriched `/peers` over a REAL cohort constructs no provider at all (UpstoxProvider monkeypatched to explode; both surface 200 from stored data).
  10. Suites: backend **461/461** (446 baseline + 15 new: 9 storage, 3 peers-repo, 3 peers-endpoint), frontend **72/72** + `tsc -b` clean (no frontend changes; the tracker's earlier "73/73" counts predate this round - CI baseline is 72 in 9 files). No migrations (T1/T8 need none: cap/order use existing `mcap_rank`/`is_etf`/`active` columns; all new read helpers read existing tables). Storage impact of this round: ~0 (no new tables; alpha JSONB untouched).

---

*Resume here. M1-T7 continues observing the nightly cron through ~2026-09-17 (zero-cost itemized verification still pending owner confirmation). M2 resumes at M2-T2 (statements schema + yfinance primary), with every new ingestion pass behind `enable_m2_passes` (default OFF) until T7 clears. Plan reference: `SEMESTER2_PLAN.md` section 28; M2 build order in the 2026-09-09 M2 plan.*

## 12. M1-T3/T4/T6 Measurement Report (2026-09-08, local production-scale run)

Verdict: **PASS WITH CHANGES** (viable within budgets; T5 deploy gated on the two bounded changes below, both already implemented in this commit).

### 12.1 Website 500: root cause, fix, verification

Failing request: `GET /api/v1/stocks/{symbol}/alpha` for ranking-created top-1000 stocks with sector=NULL and industry=NULL (e.g. UTIAMC.NS; 2,656 of 2,907 catalog rows). Signature: `/stocks`, `/stocks/{s}`, `/stocks/{s}/scores`, `/stocks/{s}/technicals`, `/stocks/{s}/news` all 200; `/alpha` hung then died (HTTP 000 at 25s); `/health` stayed 200 (worker wedged, process alive). Reproduced directly via curl against 127.0.0.1:8000 and through the Vite proxy (localhost:5173/api).
Root cause chain: (a) M1-T2 created ~2,400 catalog rows with sector/industry NULL; (b) `get_peers` fell back to sector, and `column == None` compiles to `IS NULL`, matching all 2,656 unclassified rows as one meaningless cohort (verified: 2,655 peers for UTIAMC.NS); (c) `compute_stock_valuation` loaded all peers and fired one Upstox network call per peer missing a multiple (30s timeout each); (d) `compute_alpha` calls valuation with no timeout on the request path, so one /alpha fanned out to thousands of sequential provider calls and never returned.
Fix (no validation weakened, no exception suppressed, no fake data): `get_peers` returns [] when industry AND sector are both NULL; request paths serve stored snapshots only (`allow_live_fallback=False` default; Upstox fallback needs explicit opt-in for ingestion enrichment). Unclassified stocks now answer NO_PEERS (valuation 409/422 envelope) and /alpha 200 with `insufficient_data:true` + null value_signal in ~15ms.
Verification: backend 410/410 (incl. 3 new regression tests), frontend 73/73, tsc clean, build OK; manual sweep green (direct + proxy): RELIANCE /alpha 200 (composite 54), TATAMOTORS /alpha 200 (composite 43), UTIAMC /alpha 200 insufficient, TEGA /alpha 200 insufficient, HDFCBANK /altman 200 non_applicable_financial, RELIANCE /altman 200 missing_balance_sheet; zero `status=500` behavior (no 500s observed; hangs eliminated).

### 12.2 Runtime (measured, real merged yfinance+Upstox provider, BATCH_SIZE=5)

UNIVERSE_NAME cutover nifty250 -> top1000 included (`app/jobs.py`, `app/seed.py`; ingestion tests follow the constant). Benchmark job: 4/4 indexes, 1,979 bars, 0 errors, 1.8-3.8s over two runs (2026-09-08). 20-symbol top-1000 slice, production architecture: prices 20/20, 9,792 bars, 23.3s (1.16s/symbol); financials 20/20, 24.4s (1.22s/symbol); periods 20/20, 222 periods, 19.8s (0.99s/symbol); profiles 20/20, 7.5s (0.37s/symbol). Score calc over the FULL top-1000 (record_live_alpha_snapshots, batch 20): 264 stored, 0 errors, 38.6s (0.039s/symbol).
Projection (linear over per-symbol rates; prices+financials+periods+profiles ~= 3.74s/symbol): full 1000-symbol ingestion ~= 62 min; + benchmarks ~4s + alpha snapshots ~1 min + news/FinBERT (core-500, Plan 22: 20-35 min) => nightly ~= 1.5-2 h vs the 6 h Actions cap. Safety margin ~= 3-4x. No benchmark-only ingestion path was created.

### 12.3 Storage (measured live DB, Neon 0.5 GB = 512,000,000 bytes hard limit)

Before slice runs: 96 MB. After benchmarks + slices + full-universe alpha pass: 104 MB (108,582,579 bytes). Largest tables: alpha_scores 45,696 kB (119,992 rows, ~390 B/row), daily_prices 33,904 kB (189,882 rows, ~183 B/row), news_articles 8,208 kB, ranking_audit 4,344 kB, financial_periods 992 kB (2,871 rows), company_profiles 816 kB, benchmark_prices 616 kB (1,979 rows), financials 216 kB. Benchmark contribution: 0.6 MB total (4 rows + 1,979 bars).
Projection at full top-1000 scale: current 104 MB holds only ~250 fully-priced stocks (~190 bars avg); remaining ~750 stocks x ~500 bars x 183 B ~= ~69 MB prices + alpha backfill depth (~390 B/row x ~500 rows x 750 ~= ~146 MB if fully backfilled) + snapshots/periods/profiles/news ~= **~230-330 MB total**, under the 512 MB cap with ~180-280 MB headroom.
30/60/90-day steady-state growth (1 bar/day x 1000 stocks x 183 B + 1 alpha row/day x 1000 x 390 B + news title-only): ~= 0.6-1.0 MB/day => +30d ~= +20-30 MB, +60d ~= +40-60 MB, +90d ~= +60-90 MB. Headroom holds through 90 days.
Retention recommendation: none required now. First to cut if breached (Plan 22, unchanged): alpha backfill depth to 1y outside top 250 (saves up to ~100 MB); second: news title-only already in force. No historical data deleted. Rerun idempotency verified (benchmark rerun 1,979 offered / 0 duplicated; equity upserts on UNIQUE anchors; full suite green).

### 12.4 Universe (verified behavior, intentional)

ranked_in 1000 (top1000 membership exactly 1000), ranked_out 1416, excluded 7289 (M1-T2 audit, unchanged). Nightly passes read UNIVERSE_NAME=top1000 only: active ranked stocks refresh; ranked_out/excluded keep every stored row but receive no nightly refresh except via repair_catalog_gaps when they have gaps (verified in code: `_get_universe_symbols` filters on the universe name; repair pass queries zero-bar/all-null/no-profile catalog rows universe-independently). Intentional universe-driven behavior, not data loss. nifty50/100/250 rows retained as data.

### 12.5 Benchmarks

Symbols: `^NSEI` (NIFTY 50), `^NSEBANK` (NIFTY BANK), `^CNXIT` (NIFTY IT), `^CRSLDX` (CRISIL Broad Market Index). All resolve (quoteType INDEX, 5d bars verified pre-implementation); .info carries no fundamentals for indexes, so benchmarks ingest PRICES ONLY (2y, 493-496 bars each). Persisted to separate benchmarks/benchmark_prices tables (own upsert anchors); zero Stock rows created (`stocks WHERE symbol LIKE '^%'` = 0), so no interference with ranking/valuation/peers/screener. Runtime 1.8-3.8s; storage 0.6 MB. Provider limitation: yfinance-only (Upstox serves no index bars); failures isolated per index (D19). 6 backend tests green.

### 12.6 Altman Z-Score

Formulation: **Altman Z'' (1995, non-manufacturing / emerging-market)**: Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4 (X1 working capital/assets, X2 retained earnings/assets, X3 EBIT/assets, X4 book equity/liabilities); zones safe >2.6 / grey 1.1-2.6 / distress <1.1. Chosen because the SignalDesk universe is dominated by services/IT/financials: the 1968 Z and 1993 Z' both include X5 sales/assets (asset turnover), which structurally penalizes asset-light companies, and Z uses market-value leverage (pro-cyclical for a daily screen). Z'' drops X5 and uses book equity.
Required inputs: working capital, total assets, retained earnings, EBIT, book equity, total liabilities (all balance-sheet). Available in SignalDesk today: NONE (Semester 1 stores income statements only; snapshot carries no balance-sheet levels). Unavailable: all six. Coverage: 0% calculable today (honest); every response is status=unavailable with reason + missing-input list. Financials (sector markers: financial/bank/insurance/NBFC/housing finance) are non_applicable_financial even with data (verified live: HDFCBANK.NS). Example computed values (unit tests, hand-verified): safe 4.87, grey 2.06, distress -1.53; zone boundaries pinned. Missing values are never zero-filled; non-positive denominators are invalid_input.
Exposed: `GET /api/v1/stocks/{symbol}/altman` (pure read, deterministic, no provider calls) + FundamentalsSection "Financial distress" panel + methodology page section + METRIC_INFO `altman` entry. Solvency Score untouched (verified: same inputs still score 90/100 profitability/solvency in tests; Alpha weights unchanged). Tests: 17 backend (known I/O, missing/invalid, non-applicable, determinism, API incl. solvency-intact) + 1 frontend (endpoint shape) green. Pipeline position: pure read over the stored snapshot on request (no nightly pass needed; `_ingest_all` docstring records the verified cycle). Folding Altman into Alpha weights is documented as a FUTURE design decision, not implemented.

## 13. Follow-up round (2026-09-08, same day): Z-Scores now score, ETF + fund domains live

### 13.1 Altman Z-Score: real scores (was: honestly unavailable for everyone)

The M2 balance-sheet slice was pulled forward because a distress score that can never compute is a placeholder, not a feature.
- Migration `f1a2b3c4d5e6`: `balance_sheet_periods` (annual; working_capital, total_assets, retained_earnings, ebit, book_equity, total_liabilities, source; UNIQUE(stock_id, period_end, period_type)).
- Provider capability `get_balance_sheet` on the ABC (D56 pattern) + yfinance implementation (annual `balance_sheet` + `EBIT` from `income_stmt`; Working-Capital fallback CA-CL; banks legitimately lack it). `MergingProvider` passes it through (primary wins, secondary gap-fills).
- Nightly pass `ingest_balance_sheets` (batched, D19 isolation, CLI `balance-sheets`). MEASURED full run: 1,000/1,000 top-1000 stocks covered, 4,840 rows, 0 errors, **461s**. DB 104 -> 108 MB.
- Coverage: 796/1,000 latest periods carry ALL six inputs; the rest are mostly banks/NBFCs (no Working Capital) -> honest unavailable/non-applicable. Example live scores: RELIANCE **2.18 grey**, TCS **8.46 safe**; HDFCBANK `non_applicable_financial`. The reader (`compute_stock_altman`) stays a pure DB read on request.
- Tests: 13 new (upsert/idempotency/isolation, input mapping incl. never-zero-fill, available case x10 = same score, no-row unavailable, API).

### 13.2 ETF domain (Plan 9 slice, pulled forward)

- `ingest_etfs` pass + CLI `etfs`: get-or-create `is_etf` stocks rows for the curated `ETF_SYMBOLS` (16 majors; same set the ranking excludes, single source of truth) + price history via the standard equity pipeline. `ICICINIFTY.NS` has no Yahoo data (honest skip, 0 errors).
- `GET /api/v1/etfs`: symbol, name, last price, 1D, 1Y return, as-of. `/stocks` list + screener now exclude `is_etf` rows, so equity surfaces stay clean. 16/16 rows live with real prices (e.g. BANKBEES 589.09, 1Y +5.1%).
- Frontend `/etfs` page (nav link "ETFs") with DataState discipline; rows link to the standard research page.

### 13.3 Mutual-fund domain (Plan 8 slice, pulled forward)

- Tables `mutual_funds` + `mf_nav_history` (same migration). Curated catalog of 21 entries matched against the official AMFI NAVAll file by name+plan+option (verified against the LIVE file 2026-09-08: several funds renamed — Axis/ICICI Bluechip -> Large Cap, HDFC Mid-Cap Opportunities -> HDFC Mid Cap, Mirae Tax Saver -> Mirae Asset ELSS Tax Saver; the list matches 22 rows because one curated entry legitimately matches an extra share-class row; unmatched entries are logged, never guessed).
- `ingest_funds` pass + CLI `funds`: AMFI NAVAll is PRIMARY (8-column shape parsed defensively); mfapi.in history backfill (750 days, `source='mfapi'`) is the documented FALLBACK. MEASURED: 22 funds across 10 categories, 16,501 NAV rows, latest NAVs 2026-09-07/08, real returns live (e.g. UTI Nifty 50 Index 3M +3.40%).
- `GET /api/v1/funds` + `/funds/{id}` (returns computed backend-side by `services/funds.window_returns`; missing windows = null). Frontend `/funds` + `/funds/:id` pages (nav links "Funds").
- 9 new backend tests (parser shapes, share-class matching, catalog+NAV job, idempotent rerun, window-returns math, ETF row creation/universe exclusion).

### 13.4 Other changes in this round

- Plan 18 conformance: `prewarm_alpha_explanations` REMOVED from the nightly passes (no nightly bulk LLM pre-warming; helper retained for manual use).
- Fund/ETF ingestions ride the nightly `_ingest_passes` (measured contributions: balance sheets ~8 min at 1000, funds ~seconds after first sync, ETFs seconds).
- Suites: backend **423/423**, frontend **73/73**, `tsc -b` clean, `vite build` OK. Storage 108 MB of 512 MB.

## 14. Follow-up round 2 (2026-09-09): search/universe, honest nulls, technical sensitivity, Alpha v1.5

### 14.1 "ETERNAL/SWIGGY/IFCI missing" — diagnosis and fix

Diagnosis: all three WERE in the catalog and ranked-in (ETERNAL rank 31, SWIGGY 159, IFCI 326; verified in ranking_audit). Two real defects made them unfindable: (a) the header search filtered CLIENT-SIDE over `/stocks?limit=250` — the first 250 of 2,907 catalog rows, so everything past "C" was invisible; (b) part of the report window coincided with the dead-backend state (Vite proxy 500 family). Fixed:
- New `GET /stocks/search?q=` — server-side, universe-scoped, symbol/name match, prefix-ranked, debounced+abortable in the header (StockSearch rewritten; lib/search.ts retained as a pure util).
- `/stocks` list + `/screener` now present the ACTIVE ranked universe (`settings.active_universe`, default top1000): total = **1000** (was 2907). Rows outside the universe remain reachable by direct URL (`get_stock` deliberately not scoped). Verified live: search q=eternal/swiggy/ifci all return hits; `/stocks?limit=1` total = 1000; `/stocks/ETERNAL.NS` 200 with mcap Rs 2.96L Cr.
- 736 top-1000 stocks still had no bars (the nightly had never run at 1000 breadth); a full detached nightly run was started 2026-09-09 00:24 — job_runs: ingest_prices success 1000/0, ingest_financials success 1000/0 within minutes; remaining passes continue.

### 14.2 Null-input stocks rendered as errors -> honest "-"

`DataState` resolved `error` BEFORE `insufficient`, so a NO_PEERS / INSUFFICIENT_DATA envelope (a data gap, not a malfunction) rendered the red "Something went wrong" block on the valuation/scores regions for stocks with null snapshot fields. Fixed precedence: those two soft codes render the insufficient note ("-" UX) whenever the caller marked the region insufficient; genuine errors still render as errors.

### 14.3 Technical sensitivity recalibrated (v1.5)

The user's observation was correct and the cause was in `services/indicators.py`: the old scale constants (trend ±20% vs SMA20, momentum ±2% histogram/price, reversion RSI delta x0.5) mapped every realistic market state into the 40-60 band, and EMA(5) smoothing pulled it further to center — every stock read "moderate". New bands: trend ±8.3% vs SMA20 spans 0-100; momentum ±1.25%; reversion RSI 30->70 / 70->30 (slope 1.0). EMA(5) smoothing retained (drift, not sawtooth). Live sample after the change: trend components 23-46 across a downtrending large-cap sample with rising states reaching 78; the composite now differentiates weak/moderate/positive instead of pinning 45-50.

### 14.4 Alpha v1.5: balance sheet in the blend, news deprioritized (owner decision)

- Composite weights: **40% fundamental / 35% technical / 25% sentiment** (was 40/30/30; FinBERT-on-headlines is the most subjective pillar).
- Fundamental pillar: **45% profitability + 30% solvency + 25% Altman Z'' distress** (services/altman.distress_score_0_100: zone-anchored monotone mapping, z<=0 -> 0, 1.1 -> 40, 2.6 -> 70, >=5 -> 100), renormalized over available components — a missing diagnostic is dropped, never zero-filled. The distress component appears in `components` (`distress`) and in components_json.
- Verified live: ETERNAL composite 50 (fundamental 56, distress 97), RELIANCE 53 (distress 62); weights {0.4, 0.35, 0.25}. `/alpha/explanation`, ask evidence and the history backfill share the same math (`blend_fundamental` imported by jobs). Frontend copy updated (AlphaSection header, METRIC_INFO.alpha/technical_score, methodology page). Valuation stays separate; the standalone `/altman` endpoint is unchanged.
- Stored history: the running nightly's backfill_alpha_history recomputes it under v1.5.

Suites this round: backend **430/430** (new: search x4 incl. universe scoping, blend + distress mapping, technical sensitivity), frontend **73/73**, tsc clean, build OK.

## 15. Follow-up round 3 (2026-09-09): calculation gaps, dashboard, funds depth

### 15.1 Valuation gaps filled with STORED Upstox ratios (D65, no request-path calls)

- Migration `a3b4c5d6e7f8`: `financials.ev_ebitda` column. Upstox supplies EV/EBITDA as a pre-computed RATIO (never EV + EBITDA absolutes); the nightly financials pass stores it via the merged snapshot and `valuation.compute_multiple("EV_EBITDA")` falls back to the stored ratio when the absolutes are absent. Upstox P/S also mapped when the feed carries it.
- Re-ran ingest_financials over the top-1000 (201s): 474 EV/EBITDA ratios stored. Verified: Swiggy now carries P/E -20.38 (loss-maker; P/E honestly cannot rank a negative multiple -> INSUFFICIENT_DATA verdict) and P/B 3.92 with a working peer verdict; the EV/EBITDA gap closes for the ~474 stocks whose only source is that ratio.
- Negative P/E stays a data gap by design (`_is_valid` requires a positive multiple): the verdict panel explains it rather than estimating.

### 15.2 Valuation frame no longer collapses on data gaps

The whole section used to render a single "Not computable" card when the SELECTED metric was incomputable. Rebuilt: the frame always renders; the verdict panel shows either the verdict or a compact honest note ("lacks the inputs... other multiples below may still be computable"), and the all-multiples grid stays visible with "-" per gap. Soft codes (NO_PEERS/INSUFFICIENT_DATA) can no longer surface as red error cards here.

### 15.3 Blank stock pages fixed with per-section error boundaries

IFCI loaded and went blank because ONE section throwing during render unmounted the whole route. Every stock-page section now sits in its own ErrorBoundary (compact retry card, page stays up). Also recorded: recently-viewed tracking on every stock visit (device-local, lib/recent.ts).

### 15.4 Sectors backfilled across the top-1000

The nightly profiles pass now also fills stocks.sector/industry (NULL only, never overwrite) from the merged provider classification; a one-off backfill filled 698 + 253 = 951 gaps in two passes (252 first-pass failures were Upstox 429s, all healed on rerun). Sector NULL in top-1000: **0**. Markets/screener sector filters are fully populated.

### 15.5 Markets page -> dashboard

- Index cards: GET /benchmarks (stored benchmark tables; now 6 indexes incl. Sensex ^BSESN and India VIX ^INDIAVIX) with close, day change and 90d sparkline.
- Today's movers: GET /stocks gains `mcap_bucket` (large >= 1L Cr, mid 20k-1L, small < 20k) - gainers/losers flip within a size class.
- Market news feed: GET /market/news (latest across the universe, newest first).
- Device-local watchlists (multiple named lists, create from the dashboard or from any stock header via the new watchlist button) and recently-viewed panel. Account-backed lists remain M3.
- ETF + fund snapshot panels; SIP/SWP lab stub button (honest "coming soon" - it is scoped for the scenario lab).

### 15.6 Funds: sorting, CAGR windows, NAV chart

- GET /funds: server-side sort on category, name, NAV and EVERY return window (asc/desc, nulls last); 1y/3y returns are CAGR. Anchors require the window to be actually covered (21-day tolerance) - a 1y window over 8 months of history is None, never annualised from a stretched anchor.
- GET /funds/{id}?window=1m|3m|6m|1y|3y|all: window-sliced, stride-downsampled series (120 points) + dependency-free SVG NAV chart; holdings section states honestly that portfolio disclosures are the M5 dependency.
- Landing: ticker tape of the 50 largest at the top; the unfinished illustrative bar field is now REAL - the 50 largest, one bar each, sized by today's absolute move, colored red/green like the charts (hover readout); UniverseStrip renders the top 8 by market cap (4x2) instead of a hardcoded name list that silently matched one row.

### 15.7 Operational notes

- The long-running nightly process lazily imported the NEW financials repo against the OLD cached models after my live migration -> both alpha passes failed 1000/1000 ('Financials' object has no attribute 'ev_ebitda'). Re-ran both with fresh code: backfill 732s + snapshots 855s, full top-1000 history under Alpha v1.5. Lesson recorded: re-run affected passes after migrating alongside a running job process.
- Suites: backend **431/431**, frontend **73/73**, tsc clean, vite build OK.
