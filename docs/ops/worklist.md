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
- [x] **2a** Phase 2 verified on the 2026-11-10 run (42852962417): prices
      92.7% unchanged (~33k rows written instead of ~462k), alpha 96.1%
      unchanged (~19k instead of ~987k delete+insert). Details in the
      remediation log
- [x] **2b** `NXT100CASE.NS` failed the catalog repair every night (Yahoo's
      last bar 2026-10-16). Fixed by the Upstox fallback (PR #17): on the
      2026-11-10 nightly (42896037285) Upstox filled 17 days and the night
      was `success`. Remaining open question, not blocking: `POWERIETF.NS`
      and `VEEFIN.NS` have no data on either source (Yahoo 404), and
      `ICICINIFTY.NS` is unknown to Upstox. Decide whether repair should
      skip or retire such instruments
- [x] **2c** First nightly with PRs #10-#17 (42896037285): 65 min instead
      of 123, every pass about half its time (pooling likely; not a
      controlled comparison, so confirm over the next nights); writes
      91.9% / 91.6% unchanged; no Upstox fallback needed in the main price
      pass. Details in the remediation log
- [x] **3** Storage cap corrected to 1024 MB; alarm at 800 MB; prune-alpha
      needs `--confirm DELETE-ALPHA-HISTORY`, no size gate (PR #6)
- [x] **4** Migrations only via `migrate.yml`; ingest/rank fail fast if the
      schema is behind (PR #6)
- [x] **5** Remove host/user/db diagnostics from `rank.yml` (PR #6)
- [ ] **6** Reclaim index bloat online: `REINDEX CONCURRENTLY
      alpha_scores_pkey` (93.8 MB, 0 scans), drop redundant
      `ix_daily_prices_stock_id` (17.2 MB) and `ix_alpha_scores_symbol`
      (9.0 MB); check Neon headroom first; prod DDL needs approval
- [x] **7** Restore test: `restore-test.yml` restores the newest backup
      artifact into a throwaway Postgres on the runner (no secret, never
      touches production), checks every core table has rows; monthly on the
      2nd and on demand (PR #9)
- [x] **8** Failure alerting: a failed ingest, rank, backup or restore-test
      run opens or updates a GitHub issue (label `ops-alert`) and the next
      success closes it (`ops/ci/alert.sh`, `run-alert.yml`); a daily
      `watchdog.yml` alerts if no ingest succeeded in 30 h (PR #9)
- [x] **9** All 8 workflows checked active on 2026-11-10 (db-probe was
      re-enabled earlier); `watchdog.yml` now alerts daily on any disabled
      workflow (PR #9)
- [ ] **10** Private off-GitHub backup copy (repo is public; artifacts last
      30 days). The monthly restore test is covered by item 7
- [ ] **11** Update the private progress trackers kept outside the repo
      (stale since 2026-09-10)

### Hardening and correctness found in the audit

- [x] **17** Live alpha snapshots are dated by the stock's latest stored bar
      instead of the runner's calendar date (PR #11). The 4,010 existing
      weekend-dated rows are left in place (removing them is a data deletion
      and needs owner approval). Not yet seen in production: it only shows
      on a run whose UTC date has no bar (a weekend or post-midnight run)
- [ ] **18** `daily_prices.volume` is a 4-byte integer; widen to BIGINT
      before a >2.1B-share day fails a symbol's upsert (migration)
- [x] **19** Drift test: builds a throwaway database from the migrations
      alone and fails CI on any difference from the models (PR #11). Its
      first run found and fixed one mismatch: the `ranking_audit.stock_id`
      index name in the model
- [x] **20** `restore.yml`: typed `RESTORE-PRODUCTION` confirmation, shares
      the nightly-ingestion concurrency group, no longer prints the database
      user (PR #9)
- [x] **21** Dispatch inputs reach scripts through env, never interpolated:
      `db-forensics.yml`, `migrate.yml` (free-text revision), `restore.yml`,
      `restore-test.yml` (PR #9)
- [x] **22** Job connections: pooled engine (`pool_pre_ping`, recycle
      300 s) instead of `NullPool`'s fresh TLS connection per symbol
      (PR #17). The first night with it ran in 65 min instead of 123
- [x] **23** `*.dump` added to `.gitignore` (PR #9)
- [ ] **24** Clean up the parallel session's worktrees
      (`signaldesk-ops3`, `signaldesk-ops45`) and their local branches

## Render configuration (owner action, found 2026-11-10)

- [ ] Build command installs the full `requirements.txt` (torch,
      transformers, CUDA wheels) instead of `requirements-render.txt`: slow
      builds (about 8 min to deploy PR #15), large image. Set Build Command
      to `pip install -r requirements-render.txt`
- [ ] Render builds on Python 3.14 while CI and all tests use 3.12. Set
      `PYTHON_VERSION=3.12.7` (any 3.12.x), then Manual Deploy
- [ ] Note: cold boot to first `/health` 200 is ~41 s on the free
      instance; `keep-warm.yml` (item 16) avoids it during IST hours

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

- [x] **12** `Cache-Control: public, max-age=60, stale-while-revalidate=300`
      on successful `GET /api/v1/*` (browser cache; errors, POSTs and ops
      routes excluded). Note: the API is called directly on Render, not
      through Cloudflare, so there is no shared edge cache yet; proxying
      `/api` through the Worker with edge caching is a separate, larger
      change (PR #10)
- [ ] **13** Nightly static JSON snapshot for the landing page (benchmarks,
      top-50 ticker, a 6-month chart, market news)
- [x] **14** Screener: the analysed universe is cached in memory and rebuilt
      only when a job finishes (or after 1 h), instead of ~4,000 database
      round trips per request; filter/sort/paging unchanged and identical
      results (PR #10). 10 rows per page with Previous/Next (PR #14)
- [x] **15** Rate limiter keyed on a forgeable header. Measured on
      production (client-ip-probe.yml, 2026-11-10): traffic arrives via
      Cloudflare; a forged X-Forwarded-For becomes its first entry (the
      limiter's old key); CF-Connecting-IP always carries the real caller and
      Cloudflare refuses forged values (403, error 1000). The limiter now
      keys on CF-Connecting-IP (PR #15; verified live: rotating forged
      X-Forwarded-For values now get 429). The 60/min and 300/min limits
      themselves are unchanged
- [x] **16** `keep-warm.yml` pings `/health` and one screener row every
      10 min, 08:00-00:30 IST (~500 of Render's 750 free hours/month); the
      frontend persists successful queries to `localStorage` for 12 h so
      repeat visits render instantly (PR #10)

## Ingest speed

Owner request (2026-11-10): start the nightly right after market close, or
as soon as Yahoo and Upstox have published the day's final values, and make
it shorter. Target: from ~2 h today to ~45-55 min, or ~15-25 min on
weeknights with parallel jobs plus weekly heavy passes. Order: 25 first;
everything that changes the nightly waits for 2a (the post-Phase-2
baseline). Each item touches `ingest.yml` / `jobs.py`, so one branch each.

- [~] **25** Measure first: `bar-publish-probe.yml` records, every 15 min
      from 14:30 to 23:15 IST on weekdays, whether today's bar exists on
      Yahoo and its values, for RELIANCE, TCS, HDFCBANK and ^NSEI. Read-only
      (no database). Collecting since 2026-11-10 (PR #12). Upstox is not
      probed; the `UPSTOX_ANALYTICS_TOKEN` Actions secret now exists, so it
      could be added
- [ ] **26** Event-driven start from 25's results: an earlier cron (about
      16:30 IST = 11:00 UTC, final time from the data) plus a first step that
      polls the sentinels until today's bar exists and is unchanged across
      two reads, with a timeout fallback (run anyway, flag as late). Keep the
      stale-frame and NaN-row guards. The gate must not assume the start
      time (GitHub cron drifts). Item 8's alerting is already in place
- [ ] **27** Incremental price fetch (last ~10 days; full 2y refetch only
      after a detected split/dividend). Depends on the adjusted-price seam
      decision. Biggest saving (~11-19 min to ~4)
- [ ] **28** Batched multi-ticker Yahoo download and a gradual BATCH_SIZE
      increase while watching 429s (related: 22)
- [ ] **29** Tiered schedule: financial periods, balance sheets and profiles
      weekly (plus after earnings season); nightly keeps the price-linked
      passes. Saves ~30 min
- [ ] **30** Weekday-only runs plus an NSE holiday skip (pairs with 17)
- [ ] **31** Independent passes as parallel jobs (check Neon connection
      limits and shared-IP Yahoo throttling first)
- [ ] **32** Alpha: recompute only symbols whose inputs or formula version
      changed (or the derive-on-demand storage decision)
- [ ] **33** News: fetch only articles newer than the last run, skip FinBERT
      for already-scored articles, cache the model between runs
- [ ] **34** Funds on their own schedule after AMFI publishes NAVs (verify
      the publish time with a probe like 25), not tied to the equity run

## Product

- [~] Quick UI fixes (PR pending): "About the company" is a dropdown,
      closed by default; bar counts and the weights text removed; sector and
      industry link to the screener (new `industry` filter); market index
      cards in a fixed order, four per row; the blank valuation section was
      a request loop on a missing multiple (a bank's EV/EBITDA: about 100
      requests a minute, enough to hit the per-IP rate limit), fixed with
      `retryOnMount: false`. Ask panel done in PR #16
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

Done: 2a, 2b, 2c, 12, 14, 15, 16, 22. Next: 25 runs for a week (to about
2026-11-17) → 26-34 in order of saving (re-measure the baseline: the
nightly is now ~65 min, not ~2 h) → 6 → 18 → product items.
