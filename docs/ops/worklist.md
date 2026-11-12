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
      `ICICINIFTY.NS` is unknown to Upstox. Decided 2026-11-12 (owner):
      ICICINIFTY trades as NIFTYIETF now; POWERIETF is retired; VEEFIN
      began trading on NSE on 2026-11-11 and fills itself (PR #29)
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
- [x] **6** Index bloat reclaimed 2026-11-12: migration `9a8b7c6d5e4f`
      (PR #31) rebuilt `alpha_scores_pkey` concurrently and dropped the
      redundant `ix_daily_prices_stock_id` and `ix_alpha_scores_symbol`.
      Applied by `migrate.yml` (run 43185218810) together with item 18
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
- [x] **10** Private off-GitHub backup copy (repo is public; artifacts last
      30 days). The monthly restore test is covered by item 7. Decided
      2026-11-12: Cloudflare R2 (10 GB free, already on Cloudflare, S3
      API, no egress fees). Bucket, bucket-scoped token and the four
      `R2_*` Actions secrets set up by the owner 2026-11-12. The weekly
      `backup.yml` (owner chose weekly: a nightly dump would use about a
      third of Neon's 5 GB/month transfer) copies each verified dump to R2,
      checks the stored size and keeps the newest 12 (PRs #34, #36; the
      artifact uploads first so an R2 failure cannot cost the GitHub copy).
      Verified 2026-11-12: run 43197245738 copied a 58.7 MB dump and read
      its size back.
- [x] **11** Private progress trackers updated 2026-11-12
      (`SEMESTER2_PROGRESS.md` section 17; local, gitignored)

### Hardening and correctness found in the audit

- [x] **17** Live alpha snapshots are dated by the stock's latest stored bar
      instead of the runner's calendar date (PR #11). The 4,010 existing
      weekend-dated rows are left in place (removing them is a data deletion
      and needs owner approval). Not yet seen in production: it only shows
      on a run whose UTC date has no bar (a weekend or post-midnight run)
- [x] **18** `daily_prices.volume` is BIGINT: migration `c3d4e5f6a7b8`
      (PR #19), applied 2026-11-12 (run 43185218810). The table rewrite
      also removed old bloat: database 543 MB -> 399 MB (daily_prices
      206 -> 148 MB, alpha_scores 223 -> 135 MB; read-only probe
      43185624642)
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
- [~] **35** Universe trap (found 2026-11-11): RELIANCE.NS and TCS.NS have
      no price bars after 2026-09-08 and are missing from the ranked
      universe and search; the landing page's preview stock is RELIANCE.
      Cause: the 2026-09-09 rank runs were throttled by Yahoo (no_mcap);
      outside the universe the nightly stops fetching a stock, so its stored
      bars aged past 30 trading days and E9 marked it inactive and
      deactivated it at every later cycle. Fix (PR #23): E9 checks the
      provider's latest bar before calling a stale stock inactive. Then
      needs owner approval: run `rank.yml` once so the trapped stocks
      re-enter (the nightly's 2y refetch fills their gap); count the
      trapped symbols first from `ranking_audit` (`inactive_proxy` rows)
- [x] **24** Removed 2026-11-12 (owner approved): worktrees
      `signaldesk-ops3`, `signaldesk-ops45`, `signaldesk-ask`; local
      branches `docs/verify-ops-runs`, `ops/m2-t1-storage-reclaim` and the
      three worktree branches; remote `backup/pre-attribution-rewrite`

## Render configuration (owner action, found 2026-11-10)

- [x] Build command installs the full `requirements.txt` (torch,
      transformers, CUDA wheels) instead of `requirements-render.txt`: slow
      builds (about 8 min to deploy PR #15), large image. Set Build Command
      to `pip install -r requirements-render.txt`
- [x] Render builds on Python 3.14 while CI and all tests use 3.12. Set
      `PYTHON_VERSION=3.12.7` (any 3.12.x), then Manual Deploy
- [ ] Note: cold boot to first `/health` 200 is ~41 s on the free
      instance; `keep-warm.yml` (item 16) avoids it during IST hours
- [x] Both settings changed by the owner; latest deploy confirmed Live
      2026-11-12. Ask re-tested on the live site the same day (ADANIGREEN:
      answered from computed price facts, high confidence)

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
- [x] Adjusted-price seam (decided 2026-11-12): keep storing Yahoo's
      adjusted prices and re-fetch a symbol's full 2y history when its
      history has been re-adjusted. Detection needs no extra API: the
      incremental fetch (item 27) asks for ~10 days, which overlap stored
      bars; if any overlapping close differs from the stored one by more
      than 0.1%, Yahoo has re-adjusted (split or dividend) and that symbol
      gets a full refetch. Chosen over raw prices + adjustment factors:
      no schema change, every reader keeps reading one adjusted series,
      and only the few symbols with a corporate action pay the full fetch
- [x] Storage strategy (decided 2026-11-12): funds go to a second Neon
      project on the same account, created when fund work (M4/M5) starts.
      Neon's Free plan gives each project its own 100 CU-hours a month and
      1 GB (20 GB per account), so the second project does not eat the main
      one's quota. Create it in the same region as the main project so the
      API's latency to both is the same; fund ingest runs as its own job and
      never slows the equity nightly. Trade-off: no SQL joins between stocks
      and funds ("funds holding this stock" joins in the app by ISIN).
      Deriving alpha history on demand stays the next storage saving, and
      the technical-score recalibration waits for it (below)
- [x] Technical-score sensitivity (decided 2026-11-12, "better for the
      long run"): change it together with alpha v2, after alpha history is
      derived on demand. Changing the formula now rewrites all ~480k stored
      backfilled rows in one night (a churn and bloat spike Phase 2 just
      removed); once history is derived, a formula change is free.
      Direction for v2: EMA span 10 at the current scales (keeps v1.5's use
      of the full 0-100 range; daily max step 10 -> 7)
- [x] News retention: up to 20 articles per stock (owner, 2026-11-12).
      A nightly `prune_news` pass after `ingest_news` keeps each stock's 20
      newest articles that pass the relevance rule and deletes the rest with
      their sentiment rows (PR #30). The first night deletes most of the
      ~63k stored articles (1,000 stocks x 20 = ~20k kept)

## Speed

- [x] **12** `Cache-Control: public, max-age=60, stale-while-revalidate=300`
      on successful `GET /api/v1/*` (browser cache; errors, POSTs and ops
      routes excluded). Note: the API is called directly on Render, not
      through Cloudflare, so there is no shared edge cache yet; proxying
      `/api` through the Worker with edge caching is a separate, larger
      change (PR #10)
- [x] **13** Landing snapshot, both halves (owner, 2026-11-11):
      `GET /api/v1/landing` returns all seven landing queries in one cached
      response (rebuilt when a job finishes), and `landing-snapshot.yml`
      commits it after each successful ingest as
      `frontend/public/snapshot/landing.json`, which Cloudflare serves
      statically; the landing page seeds its query cache from it and then
      refreshes from the API. Market news is not on the landing page, so it
      is not included (PR #20). After merge: dispatch the workflow once
      to create the first file
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
      repeat visits render instantly (PR #10). 2026-11-12: GitHub ran it
      only ~every 8-14 h, so the primary pinger is now a Cloudflare Cron
      Trigger on the frontend Worker (PR #37)
- [ ] **36** Stock-page snapshots (owner, 2026-11-12): after each nightly,
      `stock-snapshots.yml` writes one JSON file per listed stock to the
      private R2 bucket `signaldesk-cache`; the Worker serves
      `/snapshot/stock/<SYMBOL>.json` and the stock page seeds its cache
      from it, so a first-time visitor sees the page at once even while
      Render sleeps. Budget (free long term): ~25 MB R2, ~31k writes/month
      of 1M, ~0.7 GB/month of Neon's 5 GB transfer. The alpha-history and
      technicals-series charts (75% of the bytes) and the LLM explanation
      stay live. Done once a nightly run has filled the bucket

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

- [x] Quick UI fixes (PR #21): "About the company" is a dropdown,
      closed by default; bar counts and the weights text removed; sector and
      industry link to the screener (new `industry` filter); market index
      cards in a fixed order, four per row; the blank valuation section was
      a request loop on a missing multiple (a bank's EV/EBITDA: about 100
      requests a minute, enough to hit the per-IP rate limit), fixed with
      `retryOnMount: false`. Ask panel done in PR #16
- [x] Alpha chart: fundamental/sentiment lines removed (they existed only
      on the few live snapshots) (PR #22). Technical swings
      investigated 2026-11-11: no bug and no day-to-day noise (median daily
      step 1-2 points); the v1.5 calibration (2026-09-08: trend scale 600,
      momentum 4000, EMA span 5) is simply sensitive, so a few percent of
      price trend moves the score 20-36 points within 20 trading days
      (INFY 30 -> 86 in October). Measured on 1y of INFY / HDFCBANK / ITC
      closes, median 20-day range: current 36 / 21 / 20; EMA 10 with the
      same scales 29 / 16 / 16; EMA 10 with half scales (300 / 2000)
      15 / 7 / 7; EMA 20 with half scales 10 / 5 / 5. Halving the scales
      partly undoes v1.5's goal (scores stuck at 40-60). [?] Owner decision:
      keep, EMA 10 only, or EMA 10 + half scales (fold into alpha v2)
- [x] News relevance (PR #24): new general rule (no per-ticker list).
      Strong: the name's distinctive words together in order, or a
      multi-word name's non-generic brand word. Ambiguous (needs a market
      word such as shares, Q2, crore, NSE, results): a one-word name, the
      ticker, the name's initials. Words on 3+ catalog names (bank, india,
      hdfc, tata) never count alone. Applied at ingest and at read time
      (news list and the sentiment that feeds Alpha); stored rows are not
      deleted. Measured 2026-11-11 on 1,173 stored headlines for 30
      ambiguous-name stocks: the rule rejects 360; reading all rejects,
      about 90% were wrong-company (ACC: 47 of 50 were US college sports,
      Bangladesh's Anti-Corruption Commission or the Asian Cricket Council;
      Trent: 46 of 50). In a random 60 of the kept, about 5 are still wrong
      (~8%), against an estimated ~28% under the old rule. Known misses: a
      company headline with no market word ("Eternal founder Deepinder
      Goyal ...")
- [ ] Alpha v2 with flexible, lower sentiment weighting
- [ ] Redesign ETF and fund pages (needs holdings data first)

## Suggested order

Done: 2a, 2b, 2c, 12, 14, 15, 16, 22. Next: 25 runs for a week (to about
2026-11-17) → 26-34 in order of saving (re-measure the baseline: the
nightly is now ~65 min, not ~2 h) → 6 → 18 → product items.
