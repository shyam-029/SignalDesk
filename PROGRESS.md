# SignalDesk - Progress Log

> **Purpose:** The operational counterpart to `PLANNING.md`. This is the file to read FIRST to pick up
> where we left off. Updated after every phase.
> **Rules:** What's done → in progress → next. Command cheatsheet. Known gotchas.
> **Last updated:** 2026-09-06 (Post-Part I round: Upstox renamed-symbol fix (TATAMOTORS->TMPV), /alpha split with lazy explanation + nightly pre-warm, provider-sourced company profiles with About box + ask evidence)
> **Roadmap audit completed 2026-08-19 - see PLANNING §18 (4-tier product taxonomy).**

---

## 1. Current Status

| Phase | Status |
|---|---|
| 1 - Environment setup | ✅ **COMPLETE** |
| 1 - App scaffold (config, models, migration) | ✅ **COMPLETE** |
| 1 - yfinance provider + Nifty 50 ingestion | ✅ **COMPLETE** |
| 1 - First endpoints + error handling + startup | ✅ **COMPLETE** |
| 1 - pytest suite (providers mocked) | ✅ **COMPLETE** |
| **Phase 1 - Definition of Done (see PLANNING §16)** | ✅ **MET** |
| 2 - SP1: Financials model + provider + ingestion | ✅ **COMPLETE** |
| 2 - SP2: Scoring + valuation services | ✅ **COMPLETE** |
| 2 - SP3: Repositories + routers + screener | ✅ **COMPLETE** |
| **Phase 2 - Relative valuation + fundamental scores** | ✅ **COMPLETE** |
| 2.5 - HARDENING (analysis service, N+1, retry, logging, coverage) | ✅ **COMPLETE** |
| 3 - News RSS ingestion + FinBERT sentiment | ✅ **COMPLETE** |
| 4 - Technical indicators + Alpha Score composite | ✅ **COMPLETE** |
| 5 - Grounded LLM explanation | ✅ **COMPLETE** |
| **6 - React dashboard + charts (frontend + backend gaps)** | ✅ **COMPLETE** |
| **6.5 - Experience overhaul (copy, typography, palette, motion)** | ✅ **COMPLETE** |
| **6.5 E - Historical financial data layer** | ✅ **COMPLETE** |
| **6.5 F - Dual data providers (Upstox + MergingProvider)** | ✅ **COMPLETE** |
| **6.5 G - News relevance, fallback, freshness** | ✅ **COMPLETE** |
| **6.5 D - Stock research page expansion** | ✅ **COMPLETE** |
| **6.5 - Review round (250 universe, refresh, fixes)** | ✅ **COMPLETE** |
| **Session 20 - Alpha history recompute + research UX fixes** | ✅ **COMPLETE** |
| **Part H - Grounded single-shot ask (LLM)** | ✅ **COMPLETE** |
| **Part I - Phase 6.5 verification + close-out** | ✅ **COMPLETE** |

**One-line status:** **Phase 6.5 COMPLETE (Parts A-I)** + Session 20 review round. Part I closed
6.5 with full regression (backend 262/262, tsc clean, vitest 65/65, build OK), a 47-check E2E
smoke test over every user flow against real stored data, and a data-quality audit (250/250
stocks priced to the last trading day, zero malformed/duplicate bars, margins internally exact,
honest zero-vs-missing handling). Final 6.5 additions: a header stock search matching ticker AND
company name over the real catalog (D80), and honest alpha history - backfilled rows no longer
carry forward today's fundamental/sentiment as if they were daily observations (D81). The ask
endpoint is live (stale-backend restart was the earlier "not working" cause). **Next: Phase 7
(observability).**

---

## 2. Completed Work

### Post-Part I round - Upstox everywhere, /alpha split, company profiles (2026-09-06)

User-driven round after live usage. See PLANNING D82-D84.

- [x] **Upstox gap-fill diagnosis + renamed-symbol fix (D82):** the token WORKS (live-verified:
      RELIANCE ratios/prices/statements all fetch) and the MergingProvider field-level coalesce
      already fills every field Upstox carries. The one systematic failure was symbol resolution:
      **TATAMOTORS.NS is renamed TMPV on the NSE post-demerger** (same ISIN INE155A01022), so
      1 of 251 catalog symbols failed Upstox instrument lookup and fell back to an all-null
      yfinance snapshot. Added a documented `SYMBOL_ALIASES` map (TATAMOTORS -> TMPV) to the
      Upstox adapter; TMPV verified live (fundamentals, 22 daily bars, 4 annual periods).
      Honest irreducible gaps (both providers lack them, scores renormalize):
      interest_coverage 0/251 stocks (no interest-expense line in Upstox's income statement,
      absent in yfinance), D/E for ~24 banks, EV/EBITDA absolutes for ~41 (Upstox supplies the
      pre-computed ratio, which the valuation fallback already consumes).
- [x] **/alpha split (D83):** GET /alpha is now pure DB math (composite, components, weights,
      value signal) - zero LLM work, no explanation field. The narrative moved to
      GET /stocks/{symbol}/alpha/explanation (same grounding pipeline + TTL cache + fallback).
      The frontend fetches it in parallel and renders it in its own skeleton region inside the
      Alpha card: the score renders instantly; only the sentence can show a loading state.
- [x] **Nightly explanation pre-warm (D83):** the ingestion sweep now calls
      generate_alpha_explanation for every catalog symbol right after the alpha backfill
      (2s pause between calls for free-model rate limits, shared daily cap respected), so the
      TTL cache is warm before any user visits. `LLM_DAILY_CAP` default 100 -> 300.
- [x] **Company profiles (D84):** new `company_profiles` table (+ migration 74b2071c0d29) fed by
      `ingest_company_profiles` (batched, per-symbol isolation): the provider's verbatim
      business description (yfinance longBusinessSummary), CEO (from companyOfficers),
      employees, website. Served at GET /stocks/{symbol}/profile; rendered as the
      "About the company" glass box below the Alpha score (paragraphs + CEO/employees/website
      row, missing fields omitted); added to the ask endpoint's allow-listed evidence with the
      system prompt updated: company-background questions (what the company does, who the CEO
      is) are answered THROUGH the stored profile only - facts it does not contain get an
      explicit "do not have that information", never invention.
- [x] **Tests:** alias-resolution unit tests (renamed symbol uses the new key; alias table is
      exactly the known renames), profile endpoint tests (stored + missing-null), alpha split
      tests (/alpha has no explanation field; /alpha/explanation returns a grounded narrative),
      financials coalesce test coverage via existing upsert tests. Verified live after a full
      re-ingest: TATAMOTORS has 498 price bars (latest 2026-09-04) + Upstox-sourced financials
      + alpha composite 43 (previously zero data end to end); 250/251 company profiles stored
      (250 with summaries, 34 with CEOs); /alpha response has NO explanation field; the
      explanation pre-warm warmed **250/250** symbols. Backend **267/267**, tsc clean,
      vitest 65/65, build OK.
- [x] **Data honesty notes:** remaining nulls are genuine both-provider gaps - interest
      coverage (all 251; no provider supplies an interest-expense input), D/E for ~24 banks,
      EV/EBITDA absolutes (~41; Upstox supplies the ratio, which valuation consumes), ROE/ROA
      for ~61 (mostly Financial Services where neither provider reports it). Financials upserts
      now coalesce per field on write (a throttled night can no longer wipe stored values).
      A catalog repair pass (`repair_catalog_gaps`, nightly) ingests stocks the universe
      passes dropped, so no catalog stock is permanently empty.

### Part I - Phase 6.5 verification and close-out (2026-09-06)

Final checkpoint: regression, E2E smoke, data-quality audit, integration/security audit, two
last additions, documentation. No redesigns, no speculative features, no fabricated data.

- [x] **Full regression:** backend pytest **262/262**; frontend `tsc -b` clean; vitest **65/65**
      across 8 files; `vite build` OK. Working tree clean before the Part I commit.
- [x] **E2E smoke (47/47 checks, live server, real stored data):** catalog list (251 total),
      stock detail + normalized symbol, valuation (P/E 23.92 vs median 7.87 → overvalued),
      fundamentals key ratios, technicals (score bounded, 200 closes) + 250-bar series, news
      (real articles) + sentiment aggregate, alpha composite + renormalized weights + 180-snapshot
      history, windowed performance + 52w range + volatility, peer comparison (target excluded),
      financials history incl. half-yearly grouping, ONE real grounded ask (`source: "model"`,
      answer cites the actual peer median) + /explain, insufficient-data behavior (TATAMOTORS:
      valuation 422 INSUFFICIENT_DATA, technicals flagged, null scores never zeros, ask answers
      only from its real sentiment evidence), unknown-symbol 404 envelope, 422 envelopes for
      empty/over-500 questions and bad metric, SPA deep-link routing through the vite dev server,
      and the vite proxy preserving the backend error envelope.
- [x] **Data-quality audit:** 250/250 stocks priced, latest bar 2026-09-04 (the last trading
      day - fresh, not stale); 5,770 news articles (newest Sep 5); 0 malformed bars
      (close<=0 / high<low) and 0 duplicate stock-date rows; stored annual net margins match
      NI/revenue exactly for RELIANCE (drift 0.00000); all 119,707 alpha composites within
      [0,100]; zero-vs-missing verified - BSE's D/E 0.00 is a genuine zero (debt-free exchange),
      TATAMOTORS's all-null financial snapshot (provider gap) stays null everywhere; provider
      disagreements resolved via the MergingProvider merge (see PLANNING D66). No fabricated
      values found; no carried-forward component history remains (0 rows with fundamental set
      outside genuine live snapshots).
- [x] **Integration/security audit:** Upstox exists only as a backend provider (frontend greps
      clean); MergingProvider behavior pinned by tests; no credentials, model IDs, or API keys
      anywhere in the frontend (only public `VITE_API_BASE`); `backend/.env` untracked and
      git-ignored (`git ls-files backend/.env` empty); LLM evidence-grounded (prompt allow-list
      + strict output contract + tests); ask remains single-shot with no conversation memory;
      prompt-injection protection = OpenRouter workspace guardrail (provider-side, 403 → safe
      ASK_BLOCKED) + backend sandboxing (sanitize, scope check, quoted-question embedding,
      output validation); frontend consumes the backend - no duplicated financial math (unit
      scaling for display only).
- [x] **Header stock search (D80):** `StockSearch` in the site header - matches ticker (with or
      without ".NS") and company name over the cached /stocks catalog, ranked ticker-first,
      keyboard-navigable, deep-links to the research page; matcher is a pure unit-tested
      function (`lib/search.ts`, 6 tests).
- [x] **Honest alpha component history (D81):** backfilled alpha rows store composite + real
      technical only; fundamental/sentiment are no longer carried forward as flat pseudo-history
      (dev DB re-backfilled: 0 rows with fabricated fundamentals). Component lines appear only
      as genuine daily /alpha snapshots accumulate.
- [x] **Cleanup:** no dead imports or debug artifacts found in the diff; temporary smoke/audit
      scripts live outside the repo; no stylistic rewrites of working code.

### Session 20 follow-up - ask made live, chart first-render, financials views (2026-09-06)

Post-review fixes from the first Session 20 usage round.

- [x] **"The ask service could not be reached" - root cause: stale backend process.** The
      uvicorn server on :8000 was started before Part H existed, so `POST /stocks/{symbol}/ask`
      returned a bare 404 (no envelope) and the panel reported a network failure. The server was
      restarted with current code; the exact failing case ("should i buy it" on BEL) now returns
      200 with a grounded, advice-refusing `source: "model"` answer. The panel's error states now
      distinguish a missing route (HTTP 404 without the standard envelope → "restart the backend"),
      5xx/network (retry affordance), guardrail blocks, and backend-provided messages.
- [x] **Chart first-render squish fixed:** collapsible sections keep content mounted with
      `hidden` (width 0), so TimeSeriesChart/PriceChart built themselves at zero width and came
      out compressed/offset until an unrelated rebuild (theme toggle). Both charts now defer
      creation until the container has a real width (ResizeObserver gate) and rebuild on
      visibility changes.
- [x] **Even grid backgrounds:** vertical grid lines disabled on all research charts - the time
      scale's calendar ticks sit at uneven trading-day distances and made the background look
      irregular. Horizontal reference lines are perfectly even; the hover date tracker stays.
- [x] **Quarterly-default financials with derived views:** `GET
      /stocks/{symbol}/financials/history` gains `group=half_yearly` (sums two consecutive fiscal
      quarters) and `group=three_yearly` (sums three consecutive fiscal years). Aggregation is
      backend-owned: revenue/net income summed over periods that carry them, net margin
      recomputed from the sums, operating margin revenue-weighted, EPS never summed, and every
      grouped row carries `aggregated_from` (periods summed). The chart defaults to Quarterly
      with a Quarterly / Half-yearly / Yearly / 3-yearly toggle (yearly = stored annual rows);
      missing granularities show an honest insufficient state with a hint to switch views.
      Verified live: BEL half-yearly buckets sum correctly (e.g. H1 FY2026 revenue ₹9,149.59 Cr
      from 1 quarter + ... per stored data). Tests: 3 new grouping tests (sums, recomputed
      margins, validation) - backend 262/262.

### Session 20 - alpha-history recompute, research UX fixes, Part H ask (2026-09-06)

Product-review fixes (wrong-looking alpha charts, illegible charts, missing section separation,
derived-number audit) followed by the Part H grounded single-shot ask. See PLANNING D71-D76 for
the durable decisions.

- [x] **Alpha history recomputed (the "Alpha == Technical" bug):** the retroactive backfill
      previously renormalized missing fundamental/sentiment weights down to technical-only, so
      the composite was IDENTICAL to the technical score at every point. The backfill now holds
      each stock's latest known fundamental + sentiment scores constant across the window and
      computes the REAL 40/30/30 blend per day, then replaces the symbol's stored snapshots.
      Full recompute executed against the dev DB: 119,707 snapshots, 119,707 with a fundamental
      component (was 39).
- [x] **Technical score no longer sawtooths:** sub-score scaling softened (trend ±20% vs SMA20
      spans 0-100 instead of ±10%; momentum ±2% histogram/price instead of ±1%) and the
      composite is an EMA(5) of the daily raw scores (`score_technicals_series`, O(n) rolling).
      The scalar `score_technicals` is literally the last entry of the series, so live /alpha,
      /technicals and the backfill are one math. RELIANCE's daily composite delta dropped to
      ~0.25 points on average (range 51-60).
- [x] **Chart legibility + date tracker:** every chart (price, alpha history, indicator series,
      financial history) now shows a single vertical crosshair whose time-axis label carries the
      date; no horizontal price line/bubble. Technical series default window cut from 750 to 250
      bars (one trading year) - dense 3-year lines were unreadable at panel size.
- [x] **Peers table UX:** all six metric columns (price, 1D, P/E, ROE, net margin, D/E) are
      sortable (nulls last both directions, aria-sort, click to flip); three peers show by
      default with a "Show all N peers" / "Show less" footer toggle.
- [x] **Visual section separation:** new `--section-alt` token ("a bit darker shade of white"
      light mode, lighter warm-ink dark mode) applied to alternating sections on the stock page
      (Price, Fundamentals, News) and across the landing sequence; the ad-hoc
      `bg-surface-2/30|40` washes were replaced by the token. Glassy `.glass` panels: alpha
      history chart, technical-evidence and written-explanation cards (peers table and
      performance strip were already glass).
- [x] **Derived-number audit:** peer medians (median over valid positive multiples, target
      excluded), profitability/solvency threshold scoring, performance windows, 52w range,
      annualized volatility, sentiment aggregation and D/E-vs-percent unit handling all
      verified correct against the code. One real display bug found and fixed:
      `summaries.ts` looked for components named `roe`/`de_ratio` but the backend sends
      `ROE`/`Debt/Equity`, so collapsed fundamentals summaries never showed their raw input.
      Tests updated to the real component names.
- [x] **Part H - grounded single-shot ask** (below).

### Session 20 Part H - grounded single-shot ask (2026-09-06)

`POST /stocks/{symbol}/ask` - one natural-language question about THIS stock's computed data.
NOT a chatbot: single-shot, no conversation memory, no tool use, no DB access from the model.

- [x] **Evidence-only architecture:** the router (`app/routers/ask.py`) builds the evidence
      object EXPLICITLY (company, quote, alpha + value signal, technicals, P/E valuation,
      fundamental scores, windowed performance + volatility, sentiment aggregate, last five
      annual periods, static methodology). `ask_narrative.filter_evidence()` allow-lists the
      top level AND one nested level before anything reaches a prompt; `_gather_evidence`
      never touches ORM `__dict__`. Bare stocks carry no alpha block at all, so the
      evidence-sufficiency check sees honest emptiness.
- [x] **Untrusted question handling:** sanitize (control chars stripped, whitespace collapsed,
      500-char cap measured on the RAW input), rule-based scope classifier rejects clearly
      off-topic questions with no LLM spend (finance hints win ambiguity), insufficient-evidence
      state answers without the LLM, and the question is embedded in the user message as a
      quoted data string while the system prompt forbids following embedded instructions,
      revealing the prompt, giving advice, or claiming external sources.
- [x] **Strict output contract:** the model must return `{"answer", "evidence", "confidence"}`
      JSON; `validate_output()` parses defensively (fences/preamble tolerated) and validates
      strictly - malformed output falls back to the deterministic rule-based answer built from
      the same evidence (confidence "low").
- [x] **Cache / cap / fallback:** 15-minute TTL per (symbol, question) in-process; the SHARED
      Phase 5 daily budget (`llm_narrative.budget_ok/register_llm_call` - no second counter);
      fallback chain: no key -> no model -> cap -> model unavailable -> provider error ->
      malformed output -> rule-based answer. Model availability is verified against the
      OpenRouter catalog (GET /models, 10-min memo) before the first real request.
- [x] **OpenRouter guardrail integration:** the workspace prompt-injection regex guardrail is
      provider-side (never recreated in-app); a 403 from OpenRouter is surfaced as a safe
      `ASK_BLOCKED` 422 envelope with a generic message - no guardrail internals exposed.
      `LLMError` now carries the HTTP status.
- [x] **Config wiring:** `LLM_API_KEY` is primary with `OPENROUTER_API_KEY` as an
      `AliasChoices` alias (the dev .env only ever set the latter, so the LLM was silently
      disabled before); `.env.example` documents both plus the guardrail note.
- [x] **Frontend:** `AskPanel` rebuilt as a single-shot glass panel (no thread): 500-char
      textarea with counter, suggested questions, answer with evidence bullets + confidence
      badge, dedicated states for blocked/off-network, Enter-to-send. New `api.ask`,
      `AskResponse` types, `useAsk` mutation (no auto-retry).
- [x] **Zero-network tests (`tests/test_ask.py`, 21 tests):** sanitization, scope classification
      (incl. finance-hint win), evidence allow-list, prompt-embedding-of-injection, contract
      validation (valid/fenced/preamble/malformed), rule-based fallback numbers, endpoint
      success (shares the daily cap), injection attempt stays structured, guardrail block ->
      safe error, off-topic skip, insufficient-evidence skip, malformed-output fallback,
      provider-error fallback, TTL cache hit, daily cap fallback, model-unavailable fallback.
- [x] **Real smoke test:** model availability verified, then ONE live request
      (`POST /stocks/RELIANCE/ask`, question "Why is the Alpha score what it is, and how is the
      valuation versus peers?") returned 200 with `source: "model"`, a fully grounded answer
      (Alpha 54 = 40% fundamental 62 / 30% technical 49 / 30% sentiment 48; P/E 23.92 vs peer
      median 7.87, overvalued +203.94% with peer_count=1 caveat) and a 5-item evidence list.
      Model: `minimax/minimax-m3:free` (configured via `LLM_MODEL`; availability verified).

### Session 19 - review round: Nifty 250, data refresh, research UX fixes (2026-09-06)

Product review fixes across the stock, markets and screener pages plus a full data refresh. See
PLANNING D64-D68 for the durable decisions.

- [x] **Nifty 250 universe:** official NSE lists (nifty50/nifty100/midcap150) downloaded and
      committed as `app/data/nifty250.py`; `seed.py` now seeds nifty50 + nifty100 + nifty250
      (idempotent, prunes constituents the index dropped, normalizes names/sectors to the NSE
      taxonomy); ingestion universe widened to nifty250. All "50 companies" copy rebranded to 250.
- [x] **Data refreshed to the last trading day** (prices were stale at Aug 18 because the daily
      scheduler only runs while the backend process is alive): 250/250 symbols, 122,619 bars
      (latest 2026-09-04, the last trading day), 250 merged financials, 2,720 income-statement
      periods (annual + quarterly), 116,982 alpha snapshots, 4,769 news articles, all 0 errors.
- [x] **Upstox fundamentals enrichment:** `get_fundamentals` now also derives operating margin,
      net margin, current ratio and debt/equity from the Upstox income-statement + balance-sheet
      APIs (percent units matching yfinance), so solvency components exist for stocks yfinance
      leaves sparse (Bajaj Finance: D/E 314.8%, current ratio 0.48).
- [x] **Valuation multiple fallback:** when the snapshot cannot produce a multiple (e.g. NBFC
      EBITDA missing so EV/EBITDA failed), the pre-computed Upstox ratio fills in (in-process
      1h TTL cache; target AND peers). Live-verified: BAJFINANCE EV/EBITDA 18.51 vs 13.18 median
      where it previously errored.
- [x] **Quarterly financial history:** `get_financial_history(symbol, period_type)` on the
      provider ABC + both adapters; the ingestion job stores annual AND quarterly (1,560
      quarterly rows).
- [x] **Retroactive alpha history:** `backfill_alpha_history()` computes a snapshot for every
      stored trading day from the closes up to that date (technical-only composite; the same
      renormalization rule as live), bulk-upserted without overwriting full live snapshots. Every
      stock now charts ~500 daily alpha points across ~2 years.
- [x] **News widened (product decision):** 60-day freshness window, relevance relaxed to
      any-distinctive-token, and the provider merges the symbol-query results whenever the name
      search yields fewer than 8 usable articles. RELIANCE now returns 20 articles in the window.
- [x] **Frontend fixes:** monogram `StockLogo` on the stock header, peers table, markets and
      screener rows (zero remote assets, deterministic accent color); sector links to the
      sector-filtered list from the stock header and markets rows; green/red direction arrows on
      the header, markets and peers; InfoDot "i" forced lowercase (uppercase CSS bleed fixed);
      charts no longer scale/scroll on drag (`handleScale/handleScroll` off) and the series charts
      dropped the trailing crosshair label bubble; the OHLC readout is a prominent colored bar;
      technical charts are three stacked equal-size panels with 3 years of data and consistent
      contrasting colors; alpha history caption trimmed; financial history renders one bar per
      period with point-marked margin lines; peer rows link to their research pages with bold
      accent-colored columns; the research chat is a threaded glass window (answers persist per
      question); glass surfaces on the performance strip, peer table, screener filter bar/tables;
      markets gained a sortable Market cap column and server-side sort/direction params; screener
      gained a sector filter + server-side sorting; stock page carries the landing's sine scroll
      rail and a petrol header wash for light-mode color. Grid lines were NOT extended beyond the
      landing (per the approved reference).
- [x] **Verification actually performed:** backend `pytest` **233/233**; frontend `tsc -b` clean;
      `vitest` **59/59**; `vite build` OK; live smoke: `/stocks` server-side sort (market cap
      desc = RELIANCE, BHARTIARTL, HDFCBANK) + 20 distinct sectors, sector filter (Financial
      Services = 59), `/screener` profit-sort + sector param, BAJFINANCE EV/EBITDA via fallback,
      BAJFINANCE scores show real solvency components, RELIANCE news 20 articles at
      freshness_days=60, alpha history 180+ snapshots (2 years stored); DB checks: latest bar
      2026-09-04, 250 stocks, 1,160 annual + 1,560 quarterly periods.
- [x] **Known limitation (future scope, tracked in PLANNING):** automatic daily refresh requires
      the backend process to be running (the APScheduler job fires at 18:30 in-process). True
      unattended daily updates need a deployed worker or OS-level scheduler.

### Session 18 - Phase 6.5 Part D: stock research page expansion (2026-09-06)

Frontend integration phase on the approved design (two smallest-coherent backend additions for
compatibility); see PLANNING D61-D63. No visual redesign: existing typography, tokens, spacing,
chart styling and component patterns reused throughout.

- [x] **Collapsible research sections:** `CollapsibleSection` shell (header row is the toggle,
      aria-expanded/controls; content stays mounted hidden so queries stay warm). Valuation,
      Fundamentals, Technicals, News and Methodology collapse; Alpha (now with its history chart)
      and the primary price chart stay open. Collapsed summaries are computed from the SAME query
      data the section renders (pure builders in `lib/summaries.ts`): "Fairly valued · P/E 16.6 vs
      17.3 peers", "Strong profitability · ROE 47.7%", "Bullish · RSI 62.4", "N articles · net
      sentiment Positive". A section with insufficient data shows no summary and never invents one.
- [x] **Performance strip** (always visible, under the header): 1W/1M/3M/6M/1Y signed returns,
      52-week range and 1Y volatility from `/performance`. Missing windows render "-" (not zero);
      the strip degrades to an insufficient-data note under two bars.
- [x] **Alpha history** (`AlphaHistoryChart` in the Alpha section): composite line plus
      fundamental/technical/sentiment component lines only where snapshots carry them; fewer than
      two snapshots is an explicit "history is building" state; gaps break lines instead of
      interpolating.
- [x] **Technical series** (in the collapsible Technicals section, alongside the moved aggregate
      positioning panel): price + SMA20/EMA12 overlay, RSI14, MACD (line/signal/histogram) from
      `/technicals/series` via the shared `TimeSeriesChart`; the frontend renders series and never
      recomputes indicator math.
- [x] **Peer comparison table** (in the collapsible Valuation section): same-industry peers with
      price, 1D change, P/E, ROE, net margin and D/E from `/peers`; "-" always means "the snapshot
      does not carry this metric" while a rendered zero is a real zero.
- [x] **Historical financials** (in the collapsible Fundamentals section): annual revenue and net
      income (displayed in ₹ Cr) and operating/net margin charts from `/financials/history`, with
      a latest-period readout that shows the row's source and "-" for missing fields.
- [x] **Backend additions (smallest-coherent):** `/performance` gains `volatility_1y_pct`
      (annualized daily-return volatility; null under three closes, exact-value test pinned);
      `/peers` gains ROE/profit margin/D/E from the already-batched financials snapshot.
- [x] **Verification actually performed:** backend `pytest` **234/234** (2 new volatility tests);
      frontend `tsc -b` clean; `vitest` **59/59** (16 new summary tests); `vite build` OK (stock
      page chunk 65.7 kB / gz 18.7); live smoke of all five endpoints on the running backend
      (RELIANCE: 500 bars, windows incl. an honestly missing 2Y anchor, vol 20.37%, 52w range,
      BPCL peer with null ROE rendered, 60-bar series matching /technicals values, 5 annual
      periods, 3 alpha snapshots; TATAMOTORS: insufficient_data on every new endpoint; unknown
      symbol: 404 envelope); production `vite preview` deep link HTTP 200 + API proxy OK; stale
      uvicorn on :8000 found and killed before verification (its multiprocessing child held the
      port after the parent died).

**Durable decisions (see PLANNING D61-D63):** collapsed sections keep their content mounted so
summaries stay data-backed; summaries are presentation strings from pure tested builders fed by the
same queries the sections render; the frontend charts backend series and never duplicates indicator
or performance math; missing windows/values render "-" and insufficient states, never zeros.

### Session 17 - Phase 6.5 parts E/F/G (2026-09-05)

Historical financials, dual data providers, news relevance. Frontend unchanged except the approved
landing background grid lines; see PLANNING D56-D60.

- [x] **Part E, historical financial data:** `FinancialPeriod` model + migration `a844177fa25e`
      (UNIQUE stock_id+period_end+period_type; every metric nullable); `get_financial_history()`
      as an optional provider capability (ABC default raises NotImplementedError, callers treat as
      "no history", never an error); yfinance maps `income_stmt` (4-5 annual periods, backend
      computes margins, missing stays None); `ingest_financial_periods()` job (batched, D19
      isolation, idempotent upsert refreshing ingested_at) wired into the daily run; five new
      endpoints in `routers/history.py`: `GET /stocks/{symbol}/performance` (windowed returns,
      52w range), `/alpha/history`, `/technicals/series`, `/peers`, `/financials/history`.
      Series variants (sma/ema/rsi/macd) added to `services/indicators.py`, test-pinned equal to
      the scalar functions.
- [x] **Part F, dual providers:** Upstox official docs verified before implementation (manual
      "Analytics Token" generation = Bearer credential; no interactive OAuth). `UpstoxProvider`
      resolves symbols via the official NSE instruments master (trading_symbol -> instrument_key
      + ISIN, cached per process), serves candles (yearly windows), key-ratios fundamentals
      (P/E, P/B, ROE, ROA; the rest stay None), company profile sector, and annual income
      statements (crore converted to rupees; EPS diluted-over-basic; unparseable period labels
      skipped, never guessed). `MergingProvider` + pure merge helpers: prices primary-wins by
      date with secondary gap-fill and per-bar source attribution; fundamentals field coalesce
      with 5% material-disagreement tolerance and logs (no credentials); financial history
      period coalesce with per-row source (yfinance/upstox/merged). `build_default_market_provider()`
      factory: yfinance-only without a token, merged with one; jobs use it. `MarketDataError`
      moved to `providers/base.py` (re-exported for compatibility). Config gains
      `upstox_analytics_token` + `openrouter_api_key` (recognized, not wired); `.env.example`
      documents both.
- [x] **Part G, news:** `services/news_relevance.py` (pure): relevance = long-symbol mention
      (>= 4 chars, word-bounded) OR all distinctive company-name tokens (corporate suffixes
      stripped); blocks generic nouns and unrelated symbol matches ("LT Foods" vs "Larsen &
      Toubro", "HDFC" parent confusion). `GoogleNewsRSSProvider` searches the company full name
      first, falls back to the bare-symbol query only when the name search yields nothing
      usable, applies the same relevance filter + ~30-day freshness to both. Jobs pass the
      catalog name. `/news` applies the display window (`freshness_days` in the response);
      sentiment processing untouched.
- [x] **Verification actually performed:** backend `pytest` **232/232** (77 new: indicator
      series equality, merge helpers + provider fallbacks, mocked-HTTP Upstox incl. token
      hygiene, financial-history job + all five endpoints, news relevance/fallback/freshness);
      migration applied (`alembic current` = head); **real ingestion 50/50 symbols, 228 periods,
      0 errors** via the merged provider (disagreements logged, primary kept); **real 8-stock
      provider quality check** (RELIANCE, TCS, INFY, APOLLOHOSP, HDFCBANK, ICICIBANK, SBIN, LT):
      price bars identical across providers (same 2026-09-04 closes), Upstox fills ROE/ROA gaps
      yfinance omits (RELIANCE/APOLLOHOSP/LT), confirmed yfinance `.info` defects (INFY P/S
      225.5x, ~10x INFY EBITDA error), Upstox P/E differs up to ~15% (basis/window differences),
      Upstox supplies no market cap/P/S/EV/EBITDA absolutes; backend starts and `/health` ok.
- [x] **Landing grid lines:** `.grid-lines` CSS utility (theme-aware `--rule` color, 80px cells)
      applied to the landing root only, per the approved reference; nothing else changed.

**Durable decisions (see PLANNING D56-D60):** the Upstox token is a manually generated Bearer
credential, server-side only; yfinance stays primary (free, no key) with Upstox as gap-filler;
provider merges are pure, tested functions; financial history is never fabricated (nulls and
insufficient_data are contractual); news precision beats recall.

### Session 16 - Phase 6.5: experience overhaul (2026-09-05)

Frontend-only phase (zero backend changes). Executed in parts A-C plus review rounds; see PLANNING D49-D55.

- [x] **Part A, copy discipline:** every em dash and AI-tell word removed from user-visible strings, comments, tests and both docs (scrubs verified at zero); null placeholder "-" site-wide; disclaimers normalized; `Grounded` landing section renamed `ExplainerSection`; DataState className regression from the interrupted first attempt reverted.
- [x] **Part B, typography:** Hanken Grotesk → Instrument Sans, JetBrains Mono → IBM Plex Mono (500/600/700 only, no 400 face), Libre Caslon kept; 12px floor everywhere (54 sub-12px instances removed); `.num` weight 500 floor; `.label-caps` 12px/600; chart canvas font swapped; per-role weight fixes (table cells, metadata labels, nav) without a global bump; light mode inherits identical floors.
- [x] **Part C, palette:** dimension accent tokens (jade/amber/coral/teal) wired through Framework cards, Hero chips, structure rows, universe bars and the signal diagram; dark-first default via ThemeProvider.
- [x] **Review round 1 (feedback applied):** dark theme re-skinned to "Warm Ink + Gold" at token level (warm near-black surfaces, off-white ink, gold identity); three stock photos replaced by authored SVG plates (CandleField, UniverseGrid) after the photographic treatment was rejected; all blend modes and 660 KB of images removed (frame-rate fix); sub-12px and blend-mode scans clean.
- [x] **Review round 2 (feedback applied):** market pulse → continuous marquee of ALL 50 constituents (transform-only, pause on hover, reduced-motion static row); CandleField hover/tap interactive with illustrative OHLC readout; NumbersToSignal flows made equal-length, symmetric, dimension-colored and touching the pulse origin; metric chips spring-hop on hover; framework cards clickable with accent borders + weight-row dim logic; UniverseGrid rebuilt as fifty equal bars; ScrollPulse right rail added (uniform sine, arc-length-exact dot, reduced-motion hidden); glass panels, static washes, section tint rhythm, keyword highlights (`.hi`), logo slots in UniverseStrip, blue ticker treatment, `.chart-frame` boxes; PriceChart crosshair strengthened (dashed faint lines, petrol labels) so hover feedback is visible in light mode.
- [x] **Review round 3 (palette regrade):** light mode graded from the approved reference concept (bg #f8f9ff, cards #fff, ink #0b1c30, petrol identity #006781, borders #ccd5e6/#b7c5de); dark "Warm Ink + Gold" reverted to and kept exactly as approved.
- [x] **Verification actually performed:** `tsc -b` clean; vitest **43/43** (5 new `pickTopMovers` tests: magnitude ranking, cap, value integrity, non-finite rejection, empty); `vite build` OK (landing chunk 56.8 kB / gz 17.0); **zero raster images in dist** and zero blend modes (only the pre-existing sticky-header blur); marquee/rail/reveals honor `prefers-reduced-motion`; pulse math checked against the live `/api/v1/stocks` response (top movers match `pickTopMovers` exactly); servers restarted and re-verified (root 200, deep link 200, `/api` proxy 200, backend `/health` ok).
- [x] **Pushed:** commit `3efb78d` on `main` (58 files); `Refine design concept(2)/` added to `.gitignore` with the other local-only reference folders.

**Durable decisions (see PLANNING D49-D55):** copy discipline is a hard rule; typography has a 500
weight + 12px floor with no 400 mono face loaded; dimension accents never touch raw metrics; light
"Cloud White + Petrol" and dark "Warm Ink + Gold" are both approved and independently frozen; no
photographs, authored SVG plates instead; motion budget = opacity/transform only, reduced-motion
everywhere; crosshair visibility is part of chart DoD.

### Session 15 - Phase 6: production frontend + backend gaps (2026-09-04)

**Backend additions (4, smallest-coherent; no refactor of existing code):**
- [x] **CORS** - `cors_origins` setting (comma-separated, default `http://localhost:5173`, empty disables) + `CORSMiddleware` in `main.py` (GET/POST). `.env.example` documents `CORS_ORIGINS`.
- [x] **`GET /stocks/{symbol}`** - fills the PLANNING §9 contract gap: profile (name/sector/industry) + quote block (last_price, change_abs/pct, open/high/low, prev_close, volume, bar date) + market_cap from the financials snapshot. Fields are **null when data is absent** - nothing fabricated.
- [x] **`GET /stocks/{symbol}/technicals`** - raw SMA20/EMA12/RSI14/MACD(line/signal/histogram) + the existing trend/momentum/reversion sub-scores + score; reuses `services/indicators.py` (no duplicated math); `insufficient_data` flag under 26 closes.
- [x] **`POST /stocks/{symbol}/explain`** - grounded contextual explanations for 5 FIXED question types (alpha/technical/valuation/fundamental/sentiment). Reuses Phase 5 architecture: per-type fact **allow-lists** (`_ALLOWED_FACT_KEYS`), alpha facts reuse `llm_narrative._alpha_facts()` verbatim, output contract prompt, rule-based fallback on every path (facts unavailable / no key / no model / budget / provider error), in-process TTL cache, **shared daily cap** with `/alpha` (new public `budget_ok()`/`register_llm_call()` in `llm_narrative.py`). Not a chatbot: no free text, fixed types only; unsupported type → 422 envelope.
- [x] Tests: `test_stock_detail_technicals.py` (12: detail/quote/market-cap/null-quote/404, technicals vs pure functions/insufficient/404, CORS preflight allowed+methods/disallowed-origin) + `test_explain_api.py` (11: all 5 question types rule-based, 404, 422, insufficient-data, LLM path w/ grounded prompt assertion, TTL cache, budget cap, allow-list strips unknown keys). **Full suite: 155/155 passed** (133 baseline + 22 new), zero-network.

**Frontend (`frontend/`, new):**
- [x] **Stack:** Vite 6 + React 19 + TypeScript (strict), Tailwind CSS v4 (`@tailwindcss/vite`), shadcn-style primitives (button/badge/tooltip/popover/tabs/collapsible/skeleton/input over Radix), TanStack Query v5 + TanStack Table v8, React Router v7 (lazy route chunks), Framer Motion 12, TradingView **Lightweight Charts v5** (candlesticks, crosshair OHLC legend, theme-aware, ResizeObserver), lucide-react, self-hosted **@fontsource** tri-font (Libre Caslon Text display / Hanken Grotesk body / JetBrains Mono data).
- [x] **Design tokens (`src/index.css`):** light **Warm Paper + Cobalt** default + **Deep Ink + Jade** dark as a genuine alternate token system (`@custom-variant dark`), band tokens (strong/positive/moderate/weak/veryweak) consumed only by analytical conclusions; raw metrics neutral. Class-based toggle in the site header.
- [x] **Foundations:** typed API client (`lib/api.ts`) with `ApiError` parsing the backend error envelope (status/code/detail; `isNotFound`/`isNoPeers`/`isInsufficientData`); wire-format types (`lib/types.ts`); Indian formatters (₹ grouping, lakh/crore compact, signed pct); semantic system (`lib/semantic.ts`: `scoreBand` 80/60/40/20, `valuationSemantics` (independent of Alpha), `technicalVerdict`, `sentimentSemantics`); **METRIC_INFO registry + InfoDot** (tooltip short def → popover methodology → expandable longer context) covering 30+ metrics; **DataState** (loading skeletons / empty / insufficient / stale as-of / API error+retry / unknown-symbol); per-endpoint TanStack Query hooks with keyed caching + targeted retry (404/NO_PEERS/INSUFFICIENT_DATA never retry).
- [x] **Landing page:** editorial story (RAW NUMBERS → STRUCTURE → ANALYSIS → RESEARCH → SIGNAL): hero with real 6-month RELIANCE sparkline + Alpha object, numbers-cloud→structure choreography, four-inputs→Alpha convergence (weights, valuation kept separate), score-responsive Alpha states (82/59/34 labeled examples), grounded-explanation panel, **live product preview** (real detail/alpha/technicals/prices via the API with honest DataState), live Nifty-50 universe strip (featured names from the real catalog), honest Equities/ETF/MF roadmap, expandable methodology, quiet CTA. Motion = reveals, count-ups, chart draw, component convergence only.
- [x] **Markets:** server-paginated table (API page/limit; DOM bounded to one 25-row page), sector filter via the API param, TanStack Table columns, semantic day-change color only.
- [x] **Screener:** the exact backend filters (status select, min profitability/solvency inputs clamped 0-100), scored cells with mini bars, valuation-state badges, honest empty state.
- [x] **Stock detail (`/stocks/:symbol`, deep-linkable):** header (identity, price+change, market cap, OHLC stats, as-of date, AskPanel) → Alpha (composite + weighted component bars + technical evidence sub-scores + value signal chip + grounded explanation + "Why is Alpha X?") → Valuation (tabbed metric; verdict + relative-position marker vs peer median; **all four multiples P/E, EV/EBITDA, P/B, P/S each with its own backend peer median**; expandable EV/EBITDA/market-cap inputs; NO_PEERS/INSUFFICIENT_DATA states) → Fundamentals (profitability/solvency scores + per-ratio threshold bars) → Price (Lightweight Charts, 1M-2Y) + Technical Positioning (verdict word - technical evidence only - + sub-scores + SMA/EMA/RSI/MACD readings with interpretations + heuristic disclaimer + "Why?") → News & Sentiment (net sentiment + expandable articles with labels) → compact methodology. Contextual **ExplainAction** ("Why?") + **AskPanel** (5 fixed grounded questions) - no chatbot UI.
- [x] **Methodology page:** documented weights/thresholds table, technicals-heuristic disclaimer, valuation-vs-Alpha separation, data freshness, no-fabrication policy.
- [x] Tests (Vitest + RTL, jsdom): 38 - formatters (null-safe, Indian grouping), semantic bands/verdicts, API client (envelope parsing, network error, query shapes), DataState states, InfoDot content, ScoreBlock banding, METRIC_INFO completeness.
- [x] **Verification actually performed:** `npx tsc -b` clean; `vitest run` **38/38**; `vite build` OK (per-page chunks; landing 31.9 kB gz 8.7, stock page 47.4 kB gz 14.0); **live integration**: uvicorn :8000 + `vite` :5173 - `/health` ok; direct API with `Origin: http://localhost:5173` returns `access-control-allow-origin`; OPTIONS preflight 200 (GET,POST); `GET /stocks/RELIANCE` real quote (₹1,322.00, +0.46%, mcap ₹17.9L Cr, bar 2026-08-18); `/technicals` score 55 (SMA20 1302.9, RSI14 54.3, MACD hist +1.91, 200 closes); `POST /explain` technical → rule-based grounded text; bad question_type → 422; `/valuation?metric=EV_EBITDA` → 11.64 vs 5.77 overvalued (1 peer); `/alpha` composite 59 (70/55/48) with populated explanation; `/screener?status=undervalued&min_profitability=50` → 13 matches; unknown symbol → 404; Vite serves `/` and deep link `/stocks/RELIANCE` (200) and proxies `/api` to the backend.

**Durable decisions (see PLANNING D40-D48):** markets page paginates server-side; stock detail composes
multiple focused endpoints (one per section) rather than one mega-endpoint; every valuation multiple
has its own query so peer medians show for all four simultaneously; the frontend never recomputes
backend math (EV/EBITDA comes only from the valuation endpoint); verdict wording lives client-side
(presentation), values/evidence live backend-side; design-reference folders git-ignored (local-only).

### Session 14 - Phase 5: grounded LLM explanation (2026-08-21)
- [x] **`app/config.py`** - added `llm_api_key`, `llm_base_url` (default `https://openrouter.ai/api/v1`), `llm_model` (**empty = LLM disabled**), `llm_daily_cap` (default 100). `.env.example` documents the OpenRouter key + a sample free model + cap note.
- [x] **`app/providers/llm_base.py`** - `LLMProvider` ABC + `LLMResult` (`text`, `tokens_used` optional, `model`) + `LLMError`. Provider returns the structured result (no separate usage reconstruction).
- [x] **`app/providers/openrouter_provider.py`** - raw **async httpx** → OpenAI-compatible `POST /chat/completions` (no OpenAI/Anthropic SDK). Low temperature 0.2; parses `usage.total_tokens` + echoed `model`; non-2xx / invalid-JSON / missing choices / empty text → `LLMError`.
- [x] **`app/services/llm_narrative.py`** - **`_alpha_facts()` explicit allow-list** (never `AlphaResult.__dict__`/`asdict`); `build_alpha_prompt()` returns (`system`=output contract, `user`=JSON facts only); `_alpha_narrative()` rule-based fallback. `generate_alpha_explanation()`: TTL cache → disabled-check (no key/model) → budget check → provider call → fallback on `LLMError`. **Placed here, not `explanation.py`**, to avoid the import cycle `alpha → analysis → explanation → alpha`.
- [x] **Output contract** enforced in the system prompt (short text ≤3 sentences, no invented numbers, no investment advice, no guaranteed future-return claims, "not investment advice" tag). No second model polices output - prompt boundary + tests are the guardrail (D-less design choice, see PLANNING D39).
- [x] **`app/routers/alpha.py`** - `AlphaResponse` gains `explanation: str`; wired via `generate_alpha_explanation(stock, result)`.
- [x] Tests: **`tests/test_llm.py` (15)**: allow-list exact keys, free-text exclusion, prompt grounding, output-contract instructions, no-key / no-model / provider-error / budget-cap fallbacks, provider-success path, TTL cache (provider called once), cost-logging (tokens + None-safe), OpenRouter success / non-2xx / malformed / invalid-JSON (mocked httpx, zero network). **`tests/test_alpha.py`** extended: endpoint asserts `explanation` is a non-empty string.
- [x] **Full suite: 133/133 passed** (118 existing + 15 new), network-free.
- [x] **Coverage: 78%** (up from 76%). New modules: `llm_narrative.py` 95%.
- [x] **Live verification (Postgres back up):** `GET /api/v1/stocks/RELIANCE/alpha` → 200, composite 59, `explanation` populated via rule-based fallback (no LLM key configured); `llm_disabled reason=no_key` logged; second TCS call hit `llm_cache hit` (TTL cache works), same explanation returned; snapshot persisted.
- [x] **LLM key stays unset in `.env`** - the free-model availability check is left as a manual `.env` step; the app degrades gracefully by design.

### Session 13 - Phase 5 partial / Postgres environment blocker (2026-08-21)
- The session began with **PostgreSQL failing to accept connections** on Windows: the postmaster bound port 5432 but **every backend worker died with `0xC0000142` (STATUS_DLL_INIT_FAILED)** - logged as `server process (PID ...) was terminated by exception 0xC0000142`, with the Postgres hint "antivirus, backup, or similar software interfering". Evidence recorded: `psql: server closed the connection unexpectedly`, `ConnectionRefusedError [WinError 1225]` in pytest-backed tests.
- DB-backed verifications were **blocked**, not failed. Pure/network-free work completed and verified first (71 pure tests + 19-point direct verification script). Postgres later recovered (clean `pg_postmaster_start_time`); DB-backed steps then ran green.
- **No PostgreSQL / antivirus / security settings were modified.**

### Session 12 - Phase 4: technical indicators + Alpha Score (2026-08-19)
- [x] `app/services/indicators.py` - pure functions: SMA20, EMA12 (SMA-seeded), RSI14 (Wilder, avgLoss=0→100), MACD 12/26/9 (line/signal/histogram). `score_technicals()` = trend 50% + momentum 30% + reversion 20%, renormalized over available components, bounded 0-100.
- [x] `app/models.py` - `AlphaScore` (symbol, date, fundamental/technical/sentiment/composite Numeric, `components_json` JSONB, updated_at; `UNIQUE(symbol,date)`). Migration `b0f48fb7c939`.
- [x] `app/repositories/prices.py` - added `get_close_series(stock_id, limit)` (chronological closes for indicators).
- [x] `app/repositories/alpha.py` - `get_latest` + `upsert_snapshot` (idempotent ON CONFLICT by symbol+date, refreshes updated_at).
- [x] `app/services/alpha.py` - composite = 40% fundamental + 30% technical + 30% sentiment, weights renormalized over available components; fundamental = mean(profitability, solvency) via `analysis.compute_stock_scores` (reused); sentiment from `news_repo.get_sentiment_summary` mapped -1..+1→0..100; **valuation kept separate** as `value_signal` (via `analysis.compute_stock_valuation`, swallowed NoPeers/Insufficient so alpha never fails).
- [x] `app/routers/alpha.py` - `GET /api/v1/stocks/{symbol}/alpha`; persists a snapshot at compute time.
- [x] Tests: `test_indicators.py` (16) + `test_alpha.py` (11). **Full suite: 118/118 passed.**
- [x] **Live verification:** TCS → composite 59 (fund 98/tech 27/sent 39 → 0.4·98+0.3·27+0.3·39=59.0 ✓), value_signal fairly_valued P/E 16.56 vs 17.31, components explain the low technical (weak trend 31.4 / momentum 3.8). Snapshot persisted.
- [x] Coverage rose to **76%** (from 74%).

### Session 11 - Phase 3: news RSS + FinBERT sentiment (2026-08-19)
- [x] **Deps:** torch (CPU), transformers 5.15, feedparser 6.0.14 added to requirements. FinBERT model `ProsusAI/finbert` downloaded (~420MB, cached by huggingface).
- [x] `app/models.py` - `NewsArticle` (unique `uq_news_articles_url`, timezone-aware `published_at`) + `NewsSentiment` (1:1, unique `uq_news_sentiment_article_id`, score/label/model).
- [x] Migration `ed7bb907ca7c` ("add news tables") generated + applied.
- [x] `app/providers/news_base.py` - `NewsProvider` ABC + `Article` dataclass (mirrors `MarketDataProvider`).
- [x] `app/providers/rss_provider.py` - `GoogleNewsRSSProvider` (feedparser via `asyncio.to_thread`, `NewsProviderError`, query strips `.NS` suffix).
- [x] `app/providers/sentiment.py` - `FinBERTScorer` (lazy, **thread-locked** pipeline singleton; `score_text_async` off the event loop).
- [x] `app/jobs.py` - `ingest_news()`: fetch → `ON CONFLICT DO NOTHING` upsert by URL (race-safe under concurrent symbols) → score unscored articles. `_with_retry` + per-symbol isolation reused. Wired into `_ingest_all`.
- [x] `app/repositories/news.py` - `get_articles` (eager sentiment, newest first) + `get_sentiment_summary` (weighted net score -1..+1).
- [x] `app/routers/news.py` - `GET /stocks/{symbol}/news` + `GET /stocks/{symbol}/sentiment`; registered in main.py.
- [x] `tests/test_news.py` - 7 tests (fake provider + fake scorer, no network): insert+score, idempotency, failure isolation, both endpoints, 404, no-news.
- [x] **Full suite: 91/91 passed.**
- [x] **Live run:** 50/50 symbols, **1,001 articles ingested + all scored** (219 pos / 159 neg / 623 neutral). Re-run fully idempotent (0/0/0). Live endpoints verified (RELIANCE: 20 articles, sentiment score -0.0392/neutral).

### Session 10 - P2.5 Hardening (2026-08-18)
- [x] **N+1 eliminated in `list_stocks`** - new `repositories/prices.py:get_two_latest` (one `ROW_NUMBER()` window query) replaces the per-stock loop. `list_stocks` = 3 queries total. Guarded by query-count test (`test_list_stocks_query_count_is_bounded` asserts ≤5).
- [x] **N+1 eliminated in screener/valuation** - new `repositories/financials.py:get_financials_batch` (single `IN` query) replaces per-peer financials lookup.
- [x] **Analysis service extracted** - `services/analysis.py` centralizes `compute_stock_valuation` / `compute_stock_scores` / `analyze_stock`; `valuation.py` + `scores.py` + `screener.py` routers are now thin. Pure math stays in `valuation.py`/`scores.py`.
- [x] **`financials.updated_at` refreshed on upsert** - `jobs.py` upsert `set_` now includes `func.now()`. Test asserts it moves on re-ingest.
- [x] **Retry-with-backoff** - `jobs.py:_with_retry` wraps provider fetches (prices + financials), 2 retries, exponential backoff, isolates on final failure (D19 preserved). Tests: transient-fails-then-succeeds (3 calls) + always-fails (1 error, no crash).
- [x] **Request-id structured logging** - `app/logging_utils.py` contextvar + ASGI middleware; every request logs `request_id/method/path/status/duration_ms`; `X-Request-ID` response header; `request_id` added to error envelope.
- [x] **Missing tests added** (`tests/test_hardening.py`, 8): EV_EBITDA/PB/PS via HTTP, industry-NULL→sector fallback, no-financials `/fundamentals`, query-count guard, `updated_at` refresh, retry behavior.
- [x] **Coverage baseline** - `pytest-cov` added; **74% overall** (84 tests). Low spots intentional: `seed.py` 0% (ops script, needs network), `yfinance_provider.py` 20% (providers mocked per §12).
- [x] **Measured results recorded** - live: `GET /stocks` (50 rows) ~489ms, `GET /screener` (full 50) ~467ms (first-call incl. pool warmup). `list_stocks` query count bounded at 3 (was ~2N+1).
- [x] **Full suite: 84/84 passed.**

### Session 9 - Phase 2 SP3: repositories + routers + screener (2026-08-18)
- [x] `app/seed.py` - added `backfill_industry()` (batched, idempotent, per-symbol isolation). **Ran: 49/50 industry populated** (TATAMOTORS.NS 404 → sector fallback). Industry groups: 6 banks, 5 IT, 5 auto, etc.
- [x] `app/repositories/stocks.py` - `get_stock`, `get_peers` (industry → sector fallback), `list_all_symbols`.
- [x] `app/repositories/financials.py` - `get_financials_row`, `to_key_ratios`, `get_financials` (ORM→`Fundamentals`).
- [x] `app/errors.py` + `app/main.py` - new handlers: `NoPeersError`→409 `NO_PEERS`, `InsufficientDataError`→422 `INSUFFICIENT_DATA`.
- [x] Routers: `fundamentals.py`, `scores.py`, `valuation.py` (+explanation), `screener.py`; `common.py` (symbol normalize/resolve).
- [x] Route registration verified - 8 API paths in OpenAPI spec.
- [x] Tests: `test_repositories.py` (7) + `test_analysis_api.py` (11). **Full suite: 76/76 passed.**
- [x] **Live smoke test vs real DB:** TCS valuation → P/E 16.56 vs 4 IT peers (median 17.31, fairly valued); TCS scores (profitability 97, solvency 100); screener surfaces 16 undervalued stocks.

### Session 8 - Phase 2 SP2: scoring + valuation + explanation services (2026-08-18)
- [x] `app/services/scores.py` - §8b piecewise-linear scoring: `_linear()` helper, `profitability_score()`, `solvency_score()`, `ComponentScore`/`Component`; weight renormalization + missing/negative handling.
- [x] `app/services/valuation.py` - `compute_multiple()` (PE/EV_EBITDA/PB/PS), `relative_valuation()` (peer median, margin, ±5% bands), domain exceptions `NoPeersError`/`InsufficientDataError` defined in the service layer (per approved design).
- [x] `app/services/explanation.py` - rule-based `profitability_explanation`/`solvency_explanation`/`valuation_explanation` from real components.
- [x] Tests: `test_scores.py` (16), `test_valuation.py` (17), `test_explanation.py` (7) - 44 new, all pure/unit, no DB/network.
- [x] **Full suite: 60/60 passed.**

### Session 7 - Phase 2 SP1: financials model + provider + ingestion (2026-08-18)
- [x] `app/models.py` - added `Financials` model (one row/stock, `UNIQUE(stock_id)` `uq_financials_stock_id`; valuation + profitability + solvency columns, `updated_at`).
- [x] Migration `5f7fd30113b1` ("add financials table") generated + applied; verified in Postgres.
- [x] `app/providers/base.py` - added `Fundamentals` dataclass (raw provider values) + abstract `get_fundamentals()`.
- [x] `app/providers/yfinance_provider.py` - implemented `get_fundamentals()` mapping yfinance `info`; `_as_float()` helper guards NaN/inf/string values → None.
- [x] Verified provider: `RELIANCE.NS` (P/E 23.9, EV 21T, EBITDA 1.8T) + `TCS.NS` (ROE 47.7%).
- [x] `app/jobs.py` - added `ingest_financials()` (batched, per-symbol isolation, upsert on `uq_financials_stock_id`) + `_ingest_all()` (prices then financials) wired into scheduler.
- [x] `tests/test_financials.py` - 5 tests: interface compliance, fake-provider values, upsert, idempotency, failure isolation.
- [x] Real ingestion: **50/50 rows**, re-run idempotent (stays 50). Prod prices/stocks untouched.
- [x] **Full suite: 20/20 passed** (~6s, no network).
- [x] **Data insight:** yfinance `info` often omits `return_on_equity`/`interest_coverage` per symbol → scoring renormalization (drop missing, reweight) is essential.

### Session 6 - pytest suite (2026-08-18)
- [x] Created `signaldesk_test` database (isolated from prod `signaldesk`).
- [x] `backend/pytest.ini` - `asyncio_mode=auto`, `pythonpath=.`, `testpaths=tests`.
- [x] `tests/conftest.py` - function-scoped test engine, per-test schema rebuild (`drop_all`/`create_all`), `app.dependency_overrides[get_session]` → test factory, httpx ASGI client, `seeded` fixture.
- [x] `tests/test_stocks_api.py` - 11 tests: health, list (default/sector/pagination/last_price/change), price history (bare symbol/suffix/range), 404 + 422 error envelopes.
- [x] `tests/test_providers.py` - 4 tests: fake provider OHLCV mapping, `MarketDataError` raise, interface compliance, `ingest_universe` failure isolation (D19).
- [x] **Result: 15 passed, 0 failed** in ~6s. No network calls (fake provider used; yfinance only instantiated).
- [x] Confirmed prod `signaldesk` untouched (24,499 bars / 50 stocks unchanged).

### Session 5 - API endpoints + error handling + startup (2026-08-18)
- [x] `app/errors.py` - `NotFoundError`(404), `ValidationError`(422), error-envelope builders, and handlers.
- [x] `app/routers/stocks.py` - `GET /api/v1/stocks` (pagination, sector filter, `last_price`/`change_pct` from latest two bars) + `GET /api/v1/stocks/{symbol}/prices` (range filter, symbol normalization, resample=1d only).
- [x] `app/main.py` - FastAPI app, registered handlers, included router under `/api/v1`, `/health`, scheduler via **lifespan**.
- [x] Verified all endpoints + error envelopes via httpx ASGI (8 checks passed).
- [x] Confirmed Swagger spec (`/openapi.json`) lists all 3 endpoints.
- [x] Confirmed the 5 DoD-required stocks each have 500 bars.

### Session 4 - yfinance provider + Nifty 50 ingestion (2026-08-18)
- [x] `app/providers/base.py` - `MarketDataProvider` ABC with `OHLCV`/`StockProfile` dataclasses (D16 swappable sources).
- [x] `app/providers/yfinance_provider.py` - yfinance implementation, async via `asyncio.to_thread`, raises `MarketDataError`.
- [x] Verified provider returns real OHLCV + profile for `RELIANCE.NS`.
- [x] `app/data/nifty50.py` - 50 Nifty 50 constituents (`.NS` suffix + name + sector). Fixed a duplicate (`HINDALCO` ×2 → `UPL`).
- [x] `app/seed.py` - idempotent seed → `stocks` (50), `universes` (nifty50), `stock_universe` (50 links). Re-run adds 0.
- [x] `app/jobs.py` - `ingest_universe()` (reads universe from DB, batches via `asyncio.gather`, per-symbol isolation, Postgres upsert) + APScheduler `start_scheduler()`.
- [x] Ingested **24,499 daily price bars** across 49 stocks (~500 trading days each, 2y period).
- [x] **Idempotency verified:** re-run → count unchanged (24,499 → 24,499).
- [x] **Failure isolation verified:** fake provider raising on `RELIANCE.NS` → logged, run continued (`errors: 1`).
- [x] Scheduler start/stop verified.

### Session 3 - App scaffold (2026-08-18)
- [x] `app/__init__.py` - marks `app` as an importable package.
- [x] `.env.example` (committed template) + `.env` (real values, git-ignored).
- [x] `app/config.py` - pydantic-settings `Settings`; requires `APP_ENV` + `DATABASE_URL`; optional keys default empty.
- [x] `app/db.py` - async engine, `async_sessionmaker`, `Base`, `get_session` dependency.
- [x] `app/models.py` - `Stock`, `Universe`, `stock_universe` (many-to-many), `DailyPrice` (Numeric(16,4), `UNIQUE(stock_id,date)`).
- [x] Alembic initialized; `env.py` made **async**; initial migration `8bf8964e941a` generated + applied.
- [x] Verified in Postgres: 4 tables present; `uq_daily_prices_stock_date` unique constraint confirmed.
- [x] End-to-end smoke test: insert stock+universe, link them, insert daily price, read back via relationship, FK-safe rollback. **Passed.**
- [x] `.gitignore` + `git init` at `signaldesk/` (no commit). `.env` confirmed git-ignored; `.env.example` tracked.
- [x] Idempotency: re-running `alembic upgrade head` is a no-op.

### Session 2 - Environment setup (2026-08-18)
- [x] Checked system: Python 3.12.10, Node v24.13.1, git 2.53, winget available.
- [x] PostgreSQL **17.11** installed (binaries zip - EDB installer CDN blocked automated download).
- [x] Initialized cluster with `initdb` (superuser `postgres`, password `postgres`, scram-sha-256).
- [x] Started server via `pg_ctl` (currently running, PID 29732).
- [x] Created `signaldesk` database.
- [x] Created project tree at `Desktop/Projects/signaldesk/backend/` with `app/` subpackages.
- [x] Created `.venv` virtualenv (Python 3.12.10).
- [x] Wrote `backend/requirements.txt` and installed all deps.
- [x] Verified all imports: fastapi, uvicorn, sqlalchemy, asyncpg, alembic, pydantic_settings,
      apscheduler, yfinance, pandas, numpy, httpx, pytest.
- [x] **Data source verified:** `yfinance` returns `RELIANCE.NS` prices + sector + P/E.

### Session 1 - Planning (2026-08-17)
- [x] Full product, scope, architecture, and roadmap decisions recorded in `PLANNING.md` (D1-D15).

---

## 3. In Progress / Next Steps

### Phase 7: Observability (next up per roadmap §14)
- Structured logging, stale-data flags surfaced via API (`stale: true`), `/debug/jobs`.
- Optional: aggregate `/overview` endpoint (tracked in §18 - was not needed for Phase 6; the landing preview composes existing endpoints).
- Redis stays deferred/conditional.

### Phase 6 recap (done - production frontend + 4 backend additions)
- Frontend runs with: backend `uvicorn app.main:app` + `frontend/` `npm run dev` (Vite proxies `/api` → :8000; or set `VITE_API_BASE` for direct/CORS access).
- Enable the LLM live for `/alpha` + `/explain`: set `LLM_API_KEY` + a currently-available `LLM_MODEL` in `backend/.env` (rule-based fallback otherwise, by design).
- ETFs/Mutual Funds remain honest roadmap sections (no fake capabilities); auth deliberately absent.

### Phase 5 recap (done - grounded LLM explanation)
- LLM provider abstraction (`LLMProvider`, `LLMResult`, `OpenRouterProvider`) - prompt **only with allow-listed computed facts** via `_alpha_facts()`.
- Wired into `/alpha` (explanation), `/explain` (five fixed question types) and `/ask` (Part H single-shot questions).
- LLM mocked in tests (FakeLLMProvider + mocked httpx); rule-based fallback always available.
- In-process TTL cache + SHARED daily cap + cost logging; Redis deferred.
- **To enable the LLM live:** set `LLM_API_KEY` (or `OPENROUTER_API_KEY`, accepted as an alias) + a currently-available `LLM_MODEL` in `backend/.env` (see `.env.example`). The ask endpoint additionally verifies the model against the OpenRouter catalog before its first real request.

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
.\.venv\Scripts\python.exe -m app.jobs backfill                        # recompute the whole alpha history (replaces snapshots per symbol)
.\.venv\Scripts\python.exe -m app.jobs ingest                          # run the full daily ingestion pass (prices, financials, periods, profiles, repair, backfill, pre-warm, news)

# --- Tests ---
cd C:\Users\shyam\Desktop\Projects\signaldesk\backend
.\.venv\Scripts\python.exe -m pytest -v                            # run full suite (test DB, no network)
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term    # coverage report

# --- Frontend (Phase 6) ---
cd C:\Users\shyam\Desktop\Projects\signaldesk\frontend
npm install                                                         # install deps
npm run dev                                                         # Vite dev server (:5173, proxies /api -> :8000)
npm run typecheck                                                   # tsc -b (strict, zero errors expected)
npm run test                                                        # vitest run (38 tests, jsdom)
npm run build                                                       # tsc -b && vite build (per-page chunks)
npm run preview                                                     # serve the production build

# --- Git (commit + push after each phase) ---
cd C:\Users\shyam\Desktop\Projects\signaldesk
git add -A
git commit -m "Phase X: description"
git push
```

---

## 5. Environment Reference

| Item | Value |
|---|---|
| Project root | `C:\Users\shyam\Desktop\Projects\signaldesk` |
| Backend | `backend/` (venv at `backend/.venv`) |
| Frontend | `frontend/` (Node ≥ 20; built with Node 24) |
| Postgres binaries | `C:\Users\shyam\PostgreSQL\bin` |
| Postgres data dir | `C:\Users\shyam\PostgreSQL\data` |
| Postgres superuser | `postgres` / `postgres` (dev only) |
| Database | `signaldesk` |
| DB connection (expected) | `postgresql+asyncpg://postgres:postgres@localhost:5432/signaldesk` |
| Planning doc | `C:\Users\shyam\Desktop\Projects\signaldesk\PLANNING.md` |
| Progress doc | `C:\Users\shyam\Desktop\Projects\signaldesk\PROGRESS.md` |
| GitHub repo | `https://github.com/shyam-029/SignalDesk` (public) |

---

## 6. Known Gotchas & Decisions Made

- **Never rewrite repo .md files with PowerShell text processing** - PS 5.1 `Get-Content`/`Set-Content`
  mangles UTF-8 (→ mojibake + BOM). Use the editor/edit tool for .md files; if corrupted,
  `git checkout -- <file>` restores.
- **A long-running uvicorn process serves OLD code** - new endpoints return a bare 404 (no error
  envelope) until the server is restarted; the frontend then misreports it as a network failure.
  After pulling changes, restart the backend (`python -m uvicorn app.main:app --port 8000`). Hit
  in Session 20: the ask panel showed "could not be reached" because the running server predated
  Part H.
- **Charts must not be built at zero width** - collapsible sections keep content mounted with
  `hidden`, so chart components gate creation on `el.clientWidth > 0` (ResizeObserver) and
  rebuild on visibility. A chart created at width 0 renders squished/offset until a rebuild.
- **Alpha backfill replaces a symbol's snapshots** (Session 20): `_backfill_one_alpha` deletes the
  symbol's rows before inserting the recomputed series - that is what makes formula changes propagate.
  Live /alpha requests rebuild today's snapshot on the next page view, so the daily job stays safe.
- **`OPENROUTER_API_KEY` is an alias for `LLM_API_KEY`** (AliasChoices in config.py). The dev .env
  only set the former, which silently disabled the LLM until Session 20 wired the alias.
- **The ask endpoint's evidence sufficiency is explicit** - a bare stock must carry NO alpha block
  (composite None) or `has_min_evidence` treats the all-null dict as data and skips the honest
  "insufficient" state.
- **PostgreSQL is 17.11, not 16** - decided to keep 17 (newer). Documented in PLANNING (D20).
- **EDB automated downloads are geo/network-blocked** (403 via CloudFront) - must use the
  `sbp.enterprisedb.com/getfile.jsp?fileid=...` tokenized binaries links if reinstall needed.
- **pip install timed out once** at 10 min during "Installing collected packages" - the download cache
  was warm, so a re-run finished in seconds. If interrupted, just re-run the same install command.
- **Redis intentionally not installed** - only needed at the P1 caching phase. Defer.
- **Docker not installed** - not needed until Semester 2.
- `pip` writes notices to stderr; PowerShell may show red "error" lines that are not errors.
- **Alembic env.py is async** - never switch it back to the sync default or migrations will fail with asyncpg.
- **Delete rows in FK-safe order** - when deleting a stock that's linked in `stock_universe`, delete the
  association rows *first* (child/parent order), or Postgres raises a `ForeignKeyViolationError`.
- **Cleaning test data:** `TRUNCATE daily_prices, stock_universe, stocks, universes RESTART IDENTITY CASCADE;`
- **Initial migration is `8bf8964e941a`** ("initial schema").
- **Never lazy-load relationships in async code** (`MissingGreenlet`). Use `selectinload()` or query the
  association table directly. Hit in `seed.py` - fixed by querying `stock_universe` directly.
- **`TATAMOTORS.NS` returned no data from yfinance** (transient Yahoo issue) - gracefully skipped by
  ingestion (D19 isolation). Not a code bug; may resolve on a later run.
- **`INSERT ... ON CONFLICT DO UPDATE`** (via `pg_insert`) is how `daily_prices` stays idempotent. If the
  unique constraint name changes, update the `constraint=` argument in `jobs.py`.
- **pytest-asyncio event-loop affinity:** asyncpg connections are bound to the event loop that created
  them; pytest-asyncio gives each test its own loop, so the test engine fixture MUST be **function-scoped**
  (session-scoped async engine → "another operation is in progress" errors). Hit in the first test run.
- **Dependency override is how tests redirect the DB** - `app.dependency_overrides[get_session]`; never
  touch the prod engine. Tests must also monkeypatch `app.jobs.SessionLocal` if they call `ingest_universe`.
- **Test DB `signaldesk_test`** - created via `createdb`; schema rebuilt per-test via
  `Base.metadata.drop_all/create_all` (no Alembic needed in tests).
- **Postgres `Numeric` returns `Decimal`** - comparing ORM values in tests must use `Decimal(...)`, not float
  (`Decimal('0.1500') == 0.15` is `False`). Hit in `test_financials.py`.
- **yfinance `info` omits many metrics per symbol** (e.g. `return_on_equity`, `interest_coverage` often
  missing; `TATAMOTORS.NS` intermittently 404s) - scoring MUST handle missing components via renormalization.
- **New migration `5f7fd30113b1`** ("add financials table"); financials upsert targets `uq_financials_stock_id`.
- **NULL classifier in SQL → no rows** - `column == None` is a SQL NULL comparison (never true). When falling back
  to `sector`, must compare against `stock.sector` (a real value), not `None`. Hit in `repositories/stocks.py`.
- **Industry was NULL in seed** - backfilled 49/50 via `seed.backfill_industry()`. Re-run if the catalog widens.
- **Screener is O(n²) over peers** (fine for 50-500 stocks; revisit if scaling to the full market).
- **FastAPI 0.141 mounts included routers as `_IncludedRouter`** (path shows `None` when iterating
  `app.routes`) - the real paths still work; check `/openapi.json` to confirm route registration.
- **`range` param shadows Python's builtin `range`** in `stocks.py` (intentional for the API contract).
- **`resample` is 1d-only in v1** (D-flag); weekly/monthly aggregation deferred.
- **SQLAlchemy async engines don't support `before_cursor_execute` events** - attach listeners to
  `engine.sync_engine` instead (query-count tests). Hit in `test_hardening.py`.
- **Batch methods live in repositories** (`get_two_latest`, `get_financials_batch`) - the N+1 guards
  depend on them; keep per-stock loops out of routers.
- **Analysis logic lives in `services/analysis.py`** - routers must not re-implement the valuation/
  scoring flow (audit finding). Pure math stays in `valuation.py`/`scores.py`.
- **Request-id contextvar** - the access log formatter in `main.py` references `request_id`/`method`/
  `path`/`status`/`duration_ms`; `current_request_id()` is also available to error envelope builders.
- **Retry wrapper `_with_retry`** - only `MarketDataError` is retried (transient); other exceptions
  propagate immediately.
- **FinBERT is heavy + thread-sensitive** - the model loads lazily behind a `threading.Lock` (concurrent
  first imports of `transformers.pipeline` fail under `asyncio.to_thread`). First live ingest is slow;
  model is cached after. Scoring only NEW articles (already-scored ones are skipped).
- **`published_at` must be timezone-aware** (`DateTime(timezone=True)`) - naive vs aware datetimes crash
  asyncpg. Hit in first news tests.
- **Race-safe upsert by URL** - `ON CONFLICT DO NOTHING` on `uq_news_articles_url`, NOT check-then-insert:
  the same Google News article is fetched for multiple symbols concurrently (hit 6 unique-violation
  errors before the fix).
- **Google News RSS strips the exchange suffix** - query uses bare symbol ("RELIANCE"), because RSS
  feeds don't accept "RELIANCE.NS".
- **News migration is `ed7bb907ca7c`**; test DB drops/recreates schema, so tests need no FinBERT load.
- **Alpha migration is `b0f48fb7c939`**; `alpha_scores` snapshot upsert targets `uq_alpha_scores_symbol_date`.
- **Technical-score formulas are heuristics** (product-defined), not validated predictive models - trend 50 / momentum 30 / reversion 20. Treat as explainable signals, not alpha guarantees.
- **Valuation is deliberately separate** from the Alpha composite (40/30/30) - blending multiples would double-count fundamentals. `value_signal` surfaces it prominently instead.
- **`components` vs `weights` in the /alpha response are separate dicts** - pydantic rejects a nested dict in a `dict[str,float]` (hit in the first alpha test run).
- **`get_close_series` returns oldest-first** (reverses the DESC query) - feed indicators chronological closes.
- **LLM narrative lives in `services/llm_narrative.py`, NOT `explanation.py`** - `explanation.py` is imported by `analysis.py` → `alpha.py`; importing `AlphaResult` there would create a circular import.
- **`LLM_MODEL` empty = LLM disabled** - the code default is `""`; never hard-code a model ID in source. Set key + model in `backend/.env` to enable.
- **Free OpenRouter models rotate** - a `:free` model ID that works today may 404/429 later; the app falls back to the rule-based explanation on `LLMError`, so this is non-fatal.
- **Module-level `_cache`/`_calls_today` in `llm_narrative.py` persist across tests** - the `_reset_state` autouse fixture in `test_llm.py` clears them per test.
- **Redis still deferred** - the Phase 5 explanation cache + daily cap are in-process; a restart clears them.
- **PostgreSQL on Windows `0xC0000142` (STATUS_DLL_INIT_FAILED)** - the postmaster bound port 5432 but backend workers died on connection; log hint points at antivirus/backup interference. `pg_ctl status` may say "no server running" while the port listens briefly. Recovery was external; if DB-backed tests start erroring with `ConnectionRefusedError`/`server closed the connection`, re-check the server before assuming app bugs.

### Phase 6 frontend/backend gotchas
- **Radix nested triggers (Tooltip.Trigger asChild → Popover.Trigger asChild) do not respond to `@testing-library/user-event` in jsdom** (events hang or state stays closed). Tests assert the accessible trigger + extract the popover body (`InfoContent`) as a plain component; the composition itself works in real browsers.
- **jsdom needs stubs**: `ResizeObserver` (chart/layout), `IntersectionObserver` (framer-motion `useInView`), `matchMedia`. All in `frontend/src/test/setup.ts`.
- **Lightweight Charts v5 changed the API** - `chart.addSeries(CandlestickSeries, opts)` (import the series definition), NOT v4's `chart.addCandlestickSeries()`.
- **framer-motion `useInView` requires a ref argument** (`useInView(ref, { once: true })`); the zero-arg form is a TS error.
- **en-IN compact grouping is manual** - `Intl.NumberFormat("en-IN")` gives digit grouping but NOT "Cr/L" words; scaled values (v/1e7 etc.) are formatted by hand, thousands-grouped above 100.
- **Valuation multiples are per-metric endpoints** - the stock page issues one `/valuation?metric=` query per multiple (4 total) so every row shows its own peer median; TanStack Query dedupes the selected one. EV/EBITDA is never computed client-side (backend-only math rule).
- **Quote nulls are meaningful** - `GET /stocks/{symbol}` returns null quote fields when a stock has no price bars; the list endpoint's `0.0` sentinel was deliberately NOT copied (nulls drive the UI's "no data" states).
- **Vite dev proxy** (`/api` → `http://localhost:8000`) is the default frontend transport; CORS middleware exists for direct/production access and is verified with a raw `Origin` header. `VITE_API_BASE` overrides the default.
- **Shared LLM daily cap** - `llm_narrative.budget_ok()`/`register_llm_call()` are the single budget counter for BOTH `/alpha` and `/explain` (don't create a second counter).
- **Design-reference folders are git-ignored** (`/Refine design concept*/`, `/Stock Detail Page Frames(1)/`, `/stitch_signaldesk_landing_experience(1)/`) - local visual references only, never part of the app.

---

### PostgreSQL Incident / Operational Gotcha (2026-08-21)

**Install/run facts (durable):**
- PostgreSQL **17.11** install path: `C:\Users\shyam\PostgreSQL` (NOTE: not `PostgresSQL` - that spelling does not exist).
- Data directory: `C:\Users\shyam\PostgreSQL\data`.
- SignalDesk database: `signaldesk` (superuser `postgres` / `postgres`, dev only).
- PostgreSQL is started locally for development (no Windows service).

**Incident:** On 2026-08-21 PostgreSQL intermittently crashed with backend-worker exception **`0xC0000142` (STATUS_DLL_INIT_FAILED)**. The postmaster could temporarily bind port 5432 while real connections failed (`server closed the connection unexpectedly`).

**Likely cause (not conclusively proven):** Evidence strongly implicated external logfile handling/file locking and possible **antivirus (Defender/Malwarebytes) and/or VSS shadow-copy interference**:
- `could not open file "./server.log": sharing violation` + PostgreSQL's own hint: "You might have antivirus, backup, or similar software interfering with the database system."
- Volsnap/VSS shadow-copy events on volume C: immediately before the crash.
- Instances started with `pg_ctl -l <shared server.log>` crashed; the instance started directly was stable.

**Proven stable launch method (use this):**
```
& "C:\Users\shyam\PostgreSQL\bin\postgres.exe" -D "C:\Users\shyam\PostgreSQL\data"
```
Avoid `pg_ctl -l` with the old shared `server.log` arrangement.

**Outcome:** PostgreSQL eventually recovered; the complete Phase 5 suite subsequently passed (**133/133 tests, 78% coverage**, live `/alpha` verification succeeded). No data/WAL deletion, database reinitialization, password reset, or PostgreSQL reinstall was performed.

**If the problem recurs:** read `docs/incidents/postgresql-2026-08-21.md` before troubleshooting.

---

*Append progress after every phase. When a phase hits its Definition of Done, mark it complete here.*