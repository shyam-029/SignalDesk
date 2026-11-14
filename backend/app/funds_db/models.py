# ORM models for the funds database. See app/funds_db/__init__.py.
#
# Owner decisions behind the shape: direct plans, growth option only (so one
# row per fund, no separate plan table); NAV history back to launch, packed
# one row per fund per year (about 13 bytes a NAV against 76 as daily rows);
# ETF prices stay in the stocks database, linked by etf_symbol.

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class FundsBase(DeclarativeBase):
    """Base for funds-database tables only (its own MetaData)."""


class FundHouse(FundsBase):
    """An asset management company, as AMFI names it."""

    __tablename__ = "fund_houses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    # AMFI's own spelling, kept verbatim for matching its files.
    amfi_name: Mapped[str | None] = mapped_column(Text)


class Fund(FundsBase):
    """One direct growth plan (replaces the stocks database's mutual_funds)."""

    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    # AMFI scheme code: the upsert anchor.
    amfi_code: Mapped[str] = mapped_column(String(16), unique=True)
    isin: Mapped[str | None] = mapped_column(String(24), index=True)
    fund_house_id: Mapped[int | None] = mapped_column(ForeignKey("fund_houses.id"), index=True)
    name: Mapped[str] = mapped_column(Text)  # AMFI verbatim
    # equity | hybrid | debt | other
    asset_group: Mapped[str | None] = mapped_column(String(16))
    # Tidied label (AMFI spells categories two ways) and the verbatim one.
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    amfi_category: Mapped[str | None] = mapped_column(Text)
    # open | closed | etf | index | fof
    kind: Mapped[str | None] = mapped_column(String(16))
    benchmark: Mapped[str | None] = mapped_column(Text)
    launch_date: Mapped[date | None] = mapped_column(Date)
    min_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    # Link to stocks.symbol for an ETF (e.g. NIFTYBEES.NS). Text, not a
    # foreign key: the stocks table is in the other database.
    etf_symbol: Mapped[str | None] = mapped_column(String(32))
    latest_nav: Mapped[float | None] = mapped_column(Numeric(14, 4))
    nav_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NavHistory(FundsBase):
    """One fund's NAVs for one calendar year, packed into two arrays.

    days[i] is the day of the year (1-366) of navs[i]. double precision, not
    real: real cannot hold a NAV like 3349.1234. The nightly job rewrites
    only the current year's row of each fund.
    """

    __tablename__ = "nav_history"
    __table_args__ = (
        CheckConstraint(
            "cardinality(days) = cardinality(navs)", name="ck_nav_history_same_length"
        ),
    )

    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), primary_key=True)
    yr: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    days: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    navs: Mapped[list[float]] = mapped_column(ARRAY(Double))
    source: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FundReturns(FundsBase):
    """Latest returns and risk for a fund, rewritten nightly (percent)."""

    __tablename__ = "fund_returns"

    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), primary_key=True)
    as_of: Mapped[date | None] = mapped_column(Date)
    ret_1m: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ret_3m: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ret_6m: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ret_1y: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ret_3y: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ret_5y: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ret_10y: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ret_since_launch: Mapped[float | None] = mapped_column(Numeric(10, 4))
    category_rank: Mapped[int | None] = mapped_column(Integer)
    category_size: Mapped[int | None] = mapped_column(Integer)
    volatility_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    max_drawdown_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))


class FundFactsMonthly(FundsBase):
    """Monthly facts from the fund house's factsheet (all nullable)."""

    __tablename__ = "fund_facts_monthly"

    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), primary_key=True)
    month: Mapped[date] = mapped_column(Date, primary_key=True)  # first of month
    aum_cr: Mapped[float | None] = mapped_column(Numeric(16, 2))
    expense_ratio_pct: Mapped[float | None] = mapped_column(Numeric(6, 3))
    # The regular plan's ratio, kept as one number for the direct-vs-regular
    # comparison; no regular plan is stored.
    regular_expense_ratio_pct: Mapped[float | None] = mapped_column(Numeric(6, 3))
    turnover_pct: Mapped[float | None] = mapped_column(Numeric(8, 2))
    manager: Mapped[str | None] = mapped_column(Text)
    # Debt funds.
    ytm_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    avg_maturity_yrs: Mapped[float | None] = mapped_column(Numeric(8, 3))
    mod_duration_yrs: Mapped[float | None] = mapped_column(Numeric(8, 3))
    credit_json: Mapped[dict | None] = mapped_column(JSONB)
