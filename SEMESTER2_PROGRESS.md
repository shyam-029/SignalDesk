# SignalDesk - Semester 2 Progress Tracker

> **Purpose:** The operational companion to `SEMESTER2_PLAN.md`. Read this file FIRST to resume work, then the plan for the what/why.
> **Rules:** Current state, then active milestone, then next task. Checklists per milestone. Verification results. Risks and pending human decisions stay visible until closed.
> **Last updated:** 2026-09-08 (M1-T2 done: top-1000 ranking live, 384 backend / 72 frontend green, real ranking run 1000 ranked in + full audit trail).
> **Companion:** `SEMESTER2_PLAN.md` (sections cited as Plan 1-30). Semester 1 record: `PLANNING.md` / `PROGRESS.md`, frozen, unmodified.

---

## 1. Current State

| Item | State |
|---|---|
| Repo / branch / HEAD | `C:\Users\shyam\Desktop\Projects\signaldesk`, `main`, `968a44d` (Phase 8 complete, clean tree) |
| Semester 1 | COMPLETE (Phases 1-8). Backend 348/348 (zero-network), frontend 72/72, tsc clean, build OK |
| Semester 2 plan | COMPLETE (`SEMESTER2_PLAN.md`, 30 sections + appendices) |
| Semester 2 implementation | IN PROGRESS (M1-T1, M1-T2 done) |
| Active milestone | **M1 - Scale-Up and Ship It** |
| Next concrete task | **M1-T3:** one measured end-to-end chunked ingestion run in Actions; runtime recorded vs 6h cap (includes the nifty250 -> top1000 UNIVERSE_NAME cutover decision) |

## 2. Milestone Board

| Milestone | Status | Depends on | Definition of done |
|---|---|---|---|
| M1 - Scale-Up and Ship It | IN PROGRESS (T1, T2 done) | - | Plan 24/M1 |
| M2 - Statements and Depth | NOT STARTED | M1 | Plan 24/M2 |
| M3 - Accounts and Workspace | NOT STARTED | M1 (parallel with M2) | Plan 24/M3 |
| M4 - Fund Data Backbone | NOT STARTED | M1 | Plan 24/M4 |
| M5 - Fund Research Experience | NOT STARTED | M4 | Plan 24/M5 |
| M6 - ETF Layer | NOT STARTED | M2 + M5 | Plan 24/M6 |
| M7 - Scenario and Forecast Lab | NOT STARTED | M4/M5 | Plan 24/M7 |
| M8 - Research Synthesis and Close | NOT STARTED | All | Plan 27 |

## 3. Active Milestone Checklist (M1)

- [x] M1-T1: `.github/workflows/ci.yml` runs backend pytest (348 baseline), frontend vitest/tsc/build on every push
- [x] M1-T2: top-1000 ranking job implements eligibility rules E1-E12 (Plan 7) with per-symbol audit reasons
- [ ] M1-T3: one measured end-to-end chunked ingestion run in Actions; runtime recorded vs 6h cap (Plan 22)
- [ ] M1-T4: storage projection recorded vs 0.5 GB cap; canary test in place (Plan 22)
- [ ] M1-T5: production deploy per Plan 21 (Pages + Render + Neon + cron); `/health` and `/status/full` smoke green
- [ ] M1-T6: benchmark index ingestion (`^NSEI`, sector symbols) live
- [ ] M1-T7: nightly cron green one full week; zero-cost itemized and verified
- [ ] News breadth gate: news stays core-500 until the M1-T3 benchmark proves headroom (tiered decision)

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

Not deployed. Target topology: Cloudflare Pages (frontend) + Render free API + Neon free Postgres + GitHub Actions cron/CI (Plan 21). Runbook: Plan 28. Blocked only on human decisions in section 9 (hosting choice among verified-free options is made; account creation + secrets entry remain).

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

## 11. Work Log

- 2026-09-08: Semester 2 master plan written (`SEMESTER2_PLAN.md`, 30 sections); this tracker created. No application code changed. Semester 1 `PLANNING.md`/`PROGRESS.md` left untouched. No commit, no push.
- 2026-09-08: **M1-T1 done** @ `9dfd182` - added `.github/workflows/ci.yml` (two parallel jobs, push/PR to `main` + `workflow_dispatch`; backend: Python 3.12, `postgres:17` service on localhost:5432 with `signaldesk_test` DB matching conftest, pip cache, `alembic upgrade head` then pytest; frontend: Node 22, npm cache, `npm ci`, `npm test`, `npm run typecheck`, `npm run build`). Run 1 (push, `34211797445`) and run 2 (`workflow_dispatch` re-run, `34212950591`) both green: backend 348/348 with migrations to head `c1d2e3f4a5b6`; frontend 72/72, tsc clean, build OK. No flakiness observed; no env diffs found; no application/test code touched. Known cosmetic issue only: GitHub annotations warn that `actions/*` v4/v5 Node 20 targets are force-run on Node 24 (deprecation notice from GitHub, not a failure; revisit when actions v5/v6 replacements stabilize).
- 2026-09-08: **M1-T2 done** @ `4f08d91` (CI `34222965567` green) - top-1000 universe ranking per Plan 7. New: `services/ranking.py` (pure E1-E12 logic), `repositories/ranking.py`, `providers/nse_master.py`, `data/ranking_exclusions.py` (curated ETF/REIT lists), migration `d4e5f6a7b8c9` (2 tables: `ranking_cycles`, `ranking_audit` + 8 additive `stocks` columns: isin, active, delisted_reason, delisted_at, mcap_rank, mcap_asof, restrict_flag, is_etf; no `active` collision existed). Job pass `rank_universe` via `python -m app.jobs rank` + `rank.yml` (`workflow_dispatch` ONLY, no cron - monthly schedule deferred to M1-T5). Nightly ingestion still reads `nifty250` (cutover is M1-T3). **Approved decisions 1-8 implemented as specified.**
  **Deviation 1 (pre-authorized "or equivalent" clause):** NSE `EQUITY_L.csv` returns HTTP 404 (dead URL, verified httpx + curl); the ranking reads the Upstox NSE instruments master instead - same endpoint `upstox_provider` already uses, no key, and its `instrument_type` field carries the NSE series codes verbatim, so E1-E5 semantics are unchanged (E4 actually improved: REIT/InvIT/SGB excluded structurally, curated list remains for ETFs).
  **Deviation 2 (found by the real run, fixed in this commit):** first real run exposed a rename-shadow gap - the catalog held both TATAMOTORS.NS (old seed) and TMPV.NS (current symbol); TMPV ranked while TATAMOTORS was wrongly deactivated as `absent_from_master`. Fixed: an absent catalog row whose alias target is ranked under its newer symbol now audits `renamed` (same live entity, never deactivated); second real run healed the row (active=True) and confirmed idempotency (1 cycle row, 9705 audit rows, identical counts both runs).
  Verification: backend **384 passed** (36 new tests), frontend **72/72**, tsc clean, build OK; migration applied cleanly locally and in CI; real run: 1000 ranked in / 1416 ranked out / 7289 excluded / 0 errors, `top1000` membership exactly 1000, nifty250 universe untouched; "why isn't X" query verified on real audit data.
- 2026-09-08: **Website 500 diagnosed and resolved (no application change)** - gate clearance before M1-T3/T4/T6. Diagnosis path per protocol: (1) port scan: frontend dev server (5173) listening, backend (8000) NOT; (2) reproduced the exact reported error at the frontend origin - `GET localhost:5173/api/v1/*` -> HTTP 500 "Internal Server Error" with an empty body; (3) root cause: **Vite's /api proxy returns a literal 500 when its upstream (127.0.0.1:8000) has no listener** - the backend process simply was not running (environment/stale-process class, matching the §10 gotcha family); (4) started uvicorn from current M1-T2 code; (5) verified: the user's own browser flows in the access log all 200 (`/stocks`, `/stocks/{s}/technicals|scores|news|sentiment|valuation|alpha|alpha/explanation` incl. a real OpenRouter call falling back to rule-based per design); direct API sweep all 200 (`/health`, `/status`, `/stocks?limit=200` over the ~2200-row post-ranking catalog, `/stocks/TMPV` + technicals/performance/peers/alpha/history for a ranking-created symbol, `/screener`, `/financials/history`; `/stocks/NEWIPO` correctly 404s with the error envelope - unknown-symbol semantics, not a crash); zero `status=500` lines in the backend log; the exact original failing request through the proxy now returns **HTTP 200, 28,846 bytes**. **Verdict: environment-only, NOT M1-T2, no code changed** - M1-T2 data/schema state explicitly cleared (ranking-created rows serve 200 across detail/technical/performance/peers/alpha surfaces). Backend full suite re-run post-resolution: **384 passed**. Frontend code untouched (last CI run `34223448384` green). Gotcha added to §10 for future recognition of the Vite-proxy-500 signature. **Gate for T3/T4/T6: CLEARED.**

---

*Resume here. Next: M1-T3 (measured chunked ingestion run in Actions; includes the nifty250 -> top1000 cutover). Plan reference: `SEMESTER2_PLAN.md` section 30.*
