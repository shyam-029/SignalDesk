# ORM models — the Phase 1 database schema (PLANNING §6).
#
# New concepts:
#  - Mapped[T] / mapped_column: SQLAlchemy 2.0 typed ORM. Column types and
#    constraints are declared via Python type hints + mapped_column(...).
#  - ForeignKey: a DB-level reference to another table's column, enforcing
#    referential integrity.
#  - Numeric: fixed-precision decimal — the right type for money/prices, since
#    binary floats introduce rounding errors.
#  - UniqueConstraint: guarantees (stock_id, date) appears once, making price
#    ingestion idempotent (no duplicate rows on re-run).
#  - Table(): the association table is a plain join table, so it doesn't need
#    its own model class — it's declared directly with metadata.
#  - relationship(): lets ORM queries traverse the many-to-many links
#    (e.g. stock.universes).

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Association table linking stocks to universes (many-to-many).
# A composite primary key of the two foreign keys, so each pairing is unique.
stock_universe = Table(
    "stock_universe",
    Base.metadata,
    Column("universe_id", Integer, ForeignKey("universes.id"), primary_key=True),
    Column("stock_id", Integer, ForeignKey("stocks.id"), primary_key=True),
)


class Stock(Base):
    """A single equity in the catalog. The catalog grows as the universe scales."""

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Symbol with exchange suffix, e.g. "RELIANCE.NS" — unique identifier.
    symbol: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    sector: Mapped[str | None]
    industry: Mapped[str | None]

    # --- Ranking metadata (M1-T2, Plan 7 / 14) ---
    # ISIN: the stable entity identity. Ranking matches NSE master rows to
    # catalog rows by ISIN so a symbol rename never creates a second catalog
    # entry (E5: one catalog entry per ISIN). NULL for rows seeded before the
    # column existed and not yet seen in a master.
    isin: Mapped[str | None] = mapped_column(String(24), index=True)
    # Active flag: False means delisted/suspended per the latest ranking cycle
    # (E9 inactive proxy or E10 master absence — one-cycle trigger, reversible
    # on reappearance). The row and ALL its history are never deleted.
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Why active became False ("absent_from_master" | "inactive_proxy"); NULL
    # while active. Reappearance clears both (reversibility).
    delisted_reason: Mapped[str | None] = mapped_column(String(64))
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Position in the ranked top-1000 universe (1 = largest eligible market
    # cap) and the date of the ranking cycle that set it; NULL when not
    # currently ranked in.
    mcap_rank: Mapped[int | None]
    mcap_asof: Mapped[date | None]
    # E1: BE/BZ series (eligible but trade-to-trade/surveillance segments).
    restrict_flag: Mapped[str | None] = mapped_column(String(32))
    # E2: ETFs live in their own domain (Plan 9); flagged when identified so
    # they are excluded from the equity ranking and M6 inherits the data.
    is_etf: Mapped[bool] = mapped_column(default=False, server_default=text("false"))

    # Many-to-many back-reference: which universes this stock belongs to.
    universes: Mapped[list["Universe"]] = relationship(
        secondary=stock_universe, back_populates="stocks"
    )


class Universe(Base):
    """A named group of stocks, e.g. "nifty50", "nifty200", "nifty500"."""

    __tablename__ = "universes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, index=True)

    # Many-to-many back-reference: which stocks this universe contains.
    stocks: Mapped[list["Stock"]] = relationship(
        secondary=stock_universe, back_populates="universes"
    )


class DailyPrice(Base):
    """Daily OHLCV bar for one stock. One row per stock per date."""

    __tablename__ = "daily_prices"
    __table_args__ = (
        # Prevent duplicate rows for the same stock on the same date.
        UniqueConstraint("stock_id", "date", name="uq_daily_prices_stock_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    date: Mapped[date]
    # Prices as Numeric (fixed-precision decimal) — no float rounding errors.
    open: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    high: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    low: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    close: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    volume: Mapped[int]

    # Back-reference to the owning stock.
    stock: Mapped["Stock"] = relationship()


class Financials(Base):
    """Latest financial snapshot for a stock (one row per stock).

    Point-in-time snapshot from the market-data provider (yfinance `info`).
    Each metric column is nullable — providers may not supply every field.
    `updated_at` records when the snapshot was taken.
    """

    __tablename__ = "financials"
    __table_args__ = (
        # One snapshot per stock; upserts target this constraint.
        UniqueConstraint("stock_id", name="uq_financials_stock_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)

    # Valuation-relevant fields (from yfinance `info`).
    market_cap: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    trailing_pe: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))
    enterprise_value: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    ebitda: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    price_to_book: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))
    price_to_sales: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))
    # Pre-computed EV/EBITDA ratio (Upstox key ratios, D65): the providers
    # that carry it never supply EV and EBITDA as separate absolutes, so the
    # ratio is stored and valuation falls back to it.
    ev_ebitda: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))

    # Profitability fields (normalized to percent before scoring).
    return_on_equity: Mapped[Numeric | None] = mapped_column(Numeric(10, 4))
    return_on_assets: Mapped[Numeric | None] = mapped_column(Numeric(10, 4))
    operating_margin: Mapped[Numeric | None] = mapped_column(Numeric(10, 4))
    profit_margin: Mapped[Numeric | None] = mapped_column(Numeric(10, 4))

    # Solvency fields.
    debt_to_equity: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))
    interest_coverage: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))
    current_ratio: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Back-reference to the owning stock.
    stock: Mapped["Stock"] = relationship()


class CompanyProfile(Base):
    """Provider-sourced company background for a stock (one row per stock).

    business_summary is the provider's own description text stored VERBATIM
    (never generated); ceo/employees/website are nullable because providers
    do not always supply them. Serves the "About the company" box and the
    ask endpoint's company evidence.
    """

    __tablename__ = "company_profiles"
    __table_args__ = (
        UniqueConstraint("stock_id", name="uq_company_profiles_stock_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)

    business_summary: Mapped[str | None] = mapped_column(Text)
    ceo: Mapped[str | None] = mapped_column(String(200))
    employees: Mapped[int | None] = mapped_column(BigInteger)
    website: Mapped[str | None] = mapped_column(String(300))
    # Which provider supplied the row ("yfinance", "upstox", ...).
    source: Mapped[str | None] = mapped_column(String(32))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Back-reference to the owning stock.
    stock: Mapped["Stock"] = relationship()


class FinancialPeriod(Base):
    """One historical income-statement period for a stock.

    Unlike `Financials` (a single point-in-time snapshot), this table keeps
    per-period history (annual first; the schema also admits quarterly rows).
    Every metric column is nullable: providers do not supply all fields for
    all periods, and missing values are never fabricated. `source` records
    which provider supplied the row ("yfinance", "upstox", or "merged").
    """

    __tablename__ = "financial_periods"
    __table_args__ = (
        # One row per stock per period end per period type; upserts target
        # this constraint so re-ingestion stays idempotent.
        UniqueConstraint(
            "stock_id", "period_end", "period_type",
            name="uq_financial_periods_stock_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    period_end: Mapped[date]
    # "annual" | "quarterly".
    period_type: Mapped[str] = mapped_column(String(16))

    # Income-statement values in rupees (Upstox reports in crore; the adapter
    # converts so units are consistent across providers).
    revenue: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    net_income: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))

    # Ratios stored as decimals (0.18 = 18%), computed by the backend.
    operating_margin: Mapped[Numeric | None] = mapped_column(Numeric(10, 6))
    net_margin: Mapped[Numeric | None] = mapped_column(Numeric(10, 6))

    # Earnings per share (rupees).
    eps: Mapped[Numeric | None] = mapped_column(Numeric(12, 4))

    source: Mapped[str] = mapped_column(String(32))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Back-reference to the owning stock.
    stock: Mapped["Stock"] = relationship()


class NewsArticle(Base):
    """A news article relevant to a stock (deduplicated by URL)."""

    __tablename__ = "news_articles"
    __table_args__ = (
        # One row per article URL — the idempotency anchor for ingestion.
        UniqueConstraint("url", name="uq_news_articles_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stock symbol (with suffix, e.g. "RELIANCE.NS") the article is about.
    symbol: Mapped[str] = mapped_column(index=True)
    source: Mapped[str]
    title: Mapped[str]
    url: Mapped[str]
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    content: Mapped[str | None]

    # One-to-one: an article has at most one sentiment row.
    sentiment: Mapped["NewsSentiment | None"] = relationship(
        back_populates="article", uselist=False
    )


class NewsSentiment(Base):
    """FinBERT sentiment result for one article (1:1 with news_articles)."""

    __tablename__ = "news_sentiment"
    __table_args__ = (
        # At most one sentiment row per article.
        UniqueConstraint("article_id", name="uq_news_sentiment_article_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("news_articles.id"), index=True
    )
    score: Mapped[float]  # 0..1 confidence for the predicted label
    label: Mapped[str]  # "positive" | "negative" | "neutral"
    model: Mapped[str]  # model identifier, e.g. "ProsusAI/finbert"

    article: Mapped["NewsArticle"] = relationship(back_populates="sentiment")


class AlphaScore(Base):
    """Daily Alpha Score snapshot for a stock (one row per symbol/date).

    Composite = 40% fundamental + 30% technical + 30% sentiment (weights
    renormalized over available components), bounded 0-100. Valuation is NOT
    blended in — it is surfaced separately as the "value signal". The
    components_json column keeps every sub-component so the score stays
    explainable.
    """

    __tablename__ = "alpha_scores"
    __table_args__ = (
        # One snapshot per symbol per computed date.
        UniqueConstraint("symbol", "date", name="uq_alpha_scores_symbol_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(index=True)
    date: Mapped[date]

    # Sub-scores 0-100 (nullable when a dimension has no data).
    fundamental: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))
    technical: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))
    sentiment: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))
    composite: Mapped[Numeric | None] = mapped_column(Numeric(6, 2))

    # Explainability: per-component breakdown (trend/momentum/reversion, etc.).
    components_json: Mapped[dict | None] = mapped_column(JSONB)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JobRun(Base):
    """One execution of a scheduled/background job pass (Phase 7).

    Durable job-history so the app can answer: what ran, when, did it
    succeed, how long did it take, what failed. Status semantics:
      running  - started, not yet finished (crashed runs stay 'running')
      success  - finished with zero per-item failures
      partial  - finished but some items failed (isolated per D19)
      failed   - the whole pass raised and aborted
    error_summary is TRUNCATED and never contains secrets (job code logs
    and stores exception messages that deliberately exclude credentials).
    """

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_job_started", "job_name", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))  # running|success|partial|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None]
    items_processed: Mapped[int | None]
    items_failed: Mapped[int | None]
    error_summary: Mapped[str | None] = mapped_column(Text)


class RankingCycle(Base):
    """One run of the top-1000 universe ranking job (M1-T2, Plan 7).

    One row per cycle date (same-day re-runs are idempotent: the existing
    row is reused and its audit rows rebuilt). Execution status lives in
    job_runs (pass name "rank_universe"); this row owns the data-level
    facts: which universe was rebuilt, the market-wide newest bar date used
    as the trading-calendar reference for the E9 inactive proxy, and timing.
    """

    __tablename__ = "ranking_cycles"
    __table_args__ = (
        UniqueConstraint("cycle_date", name="uq_ranking_cycles_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_date: Mapped[date]
    universe_name: Mapped[str] = mapped_column(String(32))
    # Market-wide newest daily_prices date at ranking time (E9 reference).
    mcap_asof: Mapped[date | None]
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None]


class RankingAudit(Base):
    """Per-symbol ranking disposition for one cycle (the audit trail).

    Every NSE master row gets exactly one row per cycle (plus catalog stocks
    absent from the master), so a human can ask "why isn't stock X in the
    top 1000 this month" and get a stored answer: ranked_out at rank N,
    excluded/no_mcap, excluded/inactive_proxy, etc. This is queryable data,
    never a log. outcome is ranked_in | ranked_out | excluded.
    """

    __tablename__ = "ranking_audit"
    __table_args__ = (
        # One audit row per master symbol per cycle (idempotency anchor).
        UniqueConstraint("cycle_id", "symbol", name="uq_ranking_audit_cycle_symbol"),
        Index("ix_ranking_audit_cycle_outcome", "cycle_id", "outcome"),
        Index("ix_ranking_audit_stock", "stock_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("ranking_cycles.id"), index=True)
    # NULL when the master row never became a catalog row (e.g. series or
    # curated exclusions); set once the symbol is rankable.
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"))
    # Bare NSE master symbol ("RELIANCE"); for a catalog stock absent from
    # the master, the bare catalog symbol.
    symbol: Mapped[str] = mapped_column(String(32))
    # Catalog symbol with suffix when matched to a row, else NULL.
    catalog_symbol: Mapped[str | None] = mapped_column(String(32))
    series: Mapped[str | None] = mapped_column(String(8))
    isin: Mapped[str | None] = mapped_column(String(24))
    # Master company-name snapshot (point-in-time record; never written back
    # to the catalog — naming stays with existing sources).
    name: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(32))
    flag: Mapped[str | None] = mapped_column(String(32))
    # Human-readable context, e.g. "REIT", "last bar 2026-07-01 (41 trading
    # days stale)", "provider fetch failed: MarketDataError".
    detail: Mapped[str | None] = mapped_column(Text)
    # Ranking input actually seen this cycle (never backfilled/estimated).
    mcap: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    # Position among eligible candidates (1 = largest mcap); <=1000 means
    # ranked_in, >1000 means ranked_out with the exact rank shown.
    rank: Mapped[int | None]


class Benchmark(Base):
    """One benchmark index (M1-T6, Plan 13/14): ^NSEI, ^NSEBANK, ^CNXIT, ^CRSLDX.

    Benchmarks live OUTSIDE the equity catalog on purpose: index rows in
    `stocks` would leak into /stocks, /screener and peer sets. kind is
    "index" for every row today (sector indexes are the same shape).
    """

    __tablename__ = "benchmarks"
    __table_args__ = (
        # One row per index symbol — the idempotency anchor for ingestion.
        UniqueConstraint("symbol", name="uq_benchmarks_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Yahoo index symbol, e.g. "^NSEI" (kept verbatim, never suffixed).
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16), default="index")
    # Which provider supplied the row ("yfinance" — index bars have no
    # Upstox secondary; provenance still recorded per the S1 contract).
    source: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BenchmarkPrice(Base):
    """Daily OHLCV bar for one benchmark index (M1-T6).

    Same shape as daily_prices so beta/drawdown/relative-performance math
    (Plan 5.2) reuses the pattern; separate table so benchmark data never
    interferes with equity ranking, valuation or peer sets.
    """

    __tablename__ = "benchmark_prices"
    __table_args__ = (
        # One bar per index per date — the idempotency anchor for ingestion.
        UniqueConstraint(
            "benchmark_id", "date", name="uq_benchmark_prices_benchmark_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    benchmark_id: Mapped[int] = mapped_column(
        ForeignKey("benchmarks.id"), index=True
    )
    date: Mapped[date]
    open: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    high: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    low: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    close: Mapped[Numeric] = mapped_column(Numeric(16, 4))
    volume: Mapped[int] = mapped_column(BigInteger)

    benchmark: Mapped["Benchmark"] = relationship()


class BalanceSheetPeriod(Base):
    """One historical annual balance-sheet period for a stock (Plan 5.4).

    Drives the real Altman Z-Score (services/altman.py): working capital,
    total assets, retained earnings, EBIT (from the income statement), book
    equity and total liabilities. Every metric column is nullable — banks
    and NBFCs report non-standard formats and stay honestly missing rather
    than estimated. source records the provider ("yfinance").
    """

    __tablename__ = "balance_sheet_periods"
    __table_args__ = (
        # One row per stock per period end per period type (annual today).
        UniqueConstraint(
            "stock_id", "period_end", "period_type",
            name="uq_balance_sheet_periods_stock_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    period_end: Mapped[date]
    period_type: Mapped[str] = mapped_column(String(16))  # "annual"

    working_capital: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    total_assets: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    retained_earnings: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    # Operating EBIT, carried from the income statement (Altman X3 numerator).
    ebit: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    book_equity: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))
    total_liabilities: Mapped[Numeric | None] = mapped_column(Numeric(20, 2))

    source: Mapped[str] = mapped_column(String(32))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship()


class MutualFund(Base):
    """One curated mutual-fund scheme (Plan 8, minimal slice).

    amfi_code is the official AMFI scheme code and the upsert anchor. The
    catalog is CURATED (about 24 major schemes across categories), not the
    whole AMFI universe: Plan 29 leaves the full-curation cut rule to M4.
    latest_nav/nav_date mirror the newest mf_nav_history row for cheap
    listing; the history rows remain the source of truth.
    """

    __tablename__ = "mutual_funds"
    __table_args__ = (
        UniqueConstraint("amfi_code", name="uq_mutual_funds_amfi_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    amfi_code: Mapped[str] = mapped_column(String(16), index=True)
    # AMFI scheme name stored verbatim (never generated).
    name: Mapped[str] = mapped_column(Text)
    # Curated category label ("Flexi Cap", "Small Cap", "Liquid", ...).
    category: Mapped[str | None] = mapped_column(String(32))
    plan: Mapped[str | None] = mapped_column(String(16))
    option: Mapped[str | None] = mapped_column(String(16))
    latest_nav: Mapped[Numeric | None] = mapped_column(Numeric(12, 4))
    nav_date: Mapped[date | None]
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Which source produced the latest NAV ("amfi" | "mfapi").
    source: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MutualFundNav(Base):
    """One daily NAV point for a fund (idempotent by fund+date).

    source distinguishes the official AMFI daily file ("amfi") from the
    mfapi.in history backfill ("mfapi") — Plan 13 allows the third-party
    mirror as a documented fallback only, so provenance is queryable.
    """

    __tablename__ = "mf_nav_history"
    __table_args__ = (
        UniqueConstraint("fund_id", "date", name="uq_mf_nav_history_fund_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("mutual_funds.id"), index=True)
    date: Mapped[date]
    nav: Mapped[Numeric] = mapped_column(Numeric(12, 4))
    source: Mapped[str] = mapped_column(String(16))