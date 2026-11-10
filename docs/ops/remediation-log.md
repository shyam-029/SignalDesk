# Storage & reliability remediation log

Running record of the 2026-11 audit remediation: what changed, why, how it was
verified, and what risk remains open. Newest entries first. Production numbers
come from workflow logs; nothing here contains credentials or hostnames.

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
| Migrations auto-apply to production via `ingest.yml` / `rank.yml` | fixed in workflows (Phase 4); Render's own start/release command unverified |
| Alpha backfill delete+insert churns ~493k rows/run and is non-atomic | fixed (Phase 2, PR #5); awaiting first nightly numbers |
| Price upsert rewrites ~462k unchanged rows/run | fixed (Phase 2, PR #5); awaiting first nightly numbers |
| Adjusted-price seam at the 2y fetch-window edge | open — needs owner decision |
| `rank.yml` logs DB host/user/db name to public Actions logs | steps removed (Phase 5); old logs and password rotation are owner decisions |
