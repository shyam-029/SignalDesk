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
    Integer,
    func,
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