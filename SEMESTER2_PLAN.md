# SignalDesk - Semester 2 Master Plan

> **Purpose:** The single authoritative product, architecture, data, ML and zero-cost deployment plan for Semester 2.
> **Status:** Planning revision, 2026-09-08. Implementation of Semester 2 has NOT started.
> **Basis:** Actual repository state at commit `968a44d` (Phase 8 complete, clean tree); full `PLANNING.md` (decisions D1-D98, sections 1-18); full `PROGRESS.md`; complete code inspection; repo-wide bucket-list sweep; free-tier terms verified 2026-09-08 from official provider pages (see Appendix A).
> **Relationship to Semester 1 docs:** `PLANNING.md` and `PROGRESS.md` remain the Semester 1 record and are NOT modified by this file. The full Semester 1 versions are also preserved in git history at and before `968a44d`. Where this plan carries forward a Semester 1 decision it cites the decision ID; where it changes one it says so explicitly.
> **Companion file:** `SEMESTER2_PROGRESS.md` - the Semester 2 operational tracker (resume work there first).

---

## Table of Contents

1. Semester 1 Actual State (verified baseline)
2. Complete Bucket List Reconstruction and Disposition
3. Semester 1 Decisions That Remain Valid (and Decisions Superseded)
4. Semester 2 Product Vision
5. Equity Research Expansion
6. Alpha Score v2
7. Top-1000 Universe Definition (explicit eligibility specification)
8. Mutual Fund Research System
9. ETF System
10. Portfolio, Watchlist and Authentication Architecture
11. ML, Forecasting, Scenario and Backtesting System
12. Comparison Engine
13. Data Source Strategy (NO DALOOPA)
14. Target Data Architecture
15. Target Backend and API Architecture
16. Target Frontend Architecture
17. Real-Time Data Strategy
18. LLM Strategy (strict zero cost)
19. Security Architecture
20. Testing Architecture
21. Zero-Cost Deployment (verified research and recommended architecture)
22. Resource, Storage and Runtime Budgets
23. Semester 2 Dependency Graph
24. Semester 2 Milestones (M1-M8)
25. Prioritization: MUST / SHOULD / COULD / FUTURE
26. Explicitly Rejected and Obsolete Items
27. Semester 2 Definition of Done
28. Deployment Runbook Outline
29. Remaining Human Decisions
30. Recommended First Implementation Task
- Appendix A: verified external facts (2026-09-08)
- Appendix B: Semester 1 engineering standards carried forward

---

## 1. Semester 1 Actual State (verified baseline)

Verified from the repository at `968a44d` (main, clean tree; public repo github.com/shyam-029/SignalDesk). Every claim below was read from code or docs, not assumed.

### 1.1 Repository facts

- HEAD: `968a44d` "Phase 8: security hardening - ops Bearer auth, gated ops/docs, pure-read alpha, per-IP rate limits + LLM concurrency cap (D94-D98)".
- Backend suite: pytest **348/348**, zero-network (dedicated `signaldesk_test` DB). Frontend suite: vitest **72/72**, `tsc -b` clean, `vite build` OK. Coverage about 78 percent.
- No `.github/` workflows exist: there is no CI yet. No `docs/` directory yet. Root holds only `.gitignore`, `LICENSE`, `PLANNING.md`, `PROGRESS.md`, `README.md`.
- **No user authentication anywhere** (Phase 8 decision D94: public read-only research app with operational shared secrets only).

### 1.2 Backend architecture (unchanged going into Semester 2)

FastAPI modular monolith in one process, 13 routers / 11 services / 8 repositories / 7 providers:

```
React frontend  --REST/JSON (/api/v1, error envelope)-->  FastAPI
  routers/        HTTP layer (validation, params, status codes)
  services/       business logic (valuation, scores, alpha, indicators, narratives)
  repositories/   SQL only (async SQLAlchemy 2.0)
  providers/      source adapters (yfinance, upstox, merging facade, RSS, FinBERT, OpenRouter)
  PostgreSQL schema, 7 Alembic migrations
  APScheduler: in-process 18:30 IST nightly job (production replaces this with GitHub Actions cron per D79)
```

Layering rule preserved: services testable without DB or network; providers swappable behind interfaces; routers thin.

### 1.3 Database schema at end of Semester 1

| Table | Contents |
|---|---|
| `stocks` | symbol (with `.NS`), name, sector, industry; catalog can exceed the active universe |
| `universes` / `stock_universe` | named universes (`nifty50`, `nifty100`, `nifty250`) + many-to-many membership; composite PK |
| `daily_prices` | OHLCV; surrogate `id` PK + `UNIQUE(stock_id, date)`; `Numeric(16,4)` |
| `financials` | one point-in-time snapshot per stock: market cap, trailing P/E, EV, EBITDA, P/B, P/S, ROE, ROA, operating/net margin, D/E, interest coverage, current ratio; `UNIQUE(stock_id)` |
| `company_profiles` | provider business summary stored verbatim, CEO, employees, website, source |
| `financial_periods` | **income-statement only**: annual + quarterly (revenue, net income, margins computed backend-side, EPS, source); `UNIQUE(stock_id, period_end, period_type)` |
| `news_articles` / `news_sentiment` | URL-deduplicated articles; FinBERT score/label/model (1:1) |
| `alpha_scores` | daily snapshots: fundamental/technical/sentiment/composite + `components_json` JSONB; `UNIQUE(symbol, date)`; about 120k rows for 251 stocks |
| `job_runs` | one row per ingestion pass (running/success/partial/failed, timings, counts, truncated error summary) |

### 1.4 Providers and ingestion

- `yfinance` PRIMARY + `Upstox` SECONDARY behind `MergingProvider`: primary wins same-date/field collisions, secondary gap-fills, per-bar/per-row source attribution, 5 percent material-disagreement logging (never credentials).
- Upstox uses a manually generated "Analytics Token" (Bearer, read-only v2 APIs, server-side only). The token **expires and must be regenerated by a human**: an operational risk carried into the runbook (section 28).
- Nine recorded ingestion passes: `ingest_prices`, `ingest_financials`, `ingest_financial_periods`, `ingest_company_profiles`, `repair_catalog_gaps`, `backfill_alpha_history`, `record_live_alpha_snapshots`, `prewarm_alpha_explanations`, `ingest_news`. Batched, resumable, per-symbol isolation (D19).
- Universe: Nifty 250 from official NSE index lists, seeded as data (D16/D64). 251 catalog stocks, about 122k daily bars (2y). Verified 2026-09-06: 250/250 priced to the last trading day, 0 duplicates, 2,720 income periods, 4,769+ articles.
- News: Google News RSS (name-first query, symbol fallback) through a relevance filter, 60-day window; FinBERT scored at ingestion only, never in request paths.

### 1.5 Research API surface (Semester 1 final)

Under `/api/v1`: `/stocks` (list with nulls-not-zeros, pagination, sector/sort), `/stocks/{s}` (detail + quote + market cap), `/prices`, `/technicals` (+ `/technicals/series`), `/fundamentals` (key ratios), `/scores`, `/valuation` (+ per-metric medians, `/explanation`), `/screener`, `/news`, `/sentiment` (nulls when no scored articles), `/alpha` (pure read) + `/alpha/explanation` (`source: llm|rule_based`) + `/alpha/history`, `/performance` (windowed returns, 52w range, 1y volatility), `/peers`, `/financials/history` (annual/quarterly + backend-derived half-yearly/3-yearly groups), `/profile`, `POST /explain` (5 fixed question types), `POST /ask` (evidence-only single-shot Q&A).
Operational (gated): `/health` liveness; `/status` public minimal + `/status/full` behind key; `/debug/jobs` behind key; `/docs` disabled in production.

### 1.6 Alpha Score (Semester 1)

Composite = 40 percent fundamental + 30 percent technical + 30 percent sentiment, weights renormalized over available components, bounded 0-100; valuation kept separate as `value_signal` (avoids double-counting fundamentals).
Fundamental pillar uses the fixed-threshold piecewise-linear methodology (section 6 baseline in section 6 of this plan); technical pillar is trend 50 / momentum 30 / reversion 20 with EMA(5) smoothing; sentiment pillar maps the news aggregate -1..+1 to 0..100. Historical composites hold the latest known fundamental and sentiment constant across the window (slow-moving point-in-time metrics) while technical scores are real per-day math; component lines are stored only where genuine snapshots exist.

### 1.7 LLM architecture (Semester 1)

OpenRouter via raw async httpx behind an `LLMProvider` ABC. Per-surface allow-listed fact serialization (never ORM dicts); strict output contracts; rule-based fallback on every path; in-process TTL caches; one shared daily cap (300); semaphore (3 concurrent provider calls); per-IP LLM bucket 20/min. Note: the nightly explanation pre-warm (about 250 calls) is REMOVED by this plan's LLM strategy (section 18).

### 1.8 Observability, security, frontend (Semester 1, carried forward)

- Structured `key=value` logging with request id; `job_runs` durable history; `/health` vs `/status` semantics; freshness classifier (prices 3d, fundamentals 30d, news 60d, alpha 2d); one error envelope on every path including FastAPI-native errors; ops Bearer auth fail-closed in production; pure-read `/alpha`; per-IP rate limits with 429 envelope + Retry-After; CORS and LLM-URL production guards. All in-process only; no Redis.
- Frontend: Vite + React 19 + strict TS, Tailwind v4, Radix, TanStack Query/Table, Router, Framer Motion, Lightweight Charts v5, self-hosted fonts; lazy route chunks; pages: landing, markets, screener, stock research, methodology. DataState discipline (loading/empty/insufficient/stale/error/unknown-symbol), METRIC_INFO registry, no fabricated values, no client-side financial math. Design system frozen by D49-D55 (copy discipline, typography floors, two approved themes, motion budget).

### 1.9 Known data gaps at end of Semester 1 (verified)

Interest coverage: 0/251 stocks have it. D/E missing for about 24 banks. EV/EBITDA absolutes missing about 41 stocks. ROE/ROA missing about 61 stocks (mostly Financial Services). yfinance `.info` defects confirmed (e.g. INFY P/S 225.5x, EBITDA off about 10x); mitigated by Upstox coalesce, never by estimation.
Structurally absent: **balance sheets and cash flows are not stored at all**; no dividends, no earnings dates or estimates, no ownership data, no benchmark data, no weekly/monthly resample, no ETF/MF data (skeleton table names only, no schemas, no routes), no auth, no accounts.

---

## 2. Complete Bucket List Reconstruction and Disposition

Every deferred idea found in the repository (PLANNING sections 2, 14, 15, 18 and D92 taxonomy; README roadmap; config placeholders; PROGRESS gotchas), preserved before filtering. "Semester 2" here means committed by this plan; details in sections 24-26.

| # | Original idea | Source | Current status | Disposition |
|---|---|---|---|---|
| 1 | Multi-stock comparison (up to 5) | D92, README | Planned, not started | **MUST** (section 12) |
| 2 | Mutual funds: research, screener, NAV history, holdings, stock-to-fund holders, overlap, SIP/lumpsum/SWP | D38, D92, section 18, section 6 stretch tables | Stub table names only, never implemented | **MUST** (section 8, core product vision) |
| 3 | Fund overlap engine | sections 2, 18 | Planned, not started | **MUST** (section 8.5) |
| 4 | Three.js holdings graph | section 4 stack, section 18 | Gated on MF data | Overlap first; 3D is **COULD** |
| 5 | ETFs: research, screener, constituents, tracking | D38, D92 | Planned, not started | **SHOULD** (section 9) |
| 6 | DCF / intrinsic valuation | D3, roadmap, section 18 | Deferred from v1 on purpose | **COULD**, only if balance-sheet/cash-flow data proves sufficient (section 5.7); no assumption theater |
| 7 | Backtesting / signal validation (forward returns, Alpha hit-rate) | D92, section 18 | `alpha_scores` history exists as seed data | **MUST** framework (section 11.2) |
| 8 | ML forecasting / scenario analysis | README deferred, D92 exploratory | No methodology defined | **SHOULD**, bootstrap/Monte Carlo only after honest evaluation (section 11.1) |
| 9 | PDF research reports | D92 | Not started | **COULD** |
| 10 | Bull/base/bear scenarios | D92 exploratory | Methodology undefined | **FUTURE** |
| 11 | Portfolio simulation / paper trading | D92 deferred | Needs auth | Portfolio tracking **SHOULD**; paper trading **FUTURE** |
| 12 | Watchlists + authentication | D92, D94 | Deliberately absent | **MUST**, account-backed (section 10) |
| 13 | Service split + RabbitMQ + Docker | old section 14 "Semester 2" | Superseded by D79 decoupling | **REJECTED as obsolete** (section 26) |
| 14 | CI/CD on GitHub Actions | sections 12, 14 | `.github/` does not exist | **MUST** |
| 15 | Monitoring / hosted dashboards | section 14 | Observability shipped S1; hosted dashboards absent | **COULD** (logs + uptime ping suffice) |
| 16 | Redis caching / persistent LLM telemetry | D7, D20, D39, D97 | Deliberately deferred, conditional | **REJECTED for S2** (single free instance; in-process adequate) |
| 17 | Live prices / Finnhub WebSocket | roadmap, dead `finnhub_api_key` config | Deferred | Polling only; Finnhub WS does not cover NSE free (section 17, **COULD**) |
| 18 | NL screener (LLM function calling) | roadmap, D39 | Stretch | **COULD** |
| 19 | Aggregate `/overview` endpoint | D38, D92 | Tracked, never needed | **COULD** |
| 20 | Screener precompute job | D38 | Tracked | **SHOULD** at 1000 stocks |
| 21 | Corporate actions / dividends data infrastructure | D92 | Not started | **MUST** (feeds dividend research) |
| 22 | MF disclosures + fund-house holdings infrastructure | D92 | Not started | **MUST** (riskiest data dependency) |
| 23 | ETF constituents / TER / AUM sources | D92 | Not started | **SHOULD** |
| 24 | Industry / sector index sets ("before Nifty-500") | section 18 | Tracked | **SHOULD** (sector-relative valuation needs them) |
| 25 | Stale-data fallback serving (failsafe 2) | error-handling section | Partially shipped (stale flags) | Close remainder as **COULD** |
| 26 | Weekly/monthly price resample | PROGRESS gotcha | v1 is 1d-only | **COULD** |
| 27 | Real logo CDN (replaces monogram discs) | D69 | Deliberately deferred | **COULD** |
| 28 | Historical financial trends | section 18 stretch | **Shipped S1** (Phase 6.5E) | OBSOLETE as backlog (done) |
| 29 | Structured risk engine | section 18 stretch | Not started | **SHOULD** (section 5.13) |
| 30 | Earnings / event timeline | section 18 stretch | Needs event provider | **COULD** (earnings dates where free) |
| 31 | Earnings-call transcripts | New in S2 scope | No legitimate free source exists | **FUTURE**; explicit alternatives committed (section 5.10) |
| 32 | Ownership / promoter / FII-DII | New in S2 scope | yfinance mostly empty for India; exchange shareholding data is scraping-gray | **COULD** with honest gaps (section 5.12, 14) |
| 33 | Universe to Nifty 500 ladder | section 3 | Designed for, not built | Superseded by top-1000 market-cap ranking (section 7) |
| 34 | Authentication | D94 | Explicitly arrives with portfolio features | **MUST**, account-backed (section 10) |
| 35 | Daloopa as anything | External workspace only | **Zero presence in this repo** (verified by grep) | **REJECTED, permanent exclusion** (section 13). The `investing/daloopa_docs` workspace is an unrelated project and stays excluded. |

Small preserved items not lost: `OPENROUTER_API_KEY` alias discipline, seed/prune universe maintenance, methodology pages per score/model, screener server-side sorting (already shipped), `/stocks` query-count guard (keep green at 1000 rows).

---

## 3. Semester 1 Decisions That Remain Valid (and Decisions Superseded)

### 3.1 Decisions that remain valid and operative in Semester 2

| ID | Content | Semester 2 relevance |
|---|---|---|
| D1-D4 | India-only, fundamentals-first analyzer; relative valuation first; valuation separate from Alpha | Product identity unchanged |
| D16 | Universe is data, not code (`universes` + `stock_universe`) | Top-1000 is rows, not code |
| D18 | Peer selection industry-keyed and universe-independent | Catalog may exceed the active 1000 without touching valuation code |
| D19 | Ingestion batched, resumable, per-symbol isolation | The 1000-symbol pipeline depends on it |
| D24-D26 | Schema conventions: surrogate PK + named unique upsert anchors, async Alembic, association-table many-to-many | All new tables follow |
| D28 | Provider ABC; ingestion depends on interfaces | New data types arrive as optional provider capabilities (D56 pattern) |
| D32 | `financials` is a point-in-time snapshot; scoring renormalizes over missing fields | Unchanged |
| D56-D60 | MergingProvider semantics (primary-wins, coalesce, gap-fill, attribution); news relevance filter | Balance sheet / cash flow / dividend ingestion reuses the pattern |
| D64 | NSE taxonomy seeding; idempotent universe maintenance with pruning | Ranking pipeline extends it |
| D65 | Valuation multiple fallback via pre-computed provider ratios | Unchanged |
| D71/D81 | Alpha history is a real blend; no carried-forward component pseudo-history | Alpha v2 inherits |
| D72 | Technical score EMA(5) smoothing; scalar equals last series entry | Unchanged |
| D75/D76 | `/ask` evidence-only architecture; untrusted-question handling; OpenRouter guardrail mapping | Extends to funds (section 18) |
| D79 | Deployment decoupled from the API process: static frontend + sleep-tolerant API + autosuspend Postgres + GitHub Actions cron | **The Semester 2 deployment architecture** (section 21) |
| D82 | Symbol aliases for renames (TATAMOTORS to TMPV); documented irreducible both-provider gaps | Top-1000 eligibility rules extend it (section 7) |
| D84 | Company profiles stored verbatim, never generated | Unchanged |
| D85-D93 | `job_runs` durability, scheduler semantics, no silent exception paths, `/health` vs `/status`, freshness TTLs, one error envelope, audit fixes | Unchanged |
| D95-D98 | Ops auth fail-closed, docs off in prod, pure-read `/alpha`, rate limits, CORS/LLM-URL guards | Unchanged; extended by section 19 |
| D40-D55 | Frontend stack, design tokens, DataState discipline, METRIC_INFO, copy discipline, typography/palette/motion freezes | Semester 2 frontend extends, never redesigns |

### 3.2 Decisions explicitly superseded or completed

| Decision | Disposition |
|---|---|
| D94 "No user authentication" | **SUPERSEDED for Semester 2 workspace functionality** (section 10). Account-backed auth arrives with watchlists and portfolios. The public research API stays anonymous; the ops-auth portions (D95-D98) remain fully in force. This supersession is deliberate and recorded here so no future session reverts it silently. |
| D83 nightly LLM explanation pre-warm (`LLM_DAILY_CAP=300` sized for about 250 pre-warm calls) | **SUPERSEDED** by the Semester 2 LLM strategy (section 18): on-demand only, strict daily cap sized to the verified free tier. No nightly bulk LLM pre-warming. Rule-based narratives remain the default. |
| D17 universe ladder Nifty 50 to 200 to 500 | **SUPERSEDED** by the top-1000 market-cap-ranked universe (section 7). |
| Old roadmap table (Semester 1 phases) | Complete (Phases 1-8). Historical record only. |
| Old scope cuts | Re-evaluated in section 26 (e.g. "backtest page DEFER" is now MUST; "real-time DEFER" stays deferred with reasons). |
| Old four-tier taxonomy (D38/D92) | Consumed by section 2 (bucket list) and section 25 (MoSCoW). Not carried forward as a parallel system. |

---

## 4. Semester 2 Product Vision

SignalDesk becomes a comprehensive Indian equity and mutual fund research platform: research a stock like an analyst, compare funds like a portfolio manager, and test every idea against history.

### 4.1 Target users

1. The author (interview artifact demonstrating product, data, ML and deployment judgment).
2. Indian retail investors doing self-directed research on equities and funds.
3. Recruiters evaluating engineering depth.

### 4.2 Core workflows (each must be end-to-end usable at close)

- **Research (stock):** company to business to statements to quality to growth to cash flow to valuation to dividends to earnings to news/sentiment to technical positioning to risks to overall conclusion (section 5; page design section 16).
- **Discovery:** markets overview, stock screener, fund screener, ETF screener, sector views.
- **Comparison:** stock vs stock (up to 5), fund vs fund, overlap of fund baskets (section 12).
- **Historical analysis:** financial trends, rolling returns, drawdown explorer, Alpha hit-rate backtest.
- **Scenario and forecasting (funds first):** goal simulator, empirical bootstrap/Monte Carlo, explicit uncertainty (section 11).
- **Portfolio and watchlist:** account-backed watchlists, holdings portfolios with performance, risk and overlap (section 10).

### 4.3 What makes Semester 2 materially better than Semester 1

Four times the universe (250 to 1000, ranked); full three-statement research (Semester 1 stored income only); dividends and earnings sections; a versioned multi-pillar Alpha Score with cash-flow quality; an entire second product domain (funds plus ETFs); an account-backed workspace; a scenario lab with backtesting discipline; and real production deployment at zero ongoing cost.

---

## 5. Equity Research Expansion

Design rule for this section: every subsection names its data source from the providers that exist today (section 13), states a feasibility verdict, and ships honest absence where free data cannot support it. Nothing is added because it sounds sophisticated.

### 5.1 Company overview

Extend the existing `company_profiles` surface (About box): sector/industry, market cap, shares outstanding where supplied. Business segments and geographic exposure are NOT available from free providers: they ship as documented absence, not as invented text. Verdict: MUST (enrichment only).

### 5.2 Price and market data

Existing `daily_prices` plus: beta vs Nifty 50 (`^NSEI`) and vs the stock's sector index where a free index symbol exists; drawdown series and maximum drawdown; relative-performance lines (stock vs benchmark vs sector median); 52-week metrics (already shipped: keep); volume trend and liquidity proxy. All backend-computed. Verdict: MUST.

### 5.3 Income statement (extend, do not rebuild)

`financial_periods` gains columns the providers already supply but the schema drops today: EBITDA, EBIT, other income, interest, depreciation, tax, diluted EPS. Annual + quarterly retained; backend-derived half-yearly/3-yearly grouping unchanged. TTM views computed backend-side from quarterly rows. Verdict: MUST.

### 5.4 Balance sheet (new, explicit design)

New `balance_sheet_periods` table fed by yfinance `balance_sheet` plus the Upstox balance-sheet API (the Upstox statements path is already proven for income; same adapter pattern).
Stored, all nullable: cash and equivalents, investments, receivables, inventory, current assets, total assets, short-term debt, long-term debt, current liabilities, total liabilities, shareholders' equity; `source` per row; `ingested_at` per row.
Derived backend-side only: net debt, working capital, debt/equity cross-check, asset turnover (revenue/total assets), equity growth, debt trajectory over time. The balance-sheet identity (assets = liabilities + equity) is validated by data-validation tests with a tolerance where both sides are present; failures flag data quality, never block the page.
Honest limit: banks and NBFCs report non-standard formats; D/E stays null there as today rather than estimated. Verdict: **MUST**.

### 5.5 Cash flow (new, explicit design)

New `cash_flow_periods` table: operating/investing/financing cash flow, capex, dividends paid where reported. Free cash flow is derived (CFO minus capex), never stored. Backend-derived: FCF margin, CFO/PAT (cash conversion), multi-year trends.
Red-flag diagnostics computed as **flags, never verdicts**: earnings without cash (persistent NI > CFO divergence), rising receivables vs revenue, persistent negative FCF, debt-funded growth (rising debt alongside capex with weak CFO). Each flag carries its inputs and a plain-language limitation note; none is presented as a fraud or failure conclusion. Verdict: **MUST**.

### 5.6 Profitability and quality

Derived from statements: ROE with DuPont decomposition (margin x turnover x leverage) where inputs exist; ROIC only where interest and clean invested-capital inputs exist (interest expense is a documented gap: ROIC ships as honest null rather than approximate); margin stability (5y standard deviation); capital efficiency; earnings quality via cash conversion. Verdict: MUST (with the ROIC caveat documented in the UI).

### 5.7 Valuation (beyond relative multiples)

Keep the four relative multiples as the core. Add: historical valuation percentile (needs price history + TTM EPS history, both computable in-house); sector-relative medians (needs the sector index sets of bucket item 24); FCF yield where cash-flow data exists; dividend yield; PEG only where a defensible growth rate exists (never on one noisy year).
**DCF stance (explicit):** DCF is COULD, not MUST. It ships only if the 5-year statement history plus clean FCF prove sufficient in the data audit, with WACC/growth/terminal assumptions shown and sensitivity ranges. If the data does not support it, it is rejected with the reason recorded. No assumption theater. Verdict: extensions MUST; DCF conditional.

### 5.8 Dividends (new, comprehensive)

New `dividends` table fed by yfinance dividend/split series plus info fields: ex-date, amount per share, kind (regular/special where the provider distinguishes; otherwise `unspecified`, never guessed). History, DPS trend, yield, payout ratio, dividend CAGR, consistency streaks, cash-flow coverage of dividends (dividends paid vs CFO/FCF), ex-date calendar where the provider supplies dates. Announced vs historical dividends are distinguished: the system records what providers report; it does not invent a declaration calendar. Verdict: **MUST**.

### 5.9 Earnings and events

Quarterly rows (already stored) plus yfinance `earnings_dates` (estimate vs actual EPS where present; patchy for India, so honest gaps). Earnings-per-quarter growth, margin changes quarter over quarter, surprise direction where estimate and actual both exist. Corporate-action adjustments ride the existing price pipeline. Verdict: MUST (best-effort on estimates).

### 5.10 Earnings calls and management commentary: limitations and alternatives

Adjudicated fact: **no legitimate free source of Indian earnings-call transcripts exists** that SignalDesk can rely on at zero cost. Transcript pipelines are therefore FUTURE, not Semester 2. The committed alternatives:
1. Company-site report links (annual reports, investor presentations) stored as provider/company-sourced URLs, never scraped without review.
2. News-based commentary through the existing relevance pipeline (management statements quoted in press appear as evidence).
3. LLM summarization restricted to stored evidence (sections 18, 20): summaries of what the database holds, with quarter-over-quarter change detection, tone notes and guidance extraction performed on stored text only.
No transcript provider is invented. If a free legitimate source emerges, it enters as an optional provider capability with provenance. Verdict: alternatives MUST; transcripts FUTURE.

### 5.11 Annual reports and filings research

BSE/NSE announcement and filing ingestion is NOT committed: exchange scraping is terms-of-service gray and format-heavy. Committed: curated outbound links to company disclosures; document ingestion only where a legitimate free source is available and reviewed. Verdict: COULD, gated on source review.

### 5.12 Ownership

yfinance holder fields are mostly empty for Indian listings; NSE/BSE shareholding-pattern disclosures are the authoritative source but automated collection is scraping-gray. Verdict: COULD with honest gaps; any promoter/FII/DII fields shown only when a reviewed source supplies them; collection approach requires human/legal review before implementation (section 29).

### 5.13 Risk analysis (new structured section)

Computed from data the system holds: leverage (D/E trajectory), liquidity (current ratio), interest coverage (when present), earnings volatility (std of quarterly net-income growth), maximum drawdown, valuation risk (historical percentile), concentration/sector cyclicality notes from peer context, and data-quality flags (thin history, provider gaps). Each risk row shows inputs, thresholds and limitations. Verdict: **MUST**.

### 5.14 Peer analysis (expanded)

Extend the peers table with growth (revenue CAGR), ROE, margins, D/E, all four valuation multiples, and 1-year return. A comparability note documents which metrics are meaningful cross-sector (returns, valuation dispersion) and which are not (margins across sectors). Verdict: MUST.

### 5.15 Technical analysis (research-oriented, unchanged in spirit)

Add 52-week position, volume trend, and the drawdown chart. Keep the heuristic disclaimer. No trading signals, no buy/sell labels: the product stays a research platform, not a signal casino. Verdict: MUST (incremental).

---

## 6. Alpha Score v2 (better calculation with more data)

### 6.1 Semester 1 methodology (live baseline, preserved until v2 lands)

Fixed-threshold piecewise-linear mapping: `score = 100 x clamp((value - F) / (C - F), 0, 1)` for higher-is-better; mirrored for lower-is-better. Profitability = ROE 40 / ROA 20 / operating margin 20 / net margin 20. Solvency = D/E 50 / interest coverage 30 / current ratio 20. Missing components drop with weight renormalization; all-missing yields `None` with `insufficient_data`. Thresholds: ROE 0-20, ROA 0-12, operating margin 0-25, net margin 0-20, D/E 50-200, interest coverage 1x-5x, current ratio 0.5x-2x. Composite 40/30/30 fundamental/technical/sentiment. This table stays the executable contract (it is implemented in `services/scores.py` and pinned by tests) until v2 is specified, implemented and backfilled.

### 6.2 v2 design

The fundamental pillar becomes three documented sub-pillars fed by the new statements: **Quality** (ROE/ROA/margins plus cash conversion CFO/PAT and FCF margin), **Growth** (revenue and EPS CAGR over 3y, margin direction), **Solvency** (D/E trajectory, interest coverage where present, current ratio, net-debt trend). Technical and sentiment pillars carry over unchanged.
Every pillar and sub-pillar ships with: methodology text, input list, limitations, data-freshness stamp, and version. Snapshots record the score version; `components_json` already carries breakdowns. Valuation remains the separate `value_signal`: no blending of multiples into the composite (D4 rationale stands). No score is added without all four of methodology, inputs, limitations and freshness; the methodology page is extended for every new number. Verdict: **MUST**, sequenced after balance-sheet/cash-flow ingestion lands (dependency graph, section 23).

---

## 7. Top-1000 Universe Definition (explicit eligibility specification)

"Top 1000" means the 1,000 largest eligible NSE-listed ordinary equity securities by market capitalization, ranked from provider data and stored as a DB-driven universe (D16), refreshed by a monthly ranking job. The catalog may hold more than 1000 stocks (peer selection is industry-keyed and universe-independent per D18); the **active universe** used for nightly ingestion is the ranked 1000.

No silently invented provider rule. Where free data cannot determine something exactly, the limitation is documented and the most defensible deterministic rule is applied:

| # | Case | Deterministic rule |
|---|---|---|
| E1 | Instrument class | Ordinary equity shares only. NSE securities master `EQUITY_L.csv` SERIES `EQ` is eligible; `BE`/`BZ` (ordinary equity in trade-to-trade or surveillance segments) are eligible but flagged `restricted_segment`. Everything else is excluded. |
| E2 | ETFs | Excluded from the equity ranking entirely. ETFs live in the ETF catalog domain (section 9) with their own metadata. |
| E3 | Mutual funds | A separate domain (section 8). Never ranked in the equity universe. |
| E4 | Preference shares, warrants, rights entitlements, partly-paid shares, debentures/bonds, REITs/InvITs | Excluded: not ordinary equity. Determined from the NSE series/instrument class, not guessed from names. |
| E5 | Duplicate or alternate listings | One catalog entry per ISIN. The symbol is the current NSE trading symbol; renames resolve through the `SYMBOL_ALIASES` map (extends D82; e.g. TATAMOTORS to TMPV). |
| E6 | Market-cap ranking source | Provider market cap (yfinance `marketCap`): the only free source with broad NSE coverage. **Documented limitation:** Upstox supplies no market cap (verified in the Semester 1 data-quality findings), so ranking cannot be cross-checked against a second free provider; Yahoo market cap may lag and is occasionally missing for small caps. |
| E7 | Missing market-cap data | Excluded from the ranked universe for that cycle; recorded in the candidate audit table with reason `no_mcap`; retried next cycle. Never estimated. |
| E8 | Newly listed securities (IPOs) | Eligible immediately if all other rules pass and the provider supplies market cap and prices; flagged `recent_listing`. Short history surfaces the standard `insufficient_data` states. |
| E9 | Suspended securities | Free data cannot reliably detect suspension: **documented limitation**. Deterministic proxy: no daily bar for more than 30 consecutive trading days means exclusion from the ranked universe with reason `inactive_proxy`; the catalog row is retained. |
| E10 | Delisted securities | Never deleted: `active=false` with reason and date recorded; full history retained so backtests stay survivorship-bias-free (section 11). |
| E11 | Renames and corporate actions | Alias map (D82 pattern) plus corporate-action ingestion (dividends, splits) where providers supply them; unhandled renames surface through the existing `repair_catalog_gaps` pass. |
| E12 | Derivatives (F&O) | Out of product scope (D2). |

Ranking pipeline: a monthly GitHub Actions job reads the NSE master plus provider market caps, applies rules E1-E12, writes the ranked universe and per-symbol audit reasons, and the nightly ingestion reads the active universe from the database. Re-ranking never deletes catalog rows. Feasibility: universe expansion is rows, not code; the binding constraints are ingestion runtime and database size (section 22), not architecture.

---

## 8. Mutual Fund Research System (first-class product, core vision)

Mutual funds are a first-class research domain with their own tables (section 14), endpoints (section 15) and pages (section 16). Data honesty rules apply unchanged: curated universe where full coverage is unaffordable, honest absence where disclosures are missing.

### 8.1 Fund profile

AMC, scheme type, category and sub-category, benchmark, inception date, option and plan (direct/regular, growth/IDCW), fund manager and tenure where the disclosure supplies them. AUM, expense ratio, exit load and minimum investment shown only where reliably published; otherwise honest nulls. Verdict: MUST.

### 8.2 Performance

1M/3M/6M/1Y/3Y/5Y CAGR where NAV history supports it (default 3y window on the free database; 5y for the top funds by AUM), rolling-return distributions, calendar-year returns, benchmark comparison and category comparison. Precomputed nightly as monthly-granularity metric rows (section 14), never computed in-request at scale. Verdict: MUST.

### 8.3 Risk

Standard deviation, downside deviation, maximum drawdown, Sharpe, Sortino, beta and alpha vs the assigned benchmark, tracking error where an index benchmark exists, upside/downside capture, consistency score (fraction of rolling windows beating benchmark/category). All precomputed; methodology documented per metric. Verdict: MUST.

### 8.4 Holdings

Fund-house monthly portfolio disclosures, Excel/CSV first and PDF later (section 13), stored as `mf_holdings`: top holdings, sector allocation, market-cap allocation, concentration (top-10 share, Herfindahl proxy), turnover proxy from month-to-month changes. Retention: latest plus quarterly snapshots; monthly files older than one quarter are summarized, not kept row-level (storage budget, section 22). Verdict: MUST (Excel-first).

### 8.5 Holdings overlap engine (explicit design)

A pure service over `mf_holdings`, no new schema: pairwise overlap for Fund A vs B, N-fund baskets, and whole-portfolio overlap. Outputs: common holdings with weights on both sides; overlap percentage with the exact definition surfaced in the UI ("share of fund A's weight also held by fund B", directional, plus the symmetric variant); weighted overlap; sector overlap; concentration impact of the duplicated exposure. Property-tested: symmetry of the symmetric variant, [0,1] bounds, known small cases reproducible by hand on three documented fund pairs as the definition of done. Verdict: **MUST**.

### 8.6 Style and factor exposure (honest limits)

Only what holdings data supports: size tilt from market-cap distribution, sector concentration, style proxy from holdings P/E mix where the catalog join exists. **No factor model is claimed unless the data supports it**; factor drift is reported as an observed allocation change, not as a model output. Verdict: SHOULD within those bounds; full factor models are FUTURE.

### 8.7 Fund manager analysis

Tenure, performance during tenure, consistency, drawdowns and style consistency, benchmark/category-relative performance: only where disclosure data is obtainable. No invented tenure data. If manager history cannot be sourced reliably, this subsection ships as documented absence. Verdict: SHOULD, gated on source audit.

### 8.8 Portfolio construction tools

Compare funds; build a hypothetical weighted basket; compute historical basket returns, volatility, drawdown, benchmark comparison, and overlap-aware diversification notes. Explicitly framed as **analytical simulation, not individualized investment advice**; disclaimers plus the human/legal review flag (sections 19, 29). Verdict: SHOULD.

### 8.9 Other fund tools (assessed, not auto-included)

Fund screener MUST. Rolling-return explorer SHOULD. Drawdown and recovery-time explorer SHOULD. SIP and lump-sum simulators MUST (they are deterministic arithmetic on stored NAV, the cheapest high-value tools). Goal simulator MUST (section 11.3). Diversification, benchmark-relative and concentration analyzers SHOULD. Expense-ratio impact calculator SHOULD. "What happened during past crashes" episode explorer SHOULD. Regime analysis, style-drift detector, manager-change analysis, downside-resilience score COULD. Tax-aware calculations FUTURE (legal and data review required first).

---

## 9. ETF System

ETFs enter the equity catalog flagged (`is_etf`) and reuse the entire equity pipeline (prices, technicals, performance, risk), plus `etf_metadata` (fund house, underlying index, TER, AUM) from AMC/NSE-published data where reliably free. Features: ETF screener, ETF detail, price/NAV performance, tracking difference vs the underlying index where a free index symbol exists, risk via the shared analytics, and overlap with funds through the same engine. Constituents for broad ETFs come from the index lists already proven in D64. Anything without a clean free source ships as honest absence. Verdict: SHOULD, sequenced after fund analytics exist to reuse.

---

## 10. Portfolio, Watchlist and Authentication Architecture

Semester 2 includes account-backed user functionality. D94's no-auth posture is superseded for workspace functionality only (section 3.2); the public research API stays anonymous.

### 10.1 Architecture rules (all mandatory)

- Public research pages remain anonymously accessible. Login is required only for user-specific workspace functionality.
- Account-backed watchlists (symbols and funds) and account-backed portfolios (holdings with quantity, average cost, date; current value, P&L, allocation, time-weighted returns, volatility, drawdown, whole-book fund overlap).
- User notes and preferences where justified (research notes on holdings; display preferences). Minimal PII: email plus password hash only.
- Secure server-side sessions. **No JWT in localStorage.** Session cookie is httpOnly, Secure, SameSite=Lax; sessions revocable server-side.
- Argon2id password hashing (`argon2-cffi`), minimum password length, enumeration-safe login errors.
- Rate-limited authentication routes (stricter than the LLM bucket), plus the Phase 8 adversarial test style extended to auth (section 20).
- User-data scoping tests: every workspace query filtered by session user, proven by tests that attempt cross-user access.
- No OAuth unless a concrete free and secure implementation is justified in a later decision. No email verification and no email-based password reset in v1 (flagged as human decisions, section 29); admin-assisted recovery only.

### 10.2 Scope boundary

Portfolio tracking and historical simulation are in scope. Paper trading (order simulation, execution semantics) is FUTURE: it needs a different data model and is not required by any committed workflow. Portfolio analytics reuse the fund/equity risk services, never duplicate their math.

---

## 11. ML, Forecasting, Scenario and Backtesting System

Nothing here claims to know the future. The system provides historical backtests, scenario simulations, probabilistic forecasts with uncertainty ranges, and calibration metrics with explicit limitations. The user-specified question ("if I invest X targeting Y in N years, what historical return/volatility profiles produced similar outcomes") is answered with historical distributions, never with a promised return.

### 11.1 Model candidates (each judged, not auto-included)

| Model | Inputs to target | Verdict | Assumptions, cost, failure modes |
|---|---|---|---|
| Historical bootstrap simulation | empirical daily NAV/price returns to N-year path distribution | **MUST** | No training, minimal leakage surface, honest uncertainty. Assumes roughly iid returns; documented. Runs in numpy in well under a second. |
| Block-bootstrap Monte Carlo | same, blocks preserve autocorrelation | **MUST** | Better regime behavior than iid; block-length choice documented and tested. |
| Rolling-window walk-forward evaluation | any model to next-period error | **MUST as the validation framework** | The spine that proves no leakage for every other model. |
| ARIMA / exponential smoothing (statsmodels) | NAV series to point forecast | **COULD**, only if it beats the bootstrap baseline out-of-sample | Cheap; weak for equity NAV; include on evidence, not sophistication. |
| Regime-conditional bootstrap | regime-labeled returns to conditional simulations | **COULD** | Nice crash-conditioning; regime definitions risk overfitting; kept simple. |
| Gradient boosting / XGBoost | engineered features to forward return | **FUTURE** | Feature and leakage burden far exceeds proven value at this data depth. |
| Temporal deep nets (LSTM/transformers) | - | **REJECTED** | GPU-free budget and data depth cannot support them credibly. |
| Bayesian approaches / ensembles | - | **FUTURE**, only after baselines and calibration exist | No ensembles before single honest models. |

All committed compute uses numpy, pandas, scipy, scikit-learn and statsmodels: local, CPU-only, importable on free runners and the free API tier. Training frequency: bootstraps need no training; any fitted model refits on a weekly Actions schedule with its parameters and window stored beside the outputs. Model outputs are precomputed where expensive and cached as `analysis_runs` rows (section 14).

### 11.2 Backtesting framework (mandatory, rigorous)

Point-in-time access only: simulations may touch only rows with date at or before t; a leakage test suite proves this by feeding simulators future rows and asserting they are ignored. Walk-forward and expanding/rolling windows; out-of-sample testing; multiple market regimes; benchmark comparison. Survivorship discipline: delisted/dropped securities and funds stay queryable (E10, fund curation keeps history). Unrealistic assumptions banned: costs/slippage stated where assumed, never zero-silently.
Metrics where appropriate: CAGR, volatility, Sharpe, Sortino, maximum drawdown, hit rate, MAE/RMSE for point forecasts, prediction-interval coverage, Brier score for probabilistic outputs, calibration summaries. Every result carries its kind; RNG seeds stored for reproducibility. Verdict: **MUST**; the leakage test suite is part of the definition of done (section 27).

### 11.3 Goal and risk simulator (mandatory)

Inputs: starting investment, monthly contribution, horizon, target corpus or return, maximum acceptable volatility/drawdown, optional confidence threshold. Outputs: required historical CAGR, required contribution for the target, historical probability of reaching the target under bootstrap, median/25th/75th percentile outcomes, historical worst-case periods, volatility and drawdown profile, calibration note. Example output shape: target 25 lakh in 5 years; median X; 25th percentile Y; 75th percentile Z; historical success probability P percent; historical maximum drawdown D percent; model confidence and calibration attached. Presented as **historical and statistical scenario analysis, not a promise of future returns**. Verdict: **MUST**.

### 11.4 Epistemic labeling (mandatory UI contract)

The frontend distinguishes five states with badges and methodology links: HISTORICAL FACT, BACKTEST, MODEL ESTIMATE, SCENARIO, UNCERTAINTY. A model estimate is never rendered as a guaranteed return; uncertainty ranges accompany every forecast. New DataState variants carry these labels (section 16).

---

## 12. Comparison Engine

Stock vs stock (up to 5): valuation multiples side by side with peer medians, fundamental sub-pillars, technical positioning, Alpha components, dividends and risk rows where comparable; methodology-aware notes where metrics are not cross-category comparable. Fund vs fund: performance windows, risk, holdings overlap, expense drag, manager tenure side by side. Read-heavy; reuses existing services; no duplicated math. Verdict: **MUST** (fund comparison rides the fund domain; stock comparison is the Semester 2 start item).

---

## 13. Data Source Strategy (NO DALOOPA)

**Daloopa status, stated once and completely:** Daloopa was never part of SignalDesk. A repo-wide grep at `968a44d` finds zero Daloopa code, configuration, dependencies or references. The `investing/daloopa_docs` material lives in a separate, unrelated workspace and is permanently excluded. Daloopa appears nowhere in this plan as a data provider, dependency, backend integration, deployment component, paid service, or source for stock or fund data. Any future proposal to introduce it would require a new explicit decision; none exists.

| Data | Source | Cost and auth | Terms, reliability, limits | Disposition |
|---|---|---|---|---|
| Equity/ETF prices (OHLCV) | yfinance `.NS` (primary) + Upstox v2 candles (secondary) | Free; Upstox manual token | Yahoo throttles at scale: chunked, rate-limit-aware ingestion. Upstox token expires (runbook item). | Keep, extend to 1000 |
| Fundamentals: income, balance sheet, cash flow, ratios | yfinance statements + Upstox statements APIs | Free | Income proven S1; BS/CF same adapter pattern. Bank formats stay null. | Keep, extend to three statements |
| Top-1000 ranking | NSE `EQUITY_L.csv` master + provider market caps | Free, no key | Public list; ranking input is Yahoo mcap only (Upstox supplies none: documented limitation). | New |
| Dividends and splits | yfinance series + info fields | Free | Reliable series; ex-dates provider-only; announced-vs-paid distinction recorded, never invented. | New |
| Earnings dates, estimates | yfinance `earnings_dates` | Free | Patchy for India: honest gaps. | New, best-effort |
| Benchmarks and sector indexes | yfinance `^NSEI`, `^CRSLDX`, `^NSEBANK`, sector symbols | Free | Ingested as benchmark rows reusing `daily_prices`. | New |
| MF NAV daily + history | AMFI official (amfiindia.com NAVAll + scheme history reports) | Free, no key | Official, structured, stable. Primary source. | New |
| MF metadata, AUM, expense ratios | AMC disclosures, AMFI scheme info | Free | Heterogeneous; curated set first. | New |
| MF holdings | AMC monthly portfolio disclosures (Excel/CSV first, PDF later) | Free | **Heterogeneous formats: the riskiest data dependency.** Monthly cadence acceptable. | New, flagged risk |
| News | Google News RSS (existing) | Free | Keep name-first + relevance filter. | Keep (core 500 first) |
| Earnings-call transcripts | None legitimate at zero cost | - | Not committed; alternatives in 5.10. | FUTURE |
| Ownership (promoter/FII/DII) | Exchange shareholding patterns are scraping-gray | - | Not committed without human/legal review. | COULD, gated |
| Macro data | RBI/MOSPI open data where needed | Free | Later; not on any critical path. | FUTURE |

Not recommended and not used: any paid data API; any exchange-website scraping without legal review; `mfapi.in` as primary (third-party mirror: acceptable fallback only); inventing transcript or ownership providers.

---

## 14. Target Data Architecture

New tables only; existing tables keep their semantics and conventions (D24-D26: surrogate PK, named unique upsert anchors, indexes on entity/date). Every row carries `source` and freshness timestamps per the Semester 1 provenance contract. Numeric money stays `Numeric`; JSONB only for explainability/metrics payloads.

```
Equities (new/changed):
  financial_periods  + ebitda, ebit, interest, depreciation, tax, eps_diluted
  balance_sheet_periods(stock_id, period_end, period_type, cash, investments,
    receivables, inventory, current_assets, total_assets, st_debt, lt_debt,
    current_liabilities, total_liabilities, equity, source, ingested_at)
    UNIQUE(stock_id, period_end, period_type)
  cash_flow_periods(stock_id, period_end, period_type, cfo, cfi, cff, capex,
    dividends_paid, source, ingested_at)   -- FCF derived, never stored
  dividends(stock_id, ex_date, amount, kind, source)
    UNIQUE(stock_id, ex_date, amount)
  earnings_events(stock_id, date, eps_estimate, eps_actual, source)
  benchmarks(symbol, name, kind)  -- prices reuse daily_prices via linked stock rows
  stocks + is_etf, isin, mcap_rank, mcap_asof, active, restrict_flag
  etf_metadata(stock_id, fund_house, index_name, ter, aum, aum_asof)

Funds (new domain):
  amcs(id, name)
  mutual_funds(id, amfi_code UNIQUE, isin_growth, name, amc_id, scheme_type,
    category, sub_category, inception, option, plan, benchmark, active)
  mf_nav_history(fund_id, date, nav)  UNIQUE(fund_id, date)
  mf_holdings(fund_id, as_of, stock_name, isin, pct_aum)
    UNIQUE(fund_id, as_of, isin)
  mf_metrics(fund_id, as_of, window, metrics JSONB)   -- monthly precompute
  fund_managers(fund_id, name, start_date, end_date)  -- only if sourced

Workspace (new domain):
  users(id, email UNIQUE, password_hash, created_at)
  sessions(id, user_id, token_hash, created_at, expires_at, revoked)
  watchlists(id, user_id, name) / watchlist_items(watchlist_id, kind, ref)
  portfolios(id, user_id, name) / portfolio_holdings(portfolio_id, kind, ref,
    qty, avg_cost, acquired_on) / holding_notes(portfolio_id, ref, note, updated_at)

ML (new domain):
  analysis_runs(kind, params JSONB, result JSONB, created_at)  -- capped, rotated
```

Retention policy (storage budget, section 22): daily prices keep 2y for the active universe; alpha backfill depth 2y for the top 250 and 1y for the rest if the canary demands it; NAV history 3y default (5y for top funds by AUM); holdings latest plus quarterly; news stores titles and metadata, not full article bodies (title plus snippet only); `analysis_runs` rotated. A storage-canary test projects growth against the 0.5 GB cap.

---

## 15. Target Backend and API Architecture

Same modular monolith (no microservices: no demonstrated requirement). New services: `statements.py`, `dividends.py`, `earnings.py`, `risk.py`, `funds/nav.py`, `funds/performance.py`, `funds/risk.py`, `funds/overlap.py`, `funds/screener.py`, `scenarios/bootstrap.py`, `scenarios/goal.py`, `backtest.py`, `comparison.py`, `workspace.py`, `auth.py` (sessions). Providers gain optional capabilities on the existing ABCs (`get_balance_sheet`, `get_cash_flow`, `get_dividends`, `get_earnings_dates`); callers treat `NotImplementedError` as "no data", never as failure (D56 pattern).

New endpoint families (all under `/api/v1`, same envelope, same auth posture as their domain):

| Family | Endpoints |
|---|---|
| Statements | `/stocks/{s}/statements` (income + balance + cash flow, periodized), `/stocks/{s}/dividends`, `/stocks/{s}/earnings`, `/stocks/{s}/risk` |
| Funds | `/funds` (screener), `/funds/{id}` (profile/performance/risk/holdings), `/funds/compare?ids=`, `/funds/overlap?ids=` |
| Fund lab | `/funds/lab/goal` (POST simulation), `/funds/lab/scenario` (POST bootstrap), `/funds/lab/backtest` (POST walk-forward) |
| ETFs | `/etfs` (screener), `/etfs/{symbol}` |
| Compare | `/compare/stocks?symbols=` (up to 5) |
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` (strictest rate bucket) |
| Workspace | `/workspace/watchlists...`, `/workspace/portfolios...` (all session-scoped) |

Ingestion passes grow (ranking, statements, dividends, earnings, benchmarks, NAV, holdings, fund metrics, screener precompute, chunked news) and stay `job_runs`-recorded. The screener becomes a precompute job at 1000 stocks (the O(n-squared) peer loop is retired from request paths). In-process scheduler stays for local dev; production scheduling is GitHub Actions (D79).

---

## 16. Target Frontend Architecture

Routes (lazy chunks, existing patterns): `/`, `/markets`, `/screener`, `/stocks/:symbol` (restructured: Overview / Statements [IS+BS+CF tabs] / Dividends / Earnings / Risk sections added), `/compare`, `/funds` (explore + screener), `/funds/:id`, `/funds/compare`, `/funds/overlap`, `/funds/lab` (goal + scenario), `/etfs`, `/etfs/:symbol`, `/workspace` (watchlists, portfolios; auth-gated), `/login`, `/register`, `/methodology` (extended per score/model).
Carried forward unchanged: DataState discipline plus new `model_estimate` and `uncertainty` states with the five epistemic badges (section 11.4); METRIC_INFO additions for every new metric (registry completeness stays test-guarded); TanStack Query with the same retry rules (404/NO_PEERS/INSUFFICIENT_DATA never retry); server pagination and virtualized tables at 1000 rows; the frozen visual system (no redesign). The frontend never recomputes backend math and never fabricates values: these rules extend to funds and scenarios.

---

## 17. Real-Time Data Strategy

No WebSockets are built and no exchange-grade real-time feed is promised: no legal free NSE real-time source exists, and Finnhub's free WebSocket tier does not cover NSE listings. Current data means daily bars plus an optional on-demand delayed-quote endpoint backed by provider `fast_info` with a 15-minute server cache and a strict rate limit, labeled delayed with its as-of time. The frontend keeps polling stored data. The dead `finnhub_api_key` config is removed or documented as unused. Every price display carries its as-of date; "daily close data" is stated in the UI rather than implied.

---

## 18. LLM Strategy (strict zero cost)

Verified 2026-09-08 from OpenRouter's official limits page: free model variants allow 20 requests/minute and 50 requests/day when the account's all-time purchased credits are under 10 USD, rising to 1000/day only after a one-time purchase of at least 10 USD in credits. Free model IDs also rotate. Consequences, all mandatory:

- LLM calls are **on-demand only**, behind the existing per-IP buckets, TTL caches and semaphore. **No nightly bulk pre-warming.** The shared daily cap is sized to the free tier (about 45 calls/day ceiling) so quota exhaustion is routine and invisible.
- Rule-based and deterministic narratives remain the default everywhere and must stay fully functional with the LLM disabled, capped or unreachable. LLM output is a cached upgrade, never a dependency.
- New surfaces (funds, scenarios) get their own evidence allow-lists on the `/ask` pattern; prompts carry computed facts only.
- The one-time 10 USD top-up that unlocks 1000 requests/day is documented as an **optional human choice outside the strict zero-cost plan**, never as part of it. GitHub Models (free PAT-authenticated tier for public repos) is the documented fallback LLM base URL candidate, subject to its own limits review at implementation time.
- Temporary credits, trials and expiring promotions never count as free architecture.

---

## 19. Security Architecture

Carry forward D94-D98 in full: no unnecessary exposure, ops Bearer auth fail-closed, gated ops and docs, pure-read analytics, per-IP rate limits, LLM concurrency cap, CORS and LLM-URL production guards, uniform safe error envelopes, secret hygiene (server-side only, never logged, never in the frontend).
Semester 2 additions: Argon2id hashing, server-side revocable sessions, httpOnly/Secure/SameSite cookies, no tokens in localStorage, enumeration-safe auth errors, strictest rate bucket on auth routes, user-data scoping enforced in queries and proven by adversarial tests, minimal PII, no file uploads (no upload attack surface), generated reports rendered server-side from stored data only.
Flagged for human/legal review, not claimed as compliance: research-vs-advice framing of disclaimers, portfolio-simulation wording, any future tax-aware or ownership-data features.

---

## 20. Testing Architecture

The Semester 1 suites (348 backend zero-network, 72 frontend) stay green in CI and grow: unit tests (score v2 math, overlap, risk, statements, bootstrap statistics), API tests (every new router), database tests (migrations, retention jobs, scoping), frontend tests (new pages, epistemic badges, honest states), E2E smoke per domain.
New mandatory suites: **data-validation tests** (balance-sheet identity tolerance, NAV sanity, dividend bounds, margin recomputation); **leakage tests** (simulators fed future rows must ignore them; walk-forward windows proven disjoint; seeded reproducibility); **calibration tests** (interval coverage on synthetic and historical data); **storage-canary test** (row-count growth projection vs the 0.5 GB cap); **auth adversarial suite** (cross-user access, session revocation, rate limits, enumeration). Backtest correctness (benchmark math, regime splits) and performance tests (screener precompute time, 1000-row pages) round it out.

---

## 21. Zero-Cost Deployment (verified research and recommended architecture)

### 21.1 Verified free-tier facts (official provider pages, 2026-09-08)

| Service | Permanent free terms | Card | Sleep / cold behavior | Trap found |
|---|---|---|---|---|
| Cloudflare Pages | 500 builds/month, 20k files, 25 MiB per file, effectively unlimited static bandwidth | No | n/a | None. Chosen for the frontend. |
| Render, Hobby plan | Free web service: 512 MB RAM, 0.1 CPU, spins down after about 15 min idle, cold start roughly 30-60s, 500 build minutes/month | No | Yes | **Free Postgres expires after 30 days: rejected as the database.** |
| Neon, Free plan | Permanent, no card: **0.5 GB storage per project (hard cap: exceeding it suspends compute until the next billing month)**, 100 CU-hours/month compute, scale-to-zero after 5 min, 5 GB egress | No | Yes | Storage cap is the number-one architecture constraint. |
| Supabase Free (fallback) | 500 MB database, pauses after 7 days idle (daily cron activity prevents pausing) | No | Yes | Same storage ceiling; kept as fallback. |
| GitHub Actions | Free unlimited standard-runner minutes on public repos (this repo is public); **6-hour per-job cap** | No | n/a | 6-hour cap governs ingestion design. |
| OpenRouter free models | 20 req/min; 50 req/day under 10 USD all-time credits; 1000/day after a one-time 10 USD purchase | No | n/a | LLM sized to 50/day (section 18). |

Rejected as not permanently free: Railway (one-time trial credit), Fly.io (card required), Render free Postgres (30-day expiry), any paid database, GPU or queue service.

### 21.2 Recommended zero-cost production architecture

```
Browser
  Cloudflare Pages (static React build, free CDN + TLS)
    |  /api via VITE_API_BASE
    v
  Render free web service (FastAPI; FinBERT excluded from this image: 512 MB)
    |  asyncpg, pooled, autosuspend-tolerant
    v
  Neon free Postgres (0.5 GB, autosuspend; storage-canary monitored)
    ^
GitHub Actions cron (public repo, free): daily chunked ingestion,
  weekly re-rank + fund-metrics + screener precompute + pg_dump backup artifact.
CI on push: pytest + vitest + tsc + build, then deploy hooks.
```

In-process APScheduler disabled in production (Actions is the scheduler: D79). FinBERT scoring stays in the ingestion runtime (Actions runners have 7 GB RAM), keeping the API image under 512 MB. Cold starts are absorbed by the static shell plus skeleton states. Rollback is Render rollback plus Alembic downgrade; backups are the Neon history window plus weekly `pg_dump` Actions artifacts plus one manual Neon snapshot. Secrets live in Render env and Actions secrets only. **Ongoing infrastructure cost: 0 (USD 0, INR 0).** Optional non-zero items are flagged separately and never counted: custom domain (about 10 USD/year), one-time 10 USD OpenRouter top-up.

---

## 22. Resource, Storage and Runtime Budgets

KNOWN LIMIT = verified fact. ESTIMATE = computed from Semester 1 row sizes and provider behavior. UNKNOWN = must be measured at Milestone 1.

| Resource | KNOWN LIMIT | Estimate at Semester 2 scale | Status |
|---|---|---|---|
| Neon storage | **0.5 GB hard** (exceeding suspends compute) | daily_prices 1000x500 rows ~60-90 MB; alpha_scores ~480k slimmed rows ~100-150 MB; NAV curated ~800 funds x 3y ~600k rows ~60-80 MB; statements ~15 MB; dividends ~5 MB; holdings (latest+quarterly) ~25-30 MB; mf_metrics ~10 MB; news title-only ~10-20 MB; misc ~30 MB. **Total roughly 320-450 MB.** | Tight. Mitigations: slim `components_json`, title-only news, 3y NAV default (5y top funds), retention jobs, canary test. First to cut if breached: alpha backfill depth to 1y outside top 250. |
| Neon compute | 100 CU-hours/month | API traffic plus ingestion far below at minimum compute size | OK (measure) |
| GH Actions runtime | 6 h/job, unlimited public minutes | Nightly at 1000 symbols roughly 2.5-4.5 h chunked: prices 15-25 min, financials 20-35 min, statements 70-130 min, profiles ~15 min, news core-500 20-35 min + FinBERT, alpha incremental 10-20 min | OK **if** benchmarked at M1 (UNKNOWN until measured); news stays core-500 first per the tiered decision |
| Render API | 512 MB RAM, cold starts | API well under; FinBERT excluded by construction | OK |
| Egress | 5 GB Neon; CF static unlimited | Tiny JSON API | OK |
| LLM | 50 requests/day free | On-demand + cache, about 45/day ceiling | OK by design |
| Frontend builds | 500/month CF Pages; Render 500 build-min/month | A handful of deploys per week | OK |

**First likely bottleneck: Neon 0.5 GB storage.** Second: Actions job runtime at full breadth (the M1 benchmark gate). Third: Render cold-start latency (UX-mitigated, not data-risk).

---

## 23. Semester 2 Dependency Graph

```
M1 Scale-Up and Ship It (1000 universe, chunked ingestion, CI, deploy skeleton, storage guardrails)
 +-> M2 Statements and Depth (BS/CF/dividends/earnings, Alpha v2, stock page restructure)
 +-> M3 Accounts and Workspace (auth, watchlists, portfolios)        [parallel with M2]
 +-> M4 Fund Data Backbone (AMFI NAV, fund catalog, metrics precompute)
       +-> M5 Fund Research Experience (screener/detail/compare/overlap)
              +-> M6 ETF Layer (reuses equity + fund analytics)
              +-> M7 Scenario and Forecast Lab (goal sim, bootstrap, backtest framework)
                     +-> M8 Research Synthesis and Close (comparison, reports, LLM-on-funds, DoD audit)
```

M3 needs only M1's deploy and schema conventions. M7 needs M4/M5 data plus the leakage test suite. M8 needs everything.

---

## 24. Semester 2 Milestones (M1-M8)

Milestone names are meaningful; there is no Phase 9/10 numbering. Each states objective, user outcome, scope, dependencies, explicit exclusions and definition of done. Test and deployment-impact rows from the planning brief are folded into scope and DoD to keep this file operable.

### M1 - Scale-Up and Ship It

- Objective: prove the two riskiest constraints (Actions runtime, database size trajectory) and get the product live at zero cost.
- User outcome: the same Semester 1 research product, live on a public URL, over the top-1000 ranked universe.
- Scope: top-1000 ranking job with E1-E12 rules and audit reasons; chunked rate-limit-aware ingestion; CI workflow (pytest, vitest, tsc, build on every push); production deploy per section 21; storage canary plus retention jobs; news stays core-500 with the runtime benchmark gate; benchmark index ingestion (`^NSEI` and sector symbols).
- Dependencies: none. Exclusions: no new research features; no auth; no funds.
- DoD: 1000 ranked stocks priced plus snapshot fundamentals on the production URL; zero-cost itemized and verified; full suite green in CI; nightly cron green one week; storage projection under cap.

### M2 - Statements and Depth

- Objective: three-statement equity research plus dividends, earnings, risk and Alpha v2.
- User outcome: balance sheets, cash flows, dividends, earnings and a structured risk section on every sufficiently covered stock; a documented better Alpha Score.
- Scope: statement/dividend/earnings/risk endpoints and pages (sections 5.3-5.9, 5.13); enriched peers; sector index sets; Alpha Score v2 with versioned methodology; screener precompute.
- Dependencies: M1. Exclusions: DCF unless the data audit passes; transcripts; ownership without review.
- DoD: three statements researchable for at least 700 of 1000 stocks with honest gaps elsewhere; Alpha v2 live, snapshotted and documented; screener off request paths.

### M3 - Accounts and Workspace

- Objective: account-backed watchlists and portfolios behind secure sessions.
- User outcome: register, log in, keep watchlists, track a holdings portfolio with returns, risk and overlap.
- Scope: auth routes and session machinery (section 10.1), workspace schema and endpoints, workspace pages, scoping and adversarial auth tests, rate-limited auth bucket.
- Dependencies: M1 (deploy + schema conventions). Parallel with M2. Exclusions: OAuth, email flows, paper trading.
- DoD: full register/login/watchlist/portfolio flow on production; cross-user access tests green; no PII beyond email+hash.

### M4 - Fund Data Backbone

- Objective: current, trustworthy fund data.
- User outcome: fund catalog with T-1 NAVs and precomputed performance/risk metrics.
- Scope: AMFI daily NAV + scheme catalog ingestion, curated fund universe (about 800 by category/AUM rule, section 29), NAV history backfill, nightly metric precompute, AMC pages.
- Dependencies: M1. Exclusions: holdings (M5), scenarios (M7).
- DoD: curated universe current to T-1; metrics tables populated; curation rule documented.

### M5 - Fund Research Experience

- Objective: the first-class fund product.
- User outcome: screen, research, compare and overlap-analyze funds.
- Scope: fund detail/screener/compare pages and endpoints; holdings ingestion Excel-first with monthly cadence; overlap engine with exact definitions; category and benchmark analytics; fund tools per section 8.9 priorities.
- Dependencies: M4. Exclusions: PDF reports (M8), transcript-like commentary.
- DoD: overlap reproducible by hand on three documented pairs; honest states where disclosures are missing; holdings current to latest disclosure month.

### M6 - ETF Layer

- Objective: ETF coverage reusing both pipelines.
- User outcome: ETF screener and detail with tracking difference and overlap.
- Scope: ETF catalog flags, metadata ingestion, screener/detail, index-difference math where free index data exists.
- Dependencies: M2 analytics + M5 fund tooling. Exclusions: full constituent ingestion where unsourced.
- DoD: ETF screener plus at least 20 tracked ETFs live with honest gaps.

### M7 - Scenario and Forecast Lab

- Objective: honest historical simulation and forecasting.
- User outcome: goal simulator, bootstrap scenarios, walk-forward backtests with uncertainty and calibration.
- Scope: bootstrap/block-bootstrap services, goal simulator, backtesting framework, leakage and calibration suites, five-state epistemic UI, Alpha hit-rate backtest vs forward returns.
- Dependencies: M4/M5 data. Exclusions: XGBoost/deep models (FUTURE), bull/base/bear narratives.
- DoD: leakage tests prove point-in-time access; every output labeled; no guaranteed-return rendering anywhere.

### M8 - Research Synthesis and Close

- Objective: tie the product together and close the semester.
- User outcome: stock comparator, downloadable research reports, LLM narratives on funds, complete methodology.
- Scope: `/compare/stocks`, PDF report generation (rate-limited), LLM-on-funds (on-demand, capped), methodology pages for every score and model, final DoD audit and documentation.
- Dependencies: all prior milestones. Exclusions: anything in FUTURE.
- DoD: section 27 fully met.

---

## 25. Prioritization: MUST / SHOULD / COULD / FUTURE

MUST: top-1000 scale-up; CI plus production deploy; balance-sheet/cash-flow/dividend/earnings/risk research; Alpha Score v2; account-backed auth, watchlists and portfolios; fund NAV/catalog/metrics; fund screener/detail/compare; holdings plus overlap engine; SIP/lump-sum and goal simulators; backtesting framework with leakage proof; stock comparison; all data infrastructure these need.
SHOULD: ETF system; screener precompute; sector/industry index sets; rolling-return, drawdown and recovery explorers; crash-episode explorer; style/size exposure from holdings; expense-ratio impact; consistency score; risk flags; retention automation; UptimeRobot monitoring.
COULD: conditional DCF; PDF reports; NL screener; `/overview`; weekly resample; logo CDN; Three.js overlap visualization; earnings-event timeline; ARIMA/regime models on evidence; Supabase fallback swap.
FUTURE: transcripts; filings ingestion; ownership/FII-DII without review; bull/base/bear narratives; paper trading; macro data; XGBoost and ensembles; tax-aware features; OAuth and email flows.

---

## 26. Explicitly Rejected and Obsolete Items

RabbitMQ and message queues (no consumer exists; Actions cron is the worker, so the old "distributed progression" is satisfied by D79's cheaper decoupling); Docker and Kubernetes (one free instance, no replication need); Redis (single process; in-process caches and limits adequate); Render free Postgres (30-day expiry); Railway and Fly.io (trial/card, not permanently free); Cassandra (cut at D-session scope review); derivatives (D2); Finnhub WebSocket for India (free tier does not cover NSE); paid data APIs of any kind; third-party NAV mirrors as primary; deep-net forecasters; **Daloopa in any form, permanently** (section 13); exchange scraping without legal review; any feature fabricated from unobtainable data.

---

## 27. Semester 2 Definition of Done

1. Production URL live at verified zero ongoing cost (itemized), frontend on Cloudflare Pages, API on Render, database on Neon, ingestion and CI on GitHub Actions.
2. 1000 ranked stocks with prices, snapshot fundamentals, and income/balance-sheet/cash-flow history where providers supply it; honest nulls elsewhere; `mcap_rank` refreshed monthly with audit reasons.
3. Alpha Score v2 live with documented methodology, versioned components and per-metric info affordances.
4. Mutual funds: curated universe with T-1 NAVs, screener/detail/compare, holdings plus overlap engine, precomputed risk and returns.
5. Scenario Lab: goal simulator plus bootstrap simulations plus walk-forward backtests with zero-leakage test proof and five-state epistemic labeling.
6. Account-backed watchlists and portfolios behind Argon2id sessions; all research routes still anonymous; Phase 8 security posture extended, never regressed.
7. Full suites green in CI (backend, frontend, leakage, security, data-validation); E2E smoke per domain; storage canary under 0.5 GB with retention jobs running.
8. Planning and progress docs current; README reflects the shipped product; no secrets in the repo; Daloopa absent (grep-clean); no em-dash or AI-tell regressions in user-visible copy.

---

## 28. Deployment Runbook Outline

Accounts (Cloudflare, Render, Neon, GitHub) to secrets provisioning (`OPS_API_KEY`, `CRON_API_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `VITE_API_BASE`, optional LLM keys) to first deploy (Render service from repo, Alembic `upgrade head` as release command, seed plus first full ingestion from Actions via workflow dispatch) to Pages connection (build command, env) to cron schedules (daily ingest after market close ~19:00 IST; weekly re-rank, fund metrics, screener precompute, `pg_dump` backup) to smoke checklist (`/health`, `/status/full`, one stock E2E, one fund E2E) to rollback (Render rollback + `alembic downgrade`) to backup/restore (weekly `pg_dump` artifact; Neon history window; one manual snapshot) to monitoring (Render logs, UptimeRobot ping on `/health`, `/status/full` review) to the operational risks register: Upstox token expiry, Yahoo throttling at 1000 symbols, Neon storage alarm, Actions runtime drift, free-model rotation, Yahoo market-cap gaps in ranking.

---

## 29. Remaining Human Decisions

Custom domain (about 10 USD/year: outside strict zero cost, optional). One-time 10 USD OpenRouter top-up (optional, unlocks 1000 requests/day; outside the plan). Email verification and password-reset flows now or later. Fund-universe curation cut rule (proposed: top by AUM per category to about 800). MF holdings automation level (manual monthly download vs semi-automated fetch with review). Upstox token renewal owner and cadence. News breadth step-up (500 to 1000) after the M1 runtime benchmark. Legal-review pass on disclaimers, simulation wording and any ownership-data collection. Whether to keep Upstox at all if token maintenance lapses (yfinance-only fallback is designed in).

---

## 30. Recommended First Implementation Task

**M1, first vertical slice:** a CI workflow that runs the existing 348-test backend suite plus the 72-test frontend suite, typecheck and build on every push (no deploy yet). Immediately followed by the top-1000 ranking job and one measured end-to-end chunked ingestion run in Actions. This single slice proves the two riskiest constraints (Actions runtime, database size trajectory) before any feature work builds on top of them. Stop after the slice, review measurements against section 22, then proceed.

---

## Appendix A: verified external facts (2026-09-08)

Free-tier terms below were read from official provider pages on 2026-09-08 by the planning agent (Neon pricing, Render pricing, Cloudflare Pages limits, OpenRouter limits). Re-verify at implementation time if months have passed; free tiers change.

- Neon Free: 0 USD permanent, no card; 0.5 GB storage per project (exceeding suspends compute until next billing month); 100 CU-hours/month compute; scale-to-zero after 5 min; 5 GB egress; 10 branches.
- Render Hobby: free web service 512 MB RAM / 0.1 CPU with spindown; free Postgres carries a 30-day limit; 500 build minutes/month.
- Cloudflare Pages Free: 500 builds/month, 20,000 files, 25 MiB per file, effectively unlimited static bandwidth.
- OpenRouter free variants: 20 requests/min; 50 requests/day with under 10 USD all-time credits, 1000/day after a one-time 10 USD purchase; model IDs rotate.
- GitHub Actions: free unlimited standard minutes on public repos; 6-hour per-job cap.

## Appendix B: Semester 1 engineering standards carried forward

Single error envelope `{error:{code,message,detail,request_id}}` with domain exceptions mapped in routers; secrets via git-ignored `.env` plus committed `.env.example` plus pydantic-settings startup validation; testing order services to repositories to routers with providers always mocked and the LLM always mocked; retry-then-stale-flag-then-clean-502 provider failsafe chain; `NoPeersError` (409) rather than silent wrong answers; copy discipline (no em dashes, no AI-tell wording, "-" null placeholder, normalized disclaimer); N+1 query guards; backend owns all math; request-id structured logging with no secrets in logs.

---

*End of Semester 2 Master Plan. Implementation starts at section 30. Companion tracker: `SEMESTER2_PROGRESS.md`.*
