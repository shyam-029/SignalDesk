# Storage & reliability remediation log

Running record of the 2026-11 audit remediation: what changed, why, how it was
verified, and what risk remains open. Newest entries first. Production numbers
come from workflow logs; nothing here contains credentials or hostnames.

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
| `prune-alpha` gate is armed (uses `pg_database_size`, which includes bloat) | open — Phase 3 |
| Migrations auto-apply to production via `ingest.yml` / `rank.yml` | open — Phase 4 |
| Alpha backfill delete+insert churns ~493k rows/run and is non-atomic | open — Phase 2 |
| Price upsert rewrites ~462k unchanged rows/run | open — Phase 2 |
| Adjusted-price seam at the 2y fetch-window edge | open — needs owner decision |
| `rank.yml` logs DB host/user/db name to public Actions logs | open — Phase 8 |
