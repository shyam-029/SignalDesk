# Storage & reliability remediation log

Running record of the 2026-11 audit remediation: what changed, why, how it was
verified, and what risk remains open. Newest entries first. Production numbers
come from workflow logs; nothing here contains credentials or hostnames.

## Nightly of 2026-11-10 — first run with PRs #10-#17 (recorded 2026-11-11)

Run 42896037285 (scheduled), 20:30-21:39 UTC, success. Code at 13db529,
the pre-rewrite SHA of today's main (same tree as 40055e5), so it includes
the Upstox price fallback, pooled job connections (item 22), the
snapshot-date fix (item 17) and the Phase 2 guards.

**Runtime: 65.2 min (nightly_ingestion 3,914 s), was 123 min.**

| Pass | 2026-11-10 16:17 run (s) | This run (s) |
|---|---|---|
| ingest_prices | 655 | 350 |
| ingest_financials | 529 | 301 |
| ingest_financial_periods | 940 | 535 |
| ingest_balance_sheets | 524 | 311 |
| ingest_company_profiles | 872 | 471 |
| ingest_etfs / funds | 18 / 92 | 13 / 51 |
| repair_catalog_gaps | 584 (54 stocks) | 25 (4 stocks) |
| backfill_alpha_history | 1,264 | 673 |
| record_live_alpha_snapshots | 861 | 517 |
| ingest_news | 1,005 | 641 |

Every pass ran at roughly half its previous time, including the
fetch-bound ones. Connection pooling (no fresh TLS handshake per symbol) is
the most likely cause, but the two runs are not a controlled comparison:
the earlier one ran in the afternoon UTC on a manual dispatch, this one at
the scheduled night slot, and Yahoo's latency differs by time of day. The
next few nightlies will show whether ~65 min holds. Repair was fast mainly
because the earlier run had already repaired 50 of its 54 stocks.

**Writes (Phase 2 guards, second confirmation):**

| Pass | Offered | Inserted | Updated | Unchanged |
|---|---|---|---|---|
| Prices | 453,298 | 0 | 36,616 | 416,682 (91.9%) |
| Alpha backfill | 482,555 | 0 | 40,528 | 442,027 (91.6%) |

0 price rows inserted is expected: the 16:17 run had already stored
2026-11-10, a market holiday. Stale alpha dates deleted: 0. Live snapshots
stored: 1,000.

**Upstox fallback (first night with the token):**

- Main price pass: no fallback needed; Yahoo answered all 1,000 symbols.
- `NXT100CASE.NS` (item 2b): Yahoo's frame was stale (2 bars, newest
  2026-10-16), Upstox filled 17 trading days. Repair finished 4/4 with 0
  failures, so the night is `success` for the first time since 2b began
  (it was `partial`). The 17 filled days are unadjusted exchange prices
  inside an adjusted series, the trade-off accepted in
  `providers/fallback.py`. That only matters if this ETF has a split or
  dividend in the gap.
- `POWERIETF.NS`, `VEEFIN.NS` (catalog repair): Yahoo returns 404 "Quote
  not found" and Upstox returns 0 candles. Likely delisted or renamed, so
  neither source has data. They did not fail the pass.
- `ICICINIFTY.NS` (ETF pass and repair): Yahoo empty; the Upstox lookup
  raised MarketDataError, most likely because the symbol is not in Upstox's
  NSE equity instrument list. It did not fail the pass.

**Item 17 not exercised.** The run started at 20:30 UTC on 2026-11-10, so
the runner's date and the last bar's date were the same day. The fix
(snapshots dated by the latest stored bar) only shows on a run whose UTC
date has no bar, e.g. a Saturday/Sunday run or one after midnight UTC.
Verified by tests only so far.

## Items 12, 14, 16 — Screener cache, browser caching, keep-warm (2026-11-10)

**Problems.**

- The screener analysed every stock in the top-1000 on every request:
  one stock lookup plus `analyze_stock` (financials, peers, peer
  financials) each, about 4,000 database round trips from Render's free
  instance to Neon per page load and per sort click.
- API responses carried no cache headers, so every navigation refetched.
- Render's free instance sleeps after ~15 minutes idle; the next visitor
  waits 30-60 s.

**Change.**

- `services/screener_cache.py`: the analysed universe is built once and
  reused until the newest finished `job_runs` row changes (any nightly,
  rank or manual pass) or 1 hour passes. Concurrent first requests share
  one build. The router's filters, sorting and paging are unchanged;
  `analyze_stock` is unchanged, so results are identical. The unused
  `stocks.list_all_symbols` was removed.
- `main.py`: successful `GET /api/v1/*` responses get
  `Cache-Control: public, max-age=60, stale-while-revalidate=300`.
- `keep-warm.yml`: pings `/health` and `/api/v1/screener?limit=1` every 10
  minutes, 02:30-18:59 UTC (08:00-00:30 IST). Not 24/7: Render's free tier
  allows 750 instance-hours a month across all free services; this uses
  about 500.
- Frontend `lib/queryPersist.ts`: successful queries are saved to
  `localStorage` (12 h max age, 1.5 MB cap, versioned) and restored on load,
  then refetched in the background as usual. No new dependency.

**Verification.** Frontend: 78 tests pass (6 new for persistence: round
trip, failed queries skipped, expiry, version mismatch, blocked/corrupt
storage, size cap), type check and production build pass. Backend: new
tests prove repeat screener requests reuse one analysis, a finished job or
the max age triggers exactly one rebuild, cached rows equal direct
`analyze_stock` output field for field, and cache headers appear only on
successful API GETs. Backend tests run in CI (no local Postgres).

**Not done.** Item 15 (rate-limiter client IP): Render does not document
how it forwards the client IP, so the trusted `X-Forwarded-For` hop must be
confirmed from real request headers first. No shared edge cache yet: the
browser calls Render directly, so `Cache-Control` only helps each visitor's
own browser.

## Items 7, 8, 9, 20, 21, 23 — Restore test, failure alerts, workflow hardening (2026-11-10)

**Problems.** Nobody had ever restored a backup (the backup job only reads
the archive's table of contents). 45 nightly runs failed unnoticed. A
scheduled workflow (db-probe) had been silently disabled by GitHub. The
production `restore.yml` could run with one click and during an ingest, and
printed the database user. Several dispatch inputs were interpolated straight
into shell or Python source.

**Change.**

- `restore-test.yml` (item 7): restores the newest `signaldesk-db-dump`
  artifact into a Postgres 17 service container on the runner, with
  `pg_restore --exit-on-error`, then fails if any core table has zero rows.
  It has no database secret, so it cannot reach production. Monthly on the
  2nd at 05:00 UTC and on demand. (Replaces an untracked draft that needed a
  scratch Neon database, which would also have counted against the cap.)
- Alerts (item 8): `ops/ci/alert.sh` opens one GitHub issue per alert title
  (label `ops-alert`), comments on it while the problem repeats, and closes
  it on recovery. `run-alert.yml` is the reusable job; `ingest`, `rank`,
  `backup` (the backup job, not the canary) and `restore-test` call it.
- `watchdog.yml` (items 8 and 9): daily at 08:00 UTC, alerts if no ingest
  run succeeded in the last 30 hours or if any workflow is not `active`.
  Read-only, GitHub API only.
- `restore.yml` (item 20): requires typing `RESTORE-PRODUCTION`, joins the
  `nightly-ingestion` concurrency group, no longer prints database or user.
- Inputs via env (item 21): `db-forensics.yml`, `migrate.yml`,
  `restore.yml`, `restore-test.yml` (which also rejects a non-numeric run id).
- `.gitignore` (item 23): `*.dump`.

**Verification.** All workflow files parse. `alert.sh` was exercised
against a stub `gh` for eight cases: first failure opens, repeat failure
comments, success closes only the exact title, a different open alert is
left alone, titles with quotes, and an invalid state exits 2. Its filter,
the watchdog's ingest-age calculation (10 h at the time) and its
disabled-workflow query were run against the real repository (read-only).
Verified on GitHub after merging (PR #9, 2026-11-10):

- `restore-test` run 42850802659: **success.** Restored backup run
  42803216508 (`signaldesk-20261110-1055.dump`, 55 MB) with
  `--exit-on-error`. Row counts match the Phase 1 forensics exactly:
  daily_prices 1,273,188; alpha_scores 507,321; news_articles 61,264;
  ranking_audit 29,301; mf_nav_history 16,772; benchmark_prices 5,395;
  stocks 3,001; financials 2,923; alembic_version 1. The backup is
  restorable. Its alert job ran and found nothing to open.
- `watchdog` run 42850822540: **success.** Last successful ingest 10 h
  earlier; no disabled workflows; no issue opened.
- All 11 workflows are registered and active, including `restore-test`,
  `run-alert` and `watchdog`.

**Known limits.** GitHub can disable the watchdog itself after 60 days
without repository activity. A `partial` nightly (some symbols failed)
exits 0 and does not alert.

## Phases 4 and 5 — Migrations only by hand; no connection details in public logs (2026-11-10)

**Problem.**

- `ingest.yml` and `rank.yml` ran `alembic upgrade head` against production
  before every job, so any merged migration reached the production schema
  unreviewed and un-backed-up, on whatever night ran next.
- `rank.yml` carried three temporary credential-debugging steps (credential
  fingerprint, direct-vs-pooler connectivity matrix) that print the database
  host, user, database name and port into public Actions logs.

**Change (workflows only; no application code, no migration).**

- Removed the fingerprint and connectivity-matrix steps from `rank.yml`.
- Replaced `alembic upgrade head` in both workflows with a **schema-at-head
  check**. The only way to change production schema is now the `migrate`
  workflow (`direction=upgrade`, `revision=head`).
- The check fails fast and names `migrate.yml` in a `::error::` annotation,
  both when the schema is behind code and when the revision cannot be read.
  Raw alembic output is deliberately never printed, because a connection
  error can carry the host and these logs are public.

**Operating consequence (read this).** After merging any PR that adds an
Alembic migration, dispatch `migrate` *before* the next nightly (13:30 UTC)
or monthly rank (04:00 UTC on the 1st). A forgotten migration now stops the
run immediately with a clear message instead of running new code on an old
schema. A failed scheduled run is not by itself an alert: 45 consecutive
failed nights (2026-09-25 to 2026-11-08, Phase 1 finding) went unnoticed, so
failure alerting is a separate open item, not solved here.

**Not verified / still open.**

- Whether Render also runs `alembic upgrade head` as a release command (there
  is no `render.yaml` in the repo; this is a Render dashboard setting). If it
  does, deploys still auto-migrate and that setting should be cleared.
- Not run: workflow YAML parses; the check itself only runs on the next
  scheduled or dispatched run.
- Old public run logs that already contain the host, user and database name
  are not deleted by this change. The password was never printed. Rotating
  the Neon password and deleting those runs are owner decisions.
## Phase 3 — Correct the storage cap; make alpha pruning impossible by accident (2026-11-10)

**Problem.** Every storage guard assumed Neon's 512 MB free limit. Phase 1
read `neon.max_cluster_size = 1024 MB` from the production database, so the
weekly canary (red from 450 MB) had been alarming against the wrong limit,
and `prune-alpha` was gated on `pg_database_size`, which includes bloat: a
size gate can fire without live data having grown, and the cap error made
it look nearer to firing than it was. The prune was only reachable by hand
(no workflow runs it), but it armed itself on size.

**Change (code and workflow thresholds only; nothing deleted, no migration).**

- `services/storage.py`: `NEON_CAP_BYTES` = 1024 MiB; baseline refreshed to
  the measured 561,414,144 bytes; growth band widened to 1.0–3.1 MB/day
  (2.9 MB/day observed, inflated by the churn Phase 2 removes). Worst-case
  90-day projection is 840.4 MB.
- Advisory alarm moved from 450 to **800 MB** (`settings.storage_cut_threshold_mb`,
  `DEFAULT_CUT_THRESHOLD_MB`, and the canary step in `backup.yml`, kept in
  sync). It is advisory only and never triggers a deletion.
- `prune_alpha_history_outside_top250` no longer has a size gate. It deletes
  nothing and reads nothing unless called with the exact phrase
  `DELETE-ALPHA-HISTORY`: `python -m app.jobs prune-alpha --confirm DELETE-ALPHA-HISTORY`.
  Owner rule: alpha pruning is not enabled; run it only with explicit approval.
- A test fails if any workflow contains `app.jobs prune-alpha`.
- `backup.yml`: the canary stays in its own `storage-canary` job
  (`needs: backup`, `if: always()`); only its threshold and message changed.

**Not verified.** The pure canary tests pass locally (7). The five prune tests
need Postgres and are untested locally; CI is their first run. The 1024 MB
figure is Neon's enforced setting, not a console screenshot of the plan.

**Still open.** An orphan `prune-alpha-recovery` workflow from the deleted
branch `ops/m2-t1-storage-reclaim` is still registered on GitHub (flagged for
the owner; not disabled here). Existing index bloat (notably
`alpha_scores_pkey`, 93.8 MB) is not reclaimed by this phase.

## Phase 2 — Stop nightly write churn (2026-11-10, code only, no migration)

**Problem (measured in Phase 1).** Each nightly run re-offers ~462k price
bars and ~493k alpha snapshots and rewrites all of them: the price upsert has
no unchanged-row guard, and the alpha backfill deleted every technical-only
row and re-inserted it (cumulative 10.5M inserts / 10.0M deletes on a 507k
row table; `alpha_scores_pkey` bloated to 93.8 MB with 0 scans). The
delete and insert were separate transactions, so a symbol briefly had no
history, and a crash between them lost it until the next run.

**Change.**

- `app/repositories/upsert_guard.py`: shared helpers. `any_distinct` builds
  the `DO UPDATE ... WHERE <any column IS DISTINCT FROM new value>` guard;
  `INSERTED_FLAG` = `RETURNING (xmax = 0)` so each upsert reports what it
  actually wrote.
- Price upsert (`jobs._fetch_one_symbol`, shared by prices, ETFs and
  catalog repair) and benchmark upsert: guarded; COALESCE semantics kept.
  `ingest_prices` now also reports `inserted` / `updated` / `unchanged`
  (`bars` keeps its meaning: rows offered).
- Alpha backfill: `alpha_repo.sync_backfill_snapshots` replaces
  wipe+insert with one transaction: guarded upsert (live snapshots with a
  fundamental score are still never overwritten) plus a delete of stale
  technical-only dates only. Same end state; ids are kept, so the primary
  key stops growing. Pass reports `inserted` / `updated` / `unchanged` /
  `deleted`.
- `record_live_alpha_snapshots` now records `items_processed` (`stored`).

**Expected effect, honestly.** Unchanged price bars stop being rewritten.
For alpha, every backfilled row's composite blends the symbol's *latest*
fundamental and sentiment (documented approximation D71), so a symbol whose
sentiment summary moves still has its whole series updated. Those updates
are now in place (same ids, often HOT) instead of delete+insert, which is
what stops the index bloat, but the row-version count for alpha may stay
high. The first nightly log after deploy gives the real split.

**Result (item 2a)** — run 42852962417, 2026-11-10 16:17-18:22 UTC (an NSE
holiday; code at 4ad7afb, i.e. Phase 2 included, PRs #10-#15 not yet):

| Pass | Offered | Inserted | Updated | Unchanged | Before Phase 2 |
|---|---|---|---|---|---|
| Prices | 453,298 | 778 | 32,343 | 420,177 (92.7%) | ~462,514 rewritten |
| Alpha backfill | 482,555 | 605 | 18,362 | 463,588 (96.1%) | ~493,386 deleted + re-inserted |

- Rows written per night: ~52k instead of ~1.45M row operations, about a
  96% cut. Stale alpha dates deleted: 0.
- The alpha saving is larger than feared: the latest-sentiment blend
  changed only ~3.8% of backfilled rows.
- Runtime 123 min (nightly_ingestion 7,381 s). Alpha backfill 21.1 min
  (was 26.0). Prices 10.9 min (was 11.1). Phase 2 cut writes, not fetching.
- Night status `partial`: one catalog-repair failure, `NXT100CASE.NS`
  (Yahoo's last bar 2026-10-16, refused by the stale-frame guard; work
  list 2b). Repair handled 54 stocks because the morning's ranking added
  new catalog rows.
- The schema-at-head check (Phase 4) passed on its first real run.

**Not changed.** No schema change, no migration, no data deleted beyond
what the old backfill already deleted. Existing bloat is not reclaimed by
this phase (that is Phase 6: online index rebuild).

## Phase 1 — Read-only storage forensics (2026-11-10)

**Purpose.** Replace estimates with measurements before any write-path,
index or vacuum change: dead tuples, per-index sizes and scan counts, Neon's
own size metric and enforced limit, bars by year/month/owner (incl. bars
older than the 2y fetch window), alpha backfill vs live rows, weekend-dated
and orphaned alpha rows, news growth, and pass re-runs per day.

**Change.**

- `ops/sql/storage_forensics.sql` and `ops/sql/job_health.sql` (30-day
  nightly health). Both run inside `BEGIN READ ONLY`; Postgres rejects any
  write. Optional tooling (`pg_cluster_size`, `pgstattuple_approx`) is used
  only if already present, each probe behind its own exception handler. No
  `CREATE EXTENSION`.
- `db-probe.yml`: new `forensics` dispatch input; both scripts run only on a
  manual dispatch with `forensics=true`. The weekly schedule is unchanged.
- `backend/tests/test_storage_forensics_sql.py`: keyword scan for writes/DDL,
  empty-schema run of both scripts, a seeded run of the forensics script on a
  fresh connection (its own READ ONLY transaction), and a proof that a write
  inside `BEGIN READ ONLY` raises.

**Known limit.** The share of nightly price writes that are true no-ops
cannot be measured read-only from the database (it needs the provider data).
Phase 2's guarded upsert reports it directly as rows actually updated.

**Results** (db-probe run 42806316780, 2026-11-10 11:18 UTC, read-only):

- **Enforced limit is 1 GB, not 512 MB**: `neon.max_cluster_size = 1024 MB`.
  561 MB is ~55% of it. `NEON_CAP_BYTES` (512 MB), the 450 MB canary and the
  450 MB prune gate are all calibrated to the wrong cap.
- **Largest single waste: `alpha_scores_pkey` = 93.8 MB with 0 scans.** A
  compact btree on 507k integer ids is ~11 MB; the excess is index bloat
  from the backfill's delete+insert pattern (cumulative 10.5M inserts /
  10.0M deletes on a 507k-row table). `alpha_scores` indexes (127 MB) are
  larger than its heap (103 MB).
- Redundant indexes measured: `ix_daily_prices_stock_id` 17.2 MB,
  `ix_alpha_scores_symbol` 9.0 MB; the rest are < 0.5 MB combined.
- Dead tuples: daily_prices 12.9%, alpha_scores 11.6%. daily_prices last
  autovacuum 2026-09-23 (stays under the default 20% trigger); 53% of its
  updates are HOT.
- Table totals: alpha_scores 230 MB, daily_prices 216 MB, news_articles
  77 MB (of which `uq_news_articles_url` 41 MB; `content` is NULL in every
  row), everything else < 25 MB.
- Prices: 1.27M bars; 1,931 catalog stocks outside top-1000 hold 769k bars
  (60%, frozen since the mid-September cutover). 100k bars are older than
  2 years (38k of them top-1000) and are never re-fetched or re-adjusted.
- Alpha: 4,010 of 18,305 live snapshot rows are dated on a weekend
  (confirms the UTC-date / non-trading-day finding). No orphaned symbols.
- News: 61k articles; burst Jul–Sep 2026 (32.6k in Sep), now 4–6k/month.
- Extensions: `pgstattuple` and `pg_repack` are available but not
  installed; Neon's `pg_cluster_size()` is not exposed.
- **Nightly ingestion failed every scheduled night from 2026-09-25 to
  2026-11-08 (45 nights)** with `ModuleNotFoundError: psycopg`, before any
  job_runs row was written, so `/debug/jobs` showed nothing. Bars were
  recovered by the 2y re-fetch on 2026-11-09; per-day live alpha snapshots
  and news for that window were not.

## Phase 0 — Restore a working backup (2026-11-10)

**Problem (verified from Actions logs).** No backup artifact has been stored
since at least 2026-10-04:

- 2026-10-04 → 2026-11-08: `pg_dump` inside the container could not reach the
  database (`PGURL` not passed into the container; fixed in `05cc1d0`).
- 2026-11-10: the dump succeeded (55 MB), but the storage canary ran between
  the dump and the upload in the same job and exited 1 at 561,414,144 bytes,
  so the upload step never ran and the dump was discarded.

**Change.** `.github/workflows/backup.yml` split into two jobs:

- `backup`: dump → verify (`pg_restore --list` must read the archive and
  find `TABLE DATA` for the core tables) → upload (`if-no-files-found: error`).
  Records file name, size and sha256 in the run summary.
- `storage-canary`: runs after `backup` regardless of its outcome
  (`needs` + `if: always()`), cannot affect it, and still fails at ≥ 450 MB.
  The alarm text no longer instructs running the Plan 22 alpha cut; it points
  at forensics first and requires owner approval for any deletion.

Both jobs are read-only against the database. Run-level conclusion stays red
while the canary alarms; read the `backup` job status for backup health.

**Verification.** YAML parsed; TOC table-match logic exercised against a
sample `pg_restore --list` listing (exact-name match, no prefix false
positives). Then dispatched on branch `ops/phase0-backup-first`
(run 42803216508, 2026-11-10 10:55 UTC):

- `backup` job: **success**. `signaldesk-20261110-1055.dump`, 55 MB, archive
  TOC readable (173 entries), TABLE DATA present for all 9 checked tables.
  Artifact `signaldesk-db-dump` stored (57,422,447 bytes zipped), expires
  2026-12-10.
- `storage-canary` job: failure as designed — 561,414,144 bytes (unchanged
  from the 06:45 UTC reading the same day).

First stored backup since at least 2026-10-04. Not yet proven restorable:
a TOC read is not a restore.

**Open after Phase 0.**

- Confirm the actual Neon plan limit and the console's storage figure
  (the DB reports 561 MB against an assumed 512 MB cap while writes still
  succeed — the cap or the metric is not what the code assumes).
- Test a restore of the artifact into a scratch database (not production).
- Artifacts are retained 30 days only; consider an off-GitHub copy.

## Outstanding risks (from the audit, not yet addressed)

| Risk | Status |
|---|---|
| `prune-alpha` gate is armed (uses `pg_database_size`, which includes bloat) | fixed (Phase 3): needs an explicit confirmation phrase, no size gate |
| Migrations auto-apply to production via `ingest.yml` / `rank.yml` | fixed (Phase 4); Render's start command is plain `uvicorn` (owner confirmed 2026-11-10), so no deploy path migrates |
| Alpha backfill delete+insert churns ~493k rows/run and is non-atomic | fixed (Phase 2, PR #5); awaiting first nightly numbers |
| Price upsert rewrites ~462k unchanged rows/run | fixed (Phase 2, PR #5); awaiting first nightly numbers |
| Adjusted-price seam at the 2y fetch-window edge | open — needs owner decision |
| `rank.yml` logs DB host/user/db name to public Actions logs | steps removed (Phase 5); the 12 runs whose logs showed host/user deleted 2026-11-10 (11 rank, 1 restore); password rotation still open (owner) |
| Orphan `prune-alpha-recovery` / `db-probe-recovery` workflows registered on GitHub | removed 2026-11-10 (runs deleted; no workflow file on any branch) |
