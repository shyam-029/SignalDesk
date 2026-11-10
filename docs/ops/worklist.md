# SignalDesk work list

The single list of remaining work, with one owner (the audit/remediation
session). Phase numbers match `docs/ops/remediation-log.md`, which records
what each finished phase changed and how it was verified.

Rules:

- One branch per item, never pushed or merged without the owner's approval.
- No alpha-score pruning and no removal of historical price bars without
  explicit owner approval.
- No production migrations, deletions or maintenance without explicit
  approval; migrations run only through `migrate.yml`.
- Parallel work uses its own worktree, never the shared checkout.

Legend: `[x]` merged to main · `[~]` in progress · `[ ]` not started ·
`[?]` waiting on an owner decision.

## Ops and reliability

- [x] **0** Working backup: canary can no longer discard the dump (PR #3)
- [x] **1** Read-only storage forensics on manual dispatch (PR #4)
- [x] **2** Stop nightly write churn: no-op upsert guards, atomic alpha backfill (PR #5)
- [ ] **2a** Verify Phase 2 on the first nightly after merge: record the
      inserted / updated / unchanged split in the remediation log
- [x] **3** Storage cap corrected to 1024 MB; alarm at 800 MB; prune-alpha
      needs `--confirm DELETE-ALPHA-HISTORY`, no size gate (PR #6)
- [x] **4** Migrations only via `migrate.yml`; ingest/rank fail fast if the
      schema is behind (PR #6)
- [x] **5** Remove host/user/db diagnostics from `rank.yml` (PR #6)
- [ ] **6** Reclaim index bloat online: `REINDEX CONCURRENTLY
      alpha_scores_pkey` (93.8 MB, 0 scans), drop redundant
      `ix_daily_prices_stock_id` (17.2 MB) and `ix_alpha_scores_symbol`
      (9.0 MB); check Neon headroom first; prod DDL needs approval
- [~] **7** Restore test: `restore-test.yml` restores the newest backup
      artifact into a throwaway Postgres on the runner (no secret, never
      touches production), checks every core table has rows; monthly on the
      2nd and on demand (PR pending)
- [~] **8** Failure alerting: a failed ingest, rank, backup or restore-test
      run opens or updates a GitHub issue (label `ops-alert`) and the next
      success closes it (`ops/ci/alert.sh`, `run-alert.yml`); a daily
      `watchdog.yml` alerts if no ingest succeeded in 30 h (PR pending)
- [~] **9** All 8 workflows checked active on 2026-11-10 (db-probe was
      re-enabled earlier); `watchdog.yml` now alerts daily on any disabled
      workflow (PR pending)
- [ ] **10** Private off-GitHub backup copy (repo is public; artifacts last
      30 days). The monthly restore test is covered by item 7
- [ ] **11** Update the private progress trackers kept outside the repo
      (stale since 2026-09-10)

### Hardening and correctness found in the audit

- [~] **17** Live alpha snapshots are dated by the stock's latest stored bar
      instead of the runner's calendar date (PR pending). The 4,010 existing
      weekend-dated rows are left in place (removing them is a data deletion
      and needs owner approval)
- [ ] **18** `daily_prices.volume` is a 4-byte integer; widen to BIGINT
      before a >2.1B-share day fails a symbol's upsert (migration)
- [~] **19** Drift test: builds a throwaway database from the migrations
      alone and fails CI on any difference from the models (PR pending)
- [~] **20** `restore.yml`: typed `RESTORE-PRODUCTION` confirmation, shares
      the nightly-ingestion concurrency group, no longer prints the database
      user (PR pending)
- [~] **21** Dispatch inputs reach scripts through env, never interpolated:
      `db-forensics.yml`, `migrate.yml` (free-text revision), `restore.yml`,
      `restore-test.yml` (PR pending)
- [ ] **22** Job connections: `NullPool` opens a fresh TLS connection per
      symbol (thousands per night); use a small pool
- [~] **23** `*.dump` added to `.gitignore` (PR pending)
- [ ] **24** Clean up the parallel session's worktrees
      (`signaldesk-ops3`, `signaldesk-ops45`) and their local branches

## Owner decisions

- [x] Render dashboard: the start command is only
      `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (owner confirmed
      2026-11-10). No migration runs on deploy, so Phase 4 is complete.
- [x] Orphan `prune-alpha-recovery` and `db-probe-recovery` workflows
      removed (their 5 runs deleted 2026-11-10; the workflow files exist on
      no branch, so they no longer appear in Actions)
- [x] Old public run logs that showed the database host/user deleted
      (11 `rank.yml` runs, 1 `restore.yml` run; 2026-11-10)
- [x] Neon database password rotated by the owner on 2026-11-10;
      `DATABASE_URL` updated in GitHub Actions (verified: read-only db-probe
      succeeded with it) and in Render (owner confirmed)
- [?] Adjusted-price seam at the 2y fetch edge: store raw prices plus
      adjustment factors, or re-fetch full history after corporate actions
- [?] Storage strategy before fund work: derive backfilled alpha history
      from prices instead of storing it (~110-120 MB), and/or move funds
      to a second database
- [?] News retention policy

## Speed

- [ ] **12** Cold start (likely the 30-40 s first load): `Cache-Control`
      with `s-maxage` + `stale-while-revalidate` on read endpoints, served
      through Cloudflare
- [ ] **13** Nightly static JSON snapshot for the landing page (benchmarks,
      top-50 ticker, a 6-month chart, market news)
- [ ] **14** Screener: server-side pagination (10 per page) instead of
      computing all 1,000 rows per request, and cache it
- [ ] **15** "Too many requests": rate limiter trusts the first
      `X-Forwarded-For` hop (spoofable); trust only Render's proxy hop and
      review the 60/min and 300/min limits
- [ ] **16** Keep-warm ping on `/health`; persist TanStack Query cache to
      `localStorage` for repeat visits

## Product

- [ ] Quick UI fixes: About as a dropdown; remove internal descriptions
      ("543 bars", weights text); industry link goes to the screener, not
      markets; even, ordered market cards; valuation section shows dashes
      instead of going blank when P/B or EBITDA is missing; Ask panel too
      transparent
- [ ] Alpha chart: remove the fundamental/sentiment lines; investigate the
      large technical-score swings
- [ ] News relevance: articles are attached to the wrong stock whenever a
      ticker or company name is also an ordinary word, acronym or another
      organisation's name. This is systemic, not a few cases (owner,
      2026-11-10); examples: ACC (cricket body vs ACC Ltd), "eternal" (the
      word vs ETERNAL.NS). Needs a general matching rule plus a measured
      false-match rate over stored articles, not a per-ticker blocklist
- [ ] Alpha v2 with flexible, lower sentiment weighting
- [ ] Redesign ETF and fund pages (needs holdings data first)

## Suggested order

2a (tonight's nightly) → merge the 7/8/9/20/21/23 PR, then run the
restore test and the watchdog once
→ 12-16 → 6 → 17-23 → product items.
