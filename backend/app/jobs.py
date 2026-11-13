# Background ingestion: fetch market data and persist to PostgreSQL.
#
# Design goals (from PLANNING):
#  - D16: read the universe from the DB, never a hardcoded list.
#  - D19: batched + resumable; one failed symbol never aborts the run.
#  - Idempotent: re-running produces no duplicate daily_price rows, thanks to
#    PostgreSQL INSERT ... ON CONFLICT (upsert).
#
# New concepts:
#  - Upsert: "insert, or if a conflicting row exists (same stock_id+date),
#    update it instead". Guarantees idempotency against the UNIQUE constraint.
#  - asyncio.gather: runs many coroutines concurrently (bounded to a batch).

import asyncio
import calendar
import functools
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import TypeVar

from sqlalchemy import delete, exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.config import settings
from app.data.funds import CURATED_FUNDS, MFAPI_BACKFILL_DAYS
from app.data.ranking_exclusions import ETF_SYMBOLS, RETIRED_SYMBOLS
from app.models import (
    AlphaScore,
    CompanyProfile,
    DailyPrice,
    FinancialPeriod,
    Financials,
    JobRun,
    MutualFund,
    NewsArticle,
    NewsSentiment,
    Stock,
    Universe,
    stock_universe,
)
from app.providers.base import Fundamentals, MarketDataProvider, OHLCV
from app.providers.factory import build_default_market_provider
from app.providers.funds_data import (
    fetch_amfi_navall,
    fetch_mfapi_history,
    match_curated,
    parse_navall,
)
from app.providers.news_base import Article, NewsProvider
from app.providers.nse_master import NseMasterRow, fetch_master_with_retry
from app.providers.rss_provider import GoogleNewsRSSProvider, NewsProviderError
from app.services.news_relevance import generic_tokens_from_names, is_relevant_article
from app.providers.sentiment import FinBERTScorer, Sentiment
from app.providers.upstox_provider import SYMBOL_ALIASES, UpstoxProvider
from app.repositories import shareholding as shareholding_repo
from app.providers.yfinance_provider import MarketDataError, YFinanceProvider
from app.repositories import balance_sheets as bs_repo
from app.repositories import benchmarks as benchmark_repo
from app.repositories import company_profiles as profile_repo
from app.repositories import funds as fund_repo
from app.repositories import ranking as ranking_repo
from app.repositories.upsert_guard import INSERTED_FLAG as _INSERTED_FLAG
from app.repositories.upsert_guard import any_distinct as _any_distinct
from app.services import ranking as ranking_svc
from app.services import storage as storage_svc

logger = logging.getLogger(__name__)

UNIVERSE_NAME = "top1000"  # M1-T3 cutover: nightly ingestion reads the ranked
# top-1000 universe (was "nifty250"). Ranked-out / excluded catalog stocks
# are intentionally outside this path: they keep every stored row, and the
# repair_catalog_gaps pass still refreshes them when they have gaps.
PERIOD = "2y"  # the full price history a stock gets (new, short or refetched)

# --- Incremental price fetch (work list item 27, owner decision 2026-11-12) ---
# Most nights only the last month is fetched instead of 2 years. Prices are
# split- and dividend-adjusted, so a corporate action rescales a stock's
# whole past; the fetched month overlaps the newest stored bars, and if any
# shared close differs by more than OVERLAP_TOLERANCE the full 2 years are
# fetched again and stored over the old series. A stock with little stored
# history, or whose newest bar is more than INCREMENTAL_MAX_GAP_DAYS old,
# always gets the full fetch.
INCREMENTAL_PERIOD = "1mo"
OVERLAP_BARS = 10
OVERLAP_MIN_SHARED = 3
OVERLAP_TOLERANCE = 0.001  # 0.1%
FULL_MIN_BARS = 400
INCREMENTAL_MAX_GAP_DAYS = 20
BATCH_SIZE = 5  # concurrent symbols per batch (respect provider rate limits)

# --- Top-1000 ranking (M1-T2) ---
# The ranked universe written by rank_universe. M1-T3 cutover complete:
# nightly ingestion reads UNIVERSE_NAME (top1000) directly.
RANKED_UNIVERSE = "top1000"
RANKED_SIZE = 1000

T = TypeVar("T")


async def _with_retry(
    fetch: Callable[[], Awaitable[T]],
    retries: int = 2,
    base_delay: float = 0.5,
    what: str = "provider call",
    delays: tuple[float, ...] | None = None,
    jitter: float = 0.0,
) -> T:
    """Retry a provider call with exponential backoff on MarketDataError.

    Only MarketDataError (transient provider/network failures) is retried;
    other exceptions propagate immediately. After the final attempt the last
    error is re-raised so callers can isolate it per symbol (D19).

    delays optionally overrides the default base_delay * 2**attempt schedule
    with an explicit per-retry sequence; jitter (fraction, e.g. 0.25) applies
    a uniform multiplier in [1-j, 1+j] to each delay. Both default to the
    historical behavior so existing callers are untouched.
    """
    for attempt in range(retries + 1):
        try:
            return await fetch()
        except MarketDataError as exc:
            if attempt >= retries:
                raise
            if delays is not None and attempt < len(delays):
                delay = delays[attempt]
            else:
                delay = base_delay * (2**attempt)
            if jitter > 0.0:
                delay *= random.uniform(1.0 - jitter, 1.0 + jitter)
            logger.warning(
                "%s failed (attempt %d/%d): %s; retrying in %.1fs",
                what,
                attempt + 1,
                retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    # Unreachable: either a return happened or the final error was re-raised.
    raise AssertionError("unreachable")


async def _get_universe_symbols(session: AsyncSession) -> list[str]:
    """Return the symbols belonging to the active universe, read from the DB."""
    result = await session.execute(
        select(Stock.symbol)
        .join(stock_universe, stock_universe.c.stock_id == Stock.id)
        .join(Universe, Universe.id == stock_universe.c.universe_id)
        .where(Universe.name == UNIVERSE_NAME)
    )
    return list(result.scalars())


# A fetched price frame ending this many days before today is treated as a
# transient provider failure and retried by _with_retry; persistence becomes
# a visible per-symbol error instead of a silently frozen series.
STALE_FRAME_MAX_AGE_DAYS = 5


def _assert_frame_fresh(
    symbol: str, bars: list[OHLCV], today: date | None = None
) -> None:
    """Reject a silently truncated provider frame.

    yfinance can return a history frame that just... stops months ago, with
    no exception and no empty frame (verified on the Actions runner 2026-11-09:
    RELIANCE.NS/TCS.NS served bars ending 2026-09-08 through three full
    nightly runs while other symbols were current). Such a frame upserts
    idempotently over already-stored rows, freezing the symbol's series with
    zero errors and zero skips — the worst kind of failure: invisible. A
    frame older than the tolerance raises MarketDataError so the existing
    retry/backoff machinery handles it and the outcome is recorded honestly.

    today pins the reference date (ranking.py convention: logic never reads
    the clock). Defaults to the real clock, so production behavior is
    unchanged; tests with fixed-date fixtures inject the matching day.
    """
    if not bars:
        return  # empty frames keep the caller's explicit "No price data" path
    last = max(b.date for b in bars)
    if last < (today or date.today()) - timedelta(days=STALE_FRAME_MAX_AGE_DAYS):
        raise MarketDataError(
            f"stale price frame for {symbol}: last bar {last.isoformat()} "
            f"(older than {STALE_FRAME_MAX_AGE_DAYS} days; provider likely "
            "served a truncated or cached frame)"
        )


async def _get_universe_symbols_and_names(
    session: AsyncSession,
) -> list[tuple[str, str | None]]:
    """Return (symbol, name) pairs for the active universe, read from the DB.

    The company full name feeds the news provider's primary search query.
    """
    result = await session.execute(
        select(Stock.symbol, Stock.name)
        .join(stock_universe, stock_universe.c.stock_id == Stock.id)
        .join(Universe, Universe.id == stock_universe.c.universe_id)
        .where(Universe.name == UNIVERSE_NAME)
    )
    return [(row.symbol, row.name) for row in result]


def _alias_fetch_symbol(symbol: str) -> str | None:
    """Return the renamed fetch symbol for a catalog symbol, if any.

    Catalog rows keep their seed symbol; demergers/renames change the NSE
    trading symbol underneath (SYMBOL_ALIASES, bare forms). The Upstox
    provider resolves renames through its instruments master, but yfinance
    does not — a renamed catalog symbol hits a dead Yahoo ticker (0 rows, or
    a frame frozen at the rename) forever. Returns the full-qualified alias
    symbol with the catalog suffix preserved, or None.
    """
    bare = symbol.split(".")[0]
    target = SYMBOL_ALIASES.get(bare)
    if not target:
        return None
    return target + symbol[len(bare):]


async def _fetch_bars_with_alias(
    provider: MarketDataProvider,
    symbol: str,
    today: date | None = None,
    period: str = PERIOD,
) -> list[OHLCV]:
    """Fetch price bars for a catalog symbol, falling back to its rename.

    Order of attempts: the catalog symbol (retried by _with_retry; a stale
    frame raises per _assert_frame_fresh), then — when the catalog symbol
    yields nothing usable (empty frame or exhausted retries) and the symbol
    has a rename alias — the aliased master symbol, which carries the same
    entity's continued series (verified 2026-11-10: TMPV.NS serves the full
    pre-demerger history that dead TATAMOTORS.NS no longer does).

    today is forwarded to the freshness guard (None = real clock).
    """
    async def _one(sym: str) -> list[OHLCV]:
        bars = await provider.get_price_history(sym, period)
        if bars:
            _assert_frame_fresh(sym, bars, today)
        return bars

    alias = _alias_fetch_symbol(symbol)
    try:
        bars = await _with_retry(
            lambda: _one(symbol), what=f"price fetch for {symbol}"
        )
        if bars:
            return bars
        if alias is None:
            return []
    except MarketDataError as primary_exc:
        if alias is None:
            raise
        logger.info(
            "price fetch for %s unusable (%s); falling back to renamed symbol %s",
            symbol, primary_exc, alias,
        )
        return await _with_retry(
            lambda: _one(alias), what=f"price fetch for {symbol} via {alias}"
        )
    logger.info(
        "no price data for %s under the catalog symbol; trying renamed symbol %s",
        symbol, alias,
    )
    return await _with_retry(
        lambda: _one(alias), what=f"price fetch for {symbol} via {alias}"
    )


_PRICE_COLUMNS = ("open", "high", "low", "close", "volume")


def _new_write_stats() -> dict[str, int]:
    """Counters for what an upsert actually wrote (Phase 2 measurement)."""
    return {"inserted": 0, "updated": 0, "unchanged": 0}


def _tally_upsert(stats: dict[str, int] | None, flags: list[bool], offered: int) -> None:
    """Fold one guarded upsert's RETURNING flags into `stats`.

    `flags` holds one `inserted` boolean per row the statement actually wrote
    (RETURNING (xmax = 0)): True = new row, False = an existing row whose
    values changed. Rows the no-op guard skipped return nothing, so they are
    `offered - len(flags)`.
    """
    if stats is None:
        return
    inserted = sum(1 for f in flags if f)
    stats["inserted"] += inserted
    stats["updated"] += len(flags) - inserted
    stats["unchanged"] += offered - len(flags)


@dataclass(frozen=True)
class StoredTail:
    """What is stored for a stock: bar count, newest date, newest closes."""

    bars: int
    last_date: date
    closes: dict  # date -> close, the newest OVERLAP_BARS stored bars


_TAILS_SQL = text(
    """
    WITH t AS (
        SELECT s.symbol AS symbol, dp.date AS day, dp.close::float8 AS close,
               row_number() OVER (PARTITION BY dp.stock_id ORDER BY dp.date DESC) AS rn,
               count(*) OVER (PARTITION BY dp.stock_id) AS n
        FROM daily_prices dp
        JOIN stocks s ON s.id = dp.stock_id
        WHERE s.symbol = ANY(:symbols)
    )
    SELECT symbol, day, close, n FROM t WHERE rn <= :k
    """
)


async def _stored_tails(symbols: list[str]) -> dict[str, StoredTail]:
    """Each stock's stored bar count and newest closes, in one query.

    About OVERLAP_BARS small rows per stock leave the database (~10k rows,
    a few hundred KB for the whole list), counted inside PostgreSQL.
    """
    if not symbols:
        return {}
    async with SessionLocal() as session:
        rows = (
            await session.execute(_TAILS_SQL, {"symbols": list(symbols), "k": OVERLAP_BARS})
        ).all()
    grouped: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for r in rows:
        grouped.setdefault(r.symbol, {})[r.day] = float(r.close)
        counts[r.symbol] = int(r.n)
    return {
        sym: StoredTail(bars=counts[sym], last_date=max(closes), closes=closes)
        for sym, closes in grouped.items()
    }


def _overlap_matches(tail: StoredTail, bars: list[OHLCV]) -> bool:
    """True when the fetched bars agree with the stored ones they overlap.

    At least OVERLAP_MIN_SHARED shared dates are required; any shared close
    more than OVERLAP_TOLERANCE away means the provider rescaled the history
    (a split, bonus or dividend adjustment) and the full series is refetched.
    """
    shared = 0
    for b in bars:
        old = tail.closes.get(b.date)
        if old is None or b.close is None:
            continue
        shared += 1
        if old <= 0 or abs(float(b.close) / old - 1.0) > OVERLAP_TOLERANCE:
            return False
    return shared >= OVERLAP_MIN_SHARED


def _incremental_ok(tail: StoredTail | None, today: date) -> bool:
    return (
        tail is not None
        and tail.bars >= FULL_MIN_BARS
        and (today - tail.last_date).days <= INCREMENTAL_MAX_GAP_DAYS
    )


async def _fetch_one_symbol(
    provider: MarketDataProvider,
    symbol: str,
    today: date | None = None,
    stats: dict[str, int] | None = None,
    tail: StoredTail | None = None,
    modes: dict[str, int] | None = None,
) -> tuple[str, int]:
    """Fetch and upsert one symbol's history. Returns (symbol, bars_offered).

    Raises MarketDataError upward so callers can isolate failures per symbol.
    today is forwarded to the freshness guard (None = real clock).
    stats, when given, accumulates inserted / updated / unchanged row counts
    (see _tally_upsert); the return contract is unchanged.

    With `tail` (what is stored, from _stored_tails) only the last month is
    fetched when that is safe (_incremental_ok) and agrees with the stored
    bars (_overlap_matches); otherwise the full PERIOD. `modes`, when given,
    counts "incremental", "full" and "refetch" (the month disagreed).
    """
    mode = "full"
    bars: list[OHLCV] = []
    if _incremental_ok(tail, today or date.today()):
        bars = await _fetch_bars_with_alias(provider, symbol, today, INCREMENTAL_PERIOD)
        if bars and _overlap_matches(tail, bars):
            mode = "incremental"
        else:
            mode = "refetch"
            if bars:
                logger.info(
                    "price history for %s changed under the stored bars "
                    "(split, bonus or dividend adjustment): refetching %s",
                    symbol, PERIOD,
                )
    if mode != "incremental":
        bars = await _fetch_bars_with_alias(provider, symbol, today)
    if modes is not None:
        modes[mode] = modes.get(mode, 0) + 1
    if not bars:
        logger.warning("No price data for %s; skipping.", symbol)
        return symbol, 0

    # Resolve the stock's DB id once (symbols are static after seeding).
    async with SessionLocal() as session:
        stock_id = await session.scalar(
            select(Stock.id).where(Stock.symbol == symbol)
        )
        if stock_id is None:
            raise MarketDataError(f"Symbol {symbol} not in DB catalog")

        # Bulk upsert: one statement for all bars of this symbol.
        stmt = pg_insert(DailyPrice).values(
            [
                {
                    "stock_id": stock_id,
                    "date": b.date,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ]
        )
        # On conflict with (stock_id, date), overwrite the existing bar —
        # but field-level COALESCE (mirrors the financials snapshot guard):
        # a column the provider did not supply tonight must never blank a
        # previously-good stored value. Defense-in-depth under the provider's
        # NaN-row guard (incident 2026-09-09).
        new_values = {
            col: func.coalesce(getattr(stmt.excluded, col), getattr(DailyPrice, col))
            for col in _PRICE_COLUMNS
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_prices_stock_date",
            set_=new_values,
            # No-op guard (Phase 2): skip the write entirely when the
            # COALESCEd values equal what is stored. Without it Postgres
            # writes a new row version for every one of the ~462k unchanged
            # bars re-offered each night (the 2y window is re-fetched whole).
            where=_any_distinct(DailyPrice, new_values),
        ).returning(_INSERTED_FLAG)
        flags = list((await session.execute(stmt)).scalars())
        await session.commit()
        _tally_upsert(stats, flags, len(bars))
        return symbol, len(bars)


async def ingest_universe(
    provider: MarketDataProvider | None = None,
    batch_size: int = BATCH_SIZE,
    today: date | None = None,
) -> dict:
    """Fetch + upsert price history for every symbol in the active universe.

    Processes symbols in bounded batches (asyncio.gather) for rate-limit safety.
    A failure in one symbol is logged and isolated; the run continues.
    today is forwarded to the freshness guard (None = real clock).
    """
    provider = provider or build_default_market_provider()

    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    if not symbols:
        logger.warning("No symbols found for universe '%s'.", UNIVERSE_NAME)
        return {"fetched": 0, "bars": 0, "errors": 0, "skipped": 0}

    total_bars = 0
    errors: list[str] = []
    skipped = 0
    written = _new_write_stats()
    tails = await _stored_tails(symbols)
    modes: dict[str, int] = {}

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(
                _fetch_one_symbol(provider, s, today, written, tails.get(s), modes)
                for s in batch
            ),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest %s: %s", symbol, res)
                errors.append(symbol)
            else:
                _, bars = res
                total_bars += bars
                if bars == 0:
                    skipped += 1

    # `bars` stays the number offered (historical meaning); the write split
    # shows how many rows the no-op guard actually spared.
    logger.info(
        "Ingestion done: %d symbols, %d bars, %d errors, %d skipped "
        "(written: %d inserted, %d updated, %d unchanged)",
        len(symbols) - len(errors),
        total_bars,
        len(errors),
        skipped,
        written["inserted"],
        written["updated"],
        written["unchanged"],
    )
    logger.info(
        "Price fetch modes: %d last month only, %d full (new or short history), "
        "%d refetched in full (history adjusted)",
        modes.get("incremental", 0), modes.get("full", 0), modes.get("refetch", 0),
    )
    # Upstox price fallback (providers/fallback.py): how often Yahoo's answer
    # was unusable and Upstox was asked instead, by reason.
    fallbacks = dict(getattr(provider, "fallbacks", {}) or {})
    fallback_failures = int(getattr(provider, "fallback_failures", 0) or 0)
    if fallbacks or fallback_failures:
        logger.info(
            "Upstox price fallback used: %s (upstox also failed: %d)",
            ", ".join(f"{k}={v}" for k, v in sorted(fallbacks.items())) or "none",
            fallback_failures,
        )
    return {
        "fetched": len(symbols) - len(errors),
        "bars": total_bars,
        "errors": len(errors),
        "skipped": skipped,
        **written,
        "upstox_fallbacks": sum(fallbacks.values()),
        "incremental": modes.get("incremental", 0),
        "full": modes.get("full", 0),
        "refetch": modes.get("refetch", 0),
    }


# --- Financials ingestion (Phase 2: valuation/fundamentals data) ---


def _financials_row(stock_id: int, f: Fundamentals) -> dict:
    """Map a provider Fundamentals object onto the financials table columns."""
    return {
        "stock_id": stock_id,
        "market_cap": f.market_cap,
        "trailing_pe": f.trailing_pe,
        "enterprise_value": f.enterprise_value,
        "ebitda": f.ebitda,
        "price_to_book": f.price_to_book,
        "price_to_sales": f.price_to_sales,
        "ev_ebitda": f.ev_ebitda,
        "return_on_equity": f.return_on_equity,
        "return_on_assets": f.return_on_assets,
        "operating_margin": f.operating_margin,
        "profit_margin": f.profit_margin,
        "debt_to_equity": f.debt_to_equity,
        "interest_coverage": f.interest_coverage,
        "current_ratio": f.current_ratio,
    }


async def _fetch_one_financials(
    provider: MarketDataProvider, symbol: str
) -> tuple[str, bool]:
    """Fetch + upsert one symbol's financial snapshot. Returns (symbol, inserted).

    Raises MarketDataError upward so callers can isolate failures per symbol.

    Field-level coalesce on write: the new (merged-provider) value wins when
    present; a field the providers did not supply TONIGHT keeps its stored
    value. Provider responses are flaky night to night (throttled info dicts
    return sparse fields without erroring), and a naive full overwrite would
    destroy previously-good values - the stored snapshot is "latest known
    value per field", refreshed `updated_at` included.
    """
    fundamentals = await _with_retry(
        lambda: provider.get_fundamentals(symbol),
        what=f"fundamentals fetch for {symbol}",
    )

    async with SessionLocal() as session:
        stock_id = await session.scalar(
            select(Stock.id).where(Stock.symbol == symbol)
        )
        if stock_id is None:
            raise MarketDataError(f"Symbol {symbol} not in DB catalog")

        row = _financials_row(stock_id, fundamentals)
        existing = await session.scalar(
            select(Financials).where(Financials.stock_id == stock_id)
        )
        if existing is not None:
            for field, value in list(row.items()):
                if field != "stock_id" and value is None:
                    stored = getattr(existing, field)
                    if stored is not None:
                        row[field] = stored

        stmt = pg_insert(Financials).values(row)
        # One row per stock: overwrite the coalesced snapshot on conflict. The
        # refresh of updated_at marks the (attempted) refresh, not that every
        # field changed.
        set_ = {k: getattr(stmt.excluded, k) for k in row if k != "stock_id"}
        set_["updated_at"] = func.now()
        stmt = stmt.on_conflict_do_update(
            constraint="uq_financials_stock_id",
            set_=set_,
        )
        await session.execute(stmt)
        await session.commit()
        return symbol, True


async def ingest_financials(
    provider: MarketDataProvider | None = None, batch_size: int = BATCH_SIZE
) -> dict:
    """Fetch + upsert a financial snapshot for every symbol in the universe.

    Same batching + per-symbol isolation as ingest_universe (D19). A symbol
    whose provider data is entirely missing still produces a row (all NULLs);
    a provider failure is isolated and logged.
    """
    provider = provider or build_default_market_provider()

    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    if not symbols:
        logger.warning("No symbols found for universe '%s'.", UNIVERSE_NAME)
        return {"fetched": 0, "rows": 0, "errors": 0}

    rows = 0
    errors: list[str] = []

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_financials(provider, s) for s in batch),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest financials for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                rows += 1

    logger.info(
        "Financials ingestion done: %d symbols, %d rows, %d errors",
        len(symbols) - len(errors),
        rows,
        len(errors),
    )
    return {"fetched": len(symbols) - len(errors), "rows": rows, "errors": len(errors)}


# --- Financial-period history ingestion (Phase 6.5 Part E) ---


def _financial_period_rows(stock_id: int, drafts: list) -> list[dict]:
    """Map provider FinancialPeriodDraft objects onto table columns."""
    return [
        {
            "stock_id": stock_id,
            "period_end": d.period_end,
            "period_type": d.period_type,
            "revenue": d.revenue,
            "net_income": d.net_income,
            "operating_margin": d.operating_margin,
            "net_margin": d.net_margin,
            "eps": d.eps,
            "source": d.source or "unknown",
        }
        for d in drafts
    ]


async def _fetch_one_financial_periods(
    provider: MarketDataProvider, symbol: str, period_type: str
) -> tuple[str, int]:
    """Fetch + upsert one symbol's income-statement periods (annual/quarterly).

    Returns (symbol, periods_stored). A provider without this capability
    (NotImplementedError) is not an error: the symbol simply stores nothing.
    Raises MarketDataError upward so callers can isolate failures per symbol.
    """
    try:
        drafts = await _with_retry(
            lambda: provider.get_financial_history(symbol, period_type),
            what=f"{period_type} financial history fetch for {symbol}",
        )
    except NotImplementedError:
        logger.info("Provider has no financial history for %s; skipping.", symbol)
        return symbol, 0

    if not drafts:
        return symbol, 0

    async with SessionLocal() as session:
        stock_id = await session.scalar(
            select(Stock.id).where(Stock.symbol == symbol)
        )
        if stock_id is None:
            raise MarketDataError(f"Symbol {symbol} not in DB catalog")

        rows = _financial_period_rows(stock_id, drafts)
        stmt = pg_insert(FinancialPeriod).values(rows)
        # One row per (stock, period_end, period_type): overwrite on conflict
        # and refresh ingested_at so re-ingestion stays idempotent and fresh.
        # Field-level COALESCE (incident 2026-09-09): a sparse provider
        # response must never null out a previously-good stored figure —
        # a None revenue the provider omits tonight keeps its stored value.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_financial_periods_stock_period",
            set_={
                "revenue": func.coalesce(stmt.excluded.revenue, FinancialPeriod.revenue),
                "net_income": func.coalesce(stmt.excluded.net_income, FinancialPeriod.net_income),
                "operating_margin": func.coalesce(stmt.excluded.operating_margin, FinancialPeriod.operating_margin),
                "net_margin": func.coalesce(stmt.excluded.net_margin, FinancialPeriod.net_margin),
                "eps": func.coalesce(stmt.excluded.eps, FinancialPeriod.eps),
                "source": stmt.excluded.source,
                "ingested_at": func.now(),
            },
        )
        await session.execute(stmt)
        await session.commit()
        return symbol, len(rows)


async def ingest_financial_periods(
    provider: MarketDataProvider | None = None, batch_size: int = BATCH_SIZE
) -> dict:
    """Ingest ~5 years of annual income-statement history for the universe.

    Same batching + per-symbol isolation as the other ingestions (D19).
    Missing periods stay missing: the provider decides what exists and the
    job never fabricates a value.
    """
    provider = provider or build_default_market_provider()

    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    if not symbols:
        logger.warning("No symbols found for universe '%s'.", UNIVERSE_NAME)
        return {"fetched": 0, "rows": 0, "errors": 0}

    rows = 0
    error_symbols: set[str] = set()

    # Both granularities: annual gives the multi-year view, quarterly the
    # recent-quarters view. Failures are isolated per symbol per pass.
    for period_type in ("annual", "quarterly"):
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            results = await asyncio.gather(
                *(_fetch_one_financial_periods(provider, s, period_type) for s in batch),
                return_exceptions=True,
            )
            for symbol, res in zip(batch, results):
                if isinstance(res, Exception):
                    logger.error(
                        "Failed to ingest %s financial history for %s: %s",
                        period_type, symbol, res,
                    )
                    error_symbols.add(symbol)
                else:
                    _, stored = res
                    rows += stored

    logger.info(
        "Financial history ingestion done: %d symbols, %d periods, %d errors",
        len(symbols) - len(error_symbols),
        rows,
        len(error_symbols),
    )
    return {
        "fetched": len(symbols) - len(error_symbols),
        "rows": rows,
        "errors": len(error_symbols),
    }


# --- News + sentiment ingestion (Phase 3) ---


async def _upsert_articles(
    session: AsyncSession, articles: list[Article]
) -> dict[str, int]:
    """Upsert a symbol's articles by URL; return {inserted, existing}.

    Idempotency anchor is the article URL (unique). Uses a single
    ON CONFLICT DO NOTHING statement, which is safe under concurrent inserts
    (the same Google News article may be fetched for multiple symbols at once).

    An empty article list returns before building the statement: the values
    list would otherwise be empty and SQLAlchemy renders
    INSERT INTO news_articles DEFAULT VALUES, which trips the symbol NOT NULL
    constraint and fails the symbol's news pass (incident 2026-09-09).
    """
    if not articles:
        return {"inserted": 0, "existing": 0}
    stmt = pg_insert(NewsArticle).values(
        [
            {
                "symbol": a.symbol,
                "source": a.source,
                "title": a.title,
                "url": a.url,
                "published_at": a.published_at,
                "content": a.content,
            }
            for a in articles
        ]
    )
    stmt = stmt.on_conflict_do_nothing(constraint="uq_news_articles_url")
    result = await session.execute(stmt)
    await session.commit()
    inserted = result.rowcount
    return {"inserted": max(inserted, 0), "existing": len(articles) - max(inserted, 0)}


async def _score_unscored(session: AsyncSession, symbol: str, scorer: FinBERTScorer) -> int:
    """Score articles for a symbol that have no sentiment row yet. Returns count."""
    unscored = (
        await session.execute(
            select(NewsArticle)
            .outerjoin(NewsSentiment, NewsSentiment.article_id == NewsArticle.id)
            .where(
                NewsArticle.symbol == symbol,
                NewsSentiment.id.is_(None),
            )
        )
    ).scalars().all()

    scored = 0
    for article in unscored:
        sentiment = await scorer.score_text_async(article.title)
        session.add(
            NewsSentiment(
                article_id=article.id,
                label=sentiment.label,
                score=sentiment.score,
                model="ProsusAI/finbert",
            )
        )
        scored += 1
    await session.commit()
    return scored


async def _fetch_and_store_one(
    provider: NewsProvider, scorer: FinBERTScorer, symbol: str, name: str | None
) -> dict:
    """Fetch + store + score one symbol's news. Returns counts.

    The stock's full name is passed through so the provider can run its
    primary company-name search; relevance filtering happens in the provider.
    """
    articles = await _with_retry(
        lambda: provider.fetch_articles(symbol, company_name=name),
        what=f"news fetch for {symbol}",
    )

    async with SessionLocal() as session:
        upsert = await _upsert_articles(session, articles)
        scored = await _score_unscored(session, symbol, scorer)
    return {**upsert, "scored": scored}


async def ingest_news(
    provider: NewsProvider | None = None,
    scorer: FinBERTScorer | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """Fetch + store + FinBERT-score news for every symbol in the universe.

    Follows the same batching + per-symbol isolation as the other ingestions
    (D19). A symbol whose provider fails is isolated and logged.
    """
    provider = provider or GoogleNewsRSSProvider()
    scorer = scorer or FinBERTScorer()

    async with SessionLocal() as session:
        universe = await _get_universe_symbols_and_names(session)

    if not universe:
        logger.warning("No symbols found for universe '%s'.", UNIVERSE_NAME)
        return {"fetched": 0, "inserted": 0, "scored": 0, "errors": 0}

    # Words shared by many company names in the universe ("bank", "hdfc",
    # "tata") never attach an article to one company on their own.
    if hasattr(provider, "generic_tokens"):
        provider.generic_tokens = generic_tokens_from_names(n for _, n in universe if n)

    total_inserted = 0
    total_scored = 0
    errors: list[str] = []

    for i in range(0, len(universe), batch_size):
        batch = universe[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_and_store_one(provider, scorer, s, n) for s, n in batch),
            return_exceptions=True,
        )
        for (symbol, _name), res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest news for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                total_inserted += res["inserted"]
                total_scored += res["scored"]

    logger.info(
        "News ingestion done: %d symbols, %d new articles, %d scored, %d errors",
        len(universe),
        total_inserted,
        total_scored,
        len(errors),
    )
    return {
        "fetched": len(universe) - len(errors),
        "inserted": total_inserted,
        "scored": total_scored,
        "errors": len(errors),
    }

# --- Alpha history backfill (retroactive snapshots, user decision 2026-09-06) ---


async def _backfill_one_alpha(
    symbol: str,
    stats: dict[str, int] | None = None,
    strength_by_day: dict | None = None,
) -> int:
    """Retroactively compute alpha snapshots for every stored trading day.

    Methodology v2.0: the composite's price pillar is the stock's Strength
    rank on that day (`strength_by_day`, from
    strength_repo.get_strength_history), not the technical score. A day
    without a Strength rank (the first year of stored prices, or a share
    that was not rankable then) keeps its technical value but has no
    composite, so the Alpha line starts where Strength can be computed and
    never mixes the two methods.

    For each bar date past indicator warm-up, the technical score is computed
    from the closes UP TO that date (real math on real stored prices, EMA-
    smoothed exactly like the live score). Fundamental and sentiment have NO
    stored history, so they are NOT written for backfilled dates - a flat
    carried-forward line would present today's values as if they were daily
    observations. The historical composite still blends the latest known
    fundamental + sentiment (documented approximation, PLANNING D71) so the
    Alpha line remains a real 40/30/30 signal rather than collapsing to the
    technical score; the per-component history fills in only as genuine
    ingestion snapshots accumulate (record_live_alpha_snapshots, Phase 8).
    Existing technical-only snapshots are synced to the recomputed series
    (alpha_repo.sync_backfill_snapshots: one transaction, unchanged rows not
    written, stale dates deleted) so the whole series follows the current
    formula. Returns the number of snapshots computed; `stats`, when given,
    accumulates inserted / updated / unchanged / deleted counts.
    """
    from app.repositories import alpha as alpha_repo
    from app.repositories import financials as fin_repo
    from app.repositories import news as news_repo
    from app.services import altman as altman_svc
    from app.services import indicators, scores as score_svc
    from app.services.alpha import _renormalized, blend_fundamental

    async with SessionLocal() as session:
        stock = await session.scalar(select(Stock).where(Stock.symbol == symbol))
        if stock is None:
            return 0
        bars = (
            await session.execute(
                select(DailyPrice.date, DailyPrice.close)
                .where(DailyPrice.stock_id == stock.id)
                .order_by(DailyPrice.date.asc())
            )
        ).all()

        # Latest known fundamental pillar (v1.5: profitability + solvency +
        # Altman distress from the stored balance sheet), slow-moving.
        fundamental: int | None = None
        fundamentals = await fin_repo.get_financials(session, stock)
        profit_score = solvency_score = None
        if fundamentals is not None:
            profit = score_svc.profitability_score(fundamentals)
            solvency = score_svc.solvency_score(fundamentals)
            profit_score, solvency_score = profit.score, solvency.score
        altman_result = await altman_svc.compute_stock_altman(session, stock)
        distress_score = None
        if (
            altman_result.status == altman_svc.STATUS_AVAILABLE
            and altman_result.score is not None
        ):
            distress_score = altman_svc.distress_score_0_100(altman_result.score)
        fundamental = blend_fundamental(profit_score, solvency_score, distress_score)

        # Latest known sentiment (slow-moving aggregate of recent headlines).
        sentiment: int | None = None
        summary = await news_repo.get_sentiment_summary(session, symbol)
        if summary and summary["count"]:
            sentiment = round((summary["score"] + 1.0) / 2.0 * 100.0)

    if len(bars) < 26:
        return 0

    dates = [b.date for b in bars]
    closes = [float(b.close) for b in bars]
    scored_series = indicators.score_technicals_series(closes)

    rows: list[dict] = []
    for i, scored in enumerate(scored_series):
        if scored is None or scored.get("score") is None:
            continue
        components = dict(scored.get("components") or {})
        day_strength = (strength_by_day or {}).get(dates[i])
        composite = None
        if day_strength is not None:
            components["strength"] = day_strength
            composite, _ = _renormalized(fundamental, round(day_strength), sentiment)
        rows.append(
            {
                "symbol": symbol,
                "date": dates[i],
                "composite": composite,
                # No stored history for these components: carried-forward
                # values would render as a flat, fabricated-looking line.
                "fundamental": None,
                "technical": scored["score"],
                "sentiment": None,
                "components_json": components,
            }
        )

    if not rows:
        return 0

    # Make the symbol's TECHNICAL-ONLY snapshots equal the recomputed series,
    # in one transaction: changed rows are updated, unchanged rows are not
    # written, stale dates are deleted. Rows that carry a genuine live
    # fundamental score are PRESERVED — wiping them every night would make
    # per-component history impossible. Only reached when there is something
    # to write (an empty recompute never deletes stored history).
    async with SessionLocal() as session:
        counts = await alpha_repo.sync_backfill_snapshots(session, symbol, rows)
    if stats is not None:
        for key, value in counts.items():
            stats[key] = stats.get(key, 0) + value
    return len(rows)


async def record_live_alpha_snapshot(symbol: str) -> bool:
    """Persist today's computed alpha snapshot for one symbol (Phase 8).

    Ownership of snapshot writes moved here from GET /alpha (which is now
    pure read). Called by the ingestion pathway — currently the nightly
    backfill sweep covers history; this helper covers the "today" row so a
    day's live view still accumulates per-component history without any
    request-time write. Returns True when a snapshot was stored.

    The snapshot is dated by the stock's LATEST STORED BAR, not the runner's
    calendar date (work list item 17). The nightly runs every day and GitHub
    often starts it after midnight UTC, so calendar dating produced rows on
    weekends and holidays (4,010 of 18,305 live rows on 2026-11-10) that
    describe the previous trading day's prices. Dating by the bar keeps every
    snapshot on a real trading day; a re-run on a non-trading day refreshes
    that day's row instead of adding a new one. Only a stock with no stored
    bars at all falls back to the calendar date (previous behaviour).
    """
    from datetime import date

    from app.repositories import alpha as alpha_repo
    from app.services import alpha as alpha_svc

    async with SessionLocal() as session:
        stock = await session.scalar(select(Stock).where(Stock.symbol == symbol))
        if stock is None:
            return False
        result = await alpha_svc.compute_alpha(session, stock)
        if result.composite is None:
            return False
        last_bar = await session.scalar(
            select(func.max(DailyPrice.date)).where(DailyPrice.stock_id == stock.id)
        )
        await alpha_repo.upsert_snapshot(
            session,
            symbol=stock.symbol,
            snapshot_date=last_bar or date.today(),
            composite=result.composite,
            fundamental=result.fundamental,
            technical=result.technical,
            sentiment=result.sentiment,
            components_json=result.components,
        )
        return True


async def record_live_alpha_snapshots(batch_size: int = BATCH_SIZE) -> dict:
    """Persist today's snapshot for every catalog symbol (ingestion pass).

    Wired into the nightly sweep after the backfill so history stays current
    without request-time writes. Per-symbol isolation: one bad symbol never
    aborts the pass.
    """
    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    stored = 0
    errors: list[str] = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(record_live_alpha_snapshot(s) for s in batch), return_exceptions=True
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Live alpha snapshot failed for %s: %s", symbol, res)
                errors.append(symbol)
            elif res:
                stored += 1

    logger.info("Live alpha snapshots stored: %d, errors: %d", stored, len(errors))
    return {"stored": stored, "errors": len(errors)}


async def record_strength_scores(today: date | None = None) -> dict:
    """Rank the whole list on one-year price strength and store the result.

    Strength and steadiness are ranks among the shares on the list, so they
    are computed for every share in one pass (services/strength.py). The
    figures are merged into each share's alpha row for its latest bar, which
    record_live_alpha_snapshots has just written; this pass must run after
    it. No provider calls. A share without about 13 months of closes, with a
    stale last bar, or with a one-day move of 40% or more in the window is
    left without a score.

    Since methodology v2.0 Strength is the composite's price pillar: after
    storing the ranks this pass re-blends the composite of the rows it
    touched (strength_repo.recompose_composites).
    """
    from app.repositories import strength as strength_repo
    from app.services import strength as strength_svc

    async with SessionLocal() as session:
        facts = await strength_repo.get_price_facts(
            session, today or date.today(), universe_name=UNIVERSE_NAME
        )
    if not facts:
        logger.info("Strength scores: no stored prices for universe '%s'", UNIVERSE_NAME)
        return {"stored": 0, "skipped": 0, "errors": 0}

    reference = max(f.last_date for f in facts.values())
    inputs: dict[str, strength_svc.Inputs] = {}
    reasons: dict[str, int] = {}
    for symbol, fact in facts.items():
        ready, reason = strength_svc.inputs_for(fact, reference)
        if ready is not None:
            inputs[symbol] = ready
        else:
            reasons[reason] = reasons.get(reason, 0) + 1

    ratings = strength_svc.rate_list(inputs)
    rated = []
    for symbol, rating in ratings.items():
        patch = {strength_repo.KEY_STRENGTH: rating.strength}
        if rating.steadiness is not None:
            patch[strength_repo.KEY_STEADINESS] = rating.steadiness
        rated.append((symbol, facts[symbol].last_date, patch))
    unrated = [(s, f.last_date) for s, f in facts.items() if s not in ratings]

    async with SessionLocal() as session:
        counts = await strength_repo.store_ratings(session, rated, unrated)
        # Methodology v2.0: Strength is the composite's price pillar, so the
        # rows the live pass wrote tonight (with yesterday's rank) are
        # re-blended now that today's rank is stored.
        counts["recomposed"] = await strength_repo.recompose_composites(
            session, [(s, f.last_date) for s, f in facts.items()]
        )

    logger.info(
        "Strength scores: rated=%d of %d written=%d cleared=%d recomposed=%d not_rated=%s",
        len(rated), len(facts), counts["written"], counts["cleared"],
        counts["recomposed"], reasons,
    )
    return {"stored": len(rated), "skipped": len(unrated), "errors": 0}


# --- Tiered schedule (work list item 29, owner decision 2026-11-14) ---------
# Some passes fetch data that changes only when a company files results, so
# they run on an interval instead of every night. "Due" is judged from the
# pass's own last successful run in job_runs, not from the weekday: the
# nightly skips weekends and NSE holidays (ingest.yml), so a fixed weekday
# could be skipped for a whole week, while an interval always catches up on
# the next run. INGEST_ALL_PASSES=1 (the workflow's all_passes input) runs
# every pass tonight.
WEEKLY_DAYS = 7
RESULTS_SEASON_DAYS = 3
# A run that starts a little later than last week's is still on time.
_DUE_SLACK = timedelta(hours=12)

# Statements change only when results are filed: weekly, every third day in
# results season. Company profiles (business summary, CEO, staff) weekly.
FINANCIAL_PASSES = ("ingest_financial_periods", "ingest_balance_sheets")
WEEKLY_PASSES = ("ingest_company_profiles",)

# Weekly full alpha-history recompute (owner decision 2026-11-13, to keep
# Neon network transfer inside the free 5 GB a month). The full pass
# re-reads every stock's ~2 years of closes (~15-25 MB). Today's snapshot is
# still written nightly by record_live_alpha_snapshots; what moves to weekly
# is the refresh of PAST points. Stocks with little or no history are still
# filled every night, so a newly added stock gets its chart at once. The
# full run is recorded under its own job name so its interval can be read.
ALPHA_FULL_JOB = "backfill_alpha_history_full"
# Days of past Strength ranks fetched for the history (covers the ~2 years
# of stored prices; the first year has no rank).
ALPHA_HISTORY_DAYS = 800
ALPHA_MIN_HISTORY_ROWS = 100  # fewer stored snapshots = backfill tonight


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def in_results_season(today: date) -> bool:
    """True while quarterly results are being filed (SEBI deadlines).

    Results are due within 45 days of a quarter's end (60 for the March
    quarter), and most arrive in the second half of that window:
    10 Jan-20 Feb, 10 Apr-31 May, 10 Jul-20 Aug, 10 Oct-20 Nov.
    """
    m, d = today.month, today.day
    if m in (1, 4, 7, 10):
        return d >= 10
    if m in (2, 8, 11):
        return d <= 20
    return m == 5


async def _pass_due(name: str, interval_days: int, now: datetime | None = None) -> bool:
    """True when `name` has no successful run within `interval_days` (minus slack)."""
    async with SessionLocal() as session:
        last = await session.scalar(
            select(func.max(JobRun.started_at)).where(
                JobRun.job_name == name, JobRun.status.in_(("success", "partial"))
            )
        )
    if last is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now - last >= timedelta(days=interval_days) - _DUE_SLACK


async def _alpha_full_backfill_due(now: datetime | None = None) -> bool:
    if _env_flag("ALPHA_BACKFILL_FULL") or _env_flag("INGEST_ALL_PASSES"):
        return True
    return await _pass_due(ALPHA_FULL_JOB, WEEKLY_DAYS, now)


async def _symbols_missing_alpha_history(session, symbols: list[str]) -> list[str]:
    """Universe symbols with fewer than ALPHA_MIN_HISTORY_ROWS snapshots.

    One aggregate query returning a count per symbol: almost no bytes.
    """
    if not symbols:
        return []
    rows = await session.execute(
        select(AlphaScore.symbol, func.count())
        .where(AlphaScore.symbol.in_(symbols))
        .group_by(AlphaScore.symbol)
    )
    counts = dict(rows.all())
    return [s for s in symbols if counts.get(s, 0) < ALPHA_MIN_HISTORY_ROWS]


async def backfill_alpha_history(
    batch_size: int = BATCH_SIZE, full: bool | None = None
) -> dict:
    """Retroactively backfill alpha snapshots for the active universe.

    full=True recomputes every symbol (weekly by ALPHA_FULL_JOB, ALPHA_BACKFILL_FULL=1, or
    the standalone `backfill` command); otherwise only symbols with little
    or no stored history are done (see ALPHA_FULL_JOB).
    Idempotent: existing technical-only rows are recomputed; full live
    snapshots (with a fundamental score) are preserved. Failures are
    isolated per symbol (D19).
    """
    if full is None:
        full = await _alpha_full_backfill_due()
    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)
        if not full:
            symbols = await _symbols_missing_alpha_history(session, symbols)
    logger.info(
        "Alpha history backfill: %s, %d symbols",
        "full weekly recompute" if full else "missing-history only", len(symbols),
    )

    # Strength on every past day (v2.0 price pillar), ranked over the whole
    # list inside PostgreSQL; only these symbols' values leave the database.
    from app.repositories import strength as strength_repo

    # Only on the weekly full recompute: the query ranks every stored day of
    # the whole list (measured locally: ~25 s, ~8.6 MB out). The nightly
    # top-up covers stocks with little history, which have no full year of
    # prices and so no Strength yet; their past days get an Alpha point on
    # the next weekly full recompute, and today's comes from the live pass.
    strength_history: dict = {}
    if symbols and full:
        async with SessionLocal() as session:
            strength_history = await strength_repo.get_strength_history(
                session,
                UNIVERSE_NAME,
                since=date.today() - timedelta(days=ALPHA_HISTORY_DAYS),
            )

    total = 0
    errors: list[str] = []
    written: dict[str, int] = {**_new_write_stats(), "deleted": 0}
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_backfill_one_alpha(s, written, strength_history.get(s)) for s in batch),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Alpha backfill failed for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                total += res

    # `snapshots` stays the number computed (historical meaning); the write
    # split shows what actually reached the table.
    logger.info(
        "Alpha history backfill done: %d snapshots, %d errors "
        "(written: %d inserted, %d updated, %d unchanged, %d stale deleted)",
        total, len(errors),
        written["inserted"], written["updated"],
        written["unchanged"], written["deleted"],
    )
    return {"snapshots": total, "errors": len(errors), "full": full, "symbols": len(symbols), **written}


# --- Company profile ingestion (provider-sourced background) -----------------


async def _fetch_one_profile(provider, symbol: str) -> tuple[str, bool]:
    """Fetch + upsert one symbol's company profile. Returns (symbol, stored).

    Raises MarketDataError upward so callers can isolate failures per symbol.
    """
    profile = await _with_retry(
        lambda: provider.get_company_profile(symbol),
        what=f"company profile fetch for {symbol}",
    )

    async with SessionLocal() as session:
        stock_id = await session.scalar(
            select(Stock.id).where(Stock.symbol == symbol)
        )
        if stock_id is None:
            raise MarketDataError(f"Symbol {symbol} not in DB catalog")
        await profile_repo.upsert_profile(
            session,
            stock_id=stock_id,
            business_summary=profile.business_summary,
            ceo=profile.ceo,
            employees=profile.employees,
            website=profile.website,
            source=getattr(provider, "name", None),
        )
        # Classification enrichment (markets/screener sector filters need it):
        # ranking-created rows carry NULL sector/industry. Fetch the merged
        # stock profile ONLY for stocks still missing classification (one
        # extra provider call for the gap rows, none for classified ones) and
        # fill the NULL columns — never overwrite an existing value.
        stock_row = await session.get(Stock, stock_id)
        needs_class = stock_row is not None and (
            stock_row.sector is None or stock_row.industry is None
        )
        stock_id_resolved = stock_id
    if needs_class:
        try:
            sp = await provider.get_stock_profile(symbol)
        except NotImplementedError:
            sp = None
        except MarketDataError:
            # Classification is best-effort: the profile itself still stored.
            logger.info("classification fetch failed for %s; sector stays null", symbol)
            sp = None
        if sp is not None and (sp.sector is not None or sp.industry is not None):
            async with SessionLocal() as session:
                row = await session.get(Stock, stock_id_resolved)
                if row is not None:
                    if row.sector is None and sp.sector is not None:
                        row.sector = sp.sector
                    if row.industry is None and sp.industry is not None:
                        row.industry = sp.industry
                await session.commit()
    return symbol, True


async def ingest_company_profiles(
    provider=None, batch_size: int = BATCH_SIZE
) -> dict:
    """Fetch + store a company background profile for every catalog symbol.

    Same batching + per-symbol isolation as the other ingestions (D19).
    business_summary is the provider's verbatim description text; fields the
    provider does not supply stay None (never generated).
    """
    provider = provider or build_default_market_provider()

    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    if not symbols:
        logger.warning("No symbols found for universe '%s'.", UNIVERSE_NAME)
        return {"fetched": 0, "rows": 0, "errors": 0}

    rows = 0
    errors: list[str] = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_profile(provider, s) for s in batch),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest company profile for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                rows += 1

    logger.info(
        "Company profile ingestion done: %d symbols, %d rows, %d errors",
        len(symbols) - len(errors),
        rows,
        len(errors),
    )
    return {"fetched": len(symbols) - len(errors), "rows": rows, "errors": len(errors)}


# --- Alpha explanation pre-warm (cache warm before any user visits) ----------

# Free OpenRouter models are rate-limited; a small pause between pre-warm
# calls keeps the nightly sweep inside the per-minute limits.
PREWARM_DELAY_SECONDS = 2.0


async def prewarm_alpha_explanations(delay: float = PREWARM_DELAY_SECONDS) -> dict:
    """Warm the alpha explanation TTL cache for the whole active universe.

    Runs right after the nightly alpha backfill (D67) inside the API process:
    the in-process cache is keyed (symbol, date), so a pre-warm at 18:35
    serves every user the next day with zero LLM latency and zero
    first-visit cost. Respects the SHARED daily cap (llm_narrative.budget_ok)
    so the pre-warm can never crowd out /ask beyond its allowance; symbols
    past the cap are simply left to lazy first-view computation.
    """
    from app.services import alpha as alpha_svc
    from app.services import llm_narrative

    if not settings.llm_api_key or not settings.llm_model:
        logger.info("explanation pre-warm skipped (LLM not configured)")
        return {"warmed": 0, "errors": 0, "skipped": "llm_not_configured"}

    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    warmed = 0
    failed = 0
    for i, symbol in enumerate(symbols):
        if not llm_narrative.budget_ok():
            logger.info(
                "explanation pre-warm stopped at the daily cap after %d symbols", warmed
            )
            break
        try:
            async with SessionLocal() as session:
                stock = await session.scalar(
                    select(Stock).where(Stock.symbol == symbol)
                )
                if stock is None:
                    continue
                result = await alpha_svc.compute_alpha(session, stock)
            await llm_narrative.generate_alpha_explanation(stock, result)
            warmed += 1
        except Exception as exc:  # one stock must never abort the sweep (D19)
            failed += 1
            logger.warning("explanation pre-warm failed for %s: %s", symbol, exc)
        if delay and i < len(symbols) - 1:
            await asyncio.sleep(delay)

    logger.info(
        "explanation pre-warm done: %d/%d symbols warmed, %d failed",
        warmed, len(symbols), failed,
    )
    return {"warmed": warmed, "errors": failed, "skipped": None}


# --- Catalog repair pass (stocks the universe passes miss) -------------------


async def repair_catalog_gaps(provider: MarketDataProvider | None = None) -> dict:
    """Ingest catalog stocks that the universe-driven passes never touch.

    The universe passes cover index constituents; a catalog stock pruned
    from the index (e.g. TATAMOTORS after its demerger) would otherwise sit
    in the catalog forever with no prices, an empty snapshot and no profile.
    This pass finds stocks with zero stored bars, an all-null financial
    snapshot, or a missing company profile and runs the same fetches for
    them, so no catalog stock is permanently empty. Per-symbol isolation
    (D19) and the idempotent upserts make the pass safe to re-run.
    """
    provider = provider or build_default_market_provider()

    price_gap = ~exists(select(DailyPrice.stock_id).where(DailyPrice.stock_id == Stock.id))
    financials_gap = ~exists(select(Financials.stock_id).where(Financials.stock_id == Stock.id))
    profile_gap = ~exists(select(CompanyProfile.stock_id).where(CompanyProfile.stock_id == Stock.id))

    async with SessionLocal() as session:
        stocks = (
            await session.execute(
                select(Stock).where(
                    (price_gap | financials_gap | profile_gap)
                    & Stock.active.is_(True)
                )
            )
        ).scalars().all()
    # Retired instruments have no source; repairing them fails every night.
    stocks = [s for s in stocks if s.symbol.split(".")[0] not in RETIRED_SYMBOLS]

    if not stocks:
        logger.info("Catalog repair pass: no gaps found.")
        return {"repaired": 0, "errors": 0}

    errors: list[str] = []
    repaired = 0
    for stock in stocks:
        ok = True
        for fetch in (
            lambda s=stock.symbol: _fetch_one_symbol(provider, s),
            lambda s=stock.symbol: _fetch_one_financials(provider, s),
            lambda s=stock.symbol: _fetch_one_profile(provider, s),
        ):
            try:
                await fetch()
            except Exception as exc:
                logger.error("Catalog repair failed for %s: %s", stock.symbol, exc)
                ok = False
        if ok:
            repaired += 1
        else:
            errors.append(stock.symbol)

    logger.info(
        "Catalog repair pass: %d stocks repaired, %d errors (%s)",
        repaired, len(errors), ",".join(errors) or "none",
    )
    return {"repaired": repaired, "errors": len(errors)}


# --- Benchmark index ingestion (M1-T6, Plan 13) ------------------------------

# Required benchmark symbols (Plan 13): Nifty 50 + sector/index breadth.
# Verified 2026-09-08/09: every symbol below serves daily bars from yfinance
# (quoteType INDEX for the NSE/BSE series, CURRENCY for INR=X, FUTURE for
# GC=F); .info carries NO fundamentals for these, so benchmarks ingest
# PRICES ONLY. The list is a module constant (not DB-driven): adding one is
# a one-line diff + test.
BENCHMARK_SYMBOLS: tuple[str, ...] = (
    "^NSEI",       # NIFTY 50
    "INR=X",       # USD/INR
    "GC=F",        # Gold futures (USD)
    "^BSESN",      # BSE SENSEX
    "^INDIAVIX",   # India VIX
    "^NSEBANK",    # NIFTY BANK
    "^CNXIT",      # NIFTY IT
    "^CNXPHARMA",  # NIFTY PHARMA
    "^NSEMDCP50",  # NIFTY MIDCAP 50
    "^CRSLDX",     # CRISIL broad market
)
# Documented limitation: no reliable free smallcap index symbol exists on
# Yahoo (^CNXSC serves zero current bars, verified 2026-09-09), so the
# smallcap segment stays absent rather than stale.
BENCHMARK_PERIOD = "2y"  # same stored depth as the equity price history

# Provider display names for the benchmarks table (yfinance .info shortName
# was read live 2026-09-08; kept as the creation default, refreshed on write).
BENCHMARK_NAMES: dict[str, str] = {
    "^NSEI": "NIFTY 50",
    "INR=X": "USD/INR",
    "GC=F": "GOLD (USD)",
    "^BSESN": "BSE SENSEX",
    "^INDIAVIX": "INDIA VIX",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
    "^CNXPHARMA": "NIFTY PHARMA",
    "^NSEMDCP50": "NIFTY MIDCAP 50",
    "^CRSLDX": "CRISIL BROAD MARKET",
}

# kind distinguishes equity indexes from macro rows (fx/commodity) so the
# UI can order and label them correctly. kind is set at creation only.
BENCHMARK_KINDS: dict[str, str] = {
    "INR=X": "fx",
    "GC=F": "commodity",
}


async def _fetch_one_benchmark(
    provider: MarketDataProvider, symbol: str
) -> tuple[str, int]:
    """Fetch + upsert one index's price history. Returns (symbol, bars_offered).

    Benchmarks ingest through the SAME provider interface as equities
    (yfinance-only: Upstox serves no index bars) but persist to the separate
    benchmarks tables — never the equity catalog — so benchmark data cannot
    interfere with ranking, valuation or peer sets. Raises MarketDataError
    upward so callers isolate per-index failures (D19).
    """
    bars = await _with_retry(
        lambda: provider.get_price_history(symbol, BENCHMARK_PERIOD),
        what=f"benchmark price fetch for {symbol}",
    )
    if not bars:
        logger.warning("No benchmark price data for %s; skipping.", symbol)
        return symbol, 0

    async with SessionLocal() as session:
        row = await benchmark_repo.get_or_create_benchmark(
            session,
            symbol=symbol,
            name=BENCHMARK_NAMES.get(symbol),
            source=getattr(provider, "name", None) or "yfinance",
            kind=BENCHMARK_KINDS.get(symbol, "index"),
        )
        benchmark_id = row.id
        offered = await benchmark_repo.upsert_bars(session, benchmark_id, bars)
        return symbol, offered


async def ingest_benchmarks(
    provider: MarketDataProvider | None = None,
    symbols: tuple[str, ...] = BENCHMARK_SYMBOLS,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """Fetch + upsert price history for every benchmark index symbol.

    Same batching + per-index isolation as the equity passes (D19). Recorded
    as its own job_runs pass ("ingest_benchmarks") so its runtime and storage
    contribution are measured separately in the M1-T3/T4 report.
    """
    provider = provider or YFinanceProvider()

    bars = 0
    errors: list[str] = []

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_benchmark(provider, s) for s in batch),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest benchmark %s: %s", symbol, res)
                errors.append(symbol)
            else:
                _, offered = res
                bars += offered

    logger.info(
        "Benchmark ingestion done: %d symbols, %d bars, %d errors",
        len(symbols) - len(errors),
        bars,
        len(errors),
    )
    return {"fetched": len(symbols) - len(errors), "bars": bars, "errors": len(errors)}


# --- Balance-sheet ingestion (Plan 5.4; drives the real Altman Z-Score) ------

async def _fetch_one_balance_sheet(
    provider: MarketDataProvider, symbol: str
) -> tuple[str, int]:
    """Fetch + upsert one symbol's annual balance-sheet periods.

    A provider without the capability (NotImplementedError) is not an error:
    the symbol stores nothing. Raises MarketDataError upward so callers
    isolate per-symbol failures (D19). Banks/NBFCs legitimately store partial
    rows (no Working Capital) — honesty lives downstream in the Z-Score.
    """
    try:
        drafts = await _with_retry(
            lambda: provider.get_balance_sheet(symbol),
            what=f"balance-sheet fetch for {symbol}",
        )
    except NotImplementedError:
        logger.info("Provider has no balance sheet for %s; skipping.", symbol)
        return symbol, 0

    if not drafts:
        return symbol, 0

    async with SessionLocal() as session:
        stock_id = await session.scalar(
            select(Stock.id).where(Stock.symbol == symbol)
        )
        if stock_id is None:
            raise MarketDataError(f"Symbol {symbol} not in DB catalog")
        stored = await bs_repo.upsert_periods(session, stock_id, drafts)
        return symbol, stored


async def ingest_balance_sheets(
    provider: MarketDataProvider | None = None, batch_size: int = BATCH_SIZE
) -> dict:
    """Fetch + upsert annual balance sheets for the active universe.

    Same batching + per-symbol isolation as the other ingestions (D19).
    Rows are small (about four annual periods per stock) and feed the real
    Altman Z-Score computation directly.
    """
    provider = provider or build_default_market_provider()

    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    if not symbols:
        logger.warning("No symbols found for universe '%s'.", UNIVERSE_NAME)
        return {"fetched": 0, "rows": 0, "errors": 0}

    rows = 0
    errors: list[str] = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_balance_sheet(provider, s) for s in batch),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest balance sheet for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                _, stored = res
                rows += stored

    logger.info(
        "Balance-sheet ingestion done: %d symbols, %d periods, %d errors",
        len(symbols) - len(errors),
        rows,
        len(errors),
    )
    return {"fetched": len(symbols) - len(errors), "rows": rows, "errors": len(errors)}


# --- Shareholding pattern (checklist 6, step 3) -------------------------------

# Most stocks fetched per night. The pattern changes once a quarter, the
# provider's rate limit for this endpoint is not documented, and the nightly
# has a time budget: a bounded slice per night covers the whole universe in
# about a week and then idles until the next quarter is published.
SHAREHOLDING_NIGHTLY_CAP = 150
# Listed companies file the pattern within 21 days of the quarter end.
SHAREHOLDING_FILING_DAYS = 21


def expected_shareholding_quarter(today: date) -> date:
    """The newest quarter end whose filing deadline has passed by `today`."""
    year, month = today.year, today.month
    # Walk back over calendar quarter ends (Mar/Jun/Sep/Dec) from this month.
    quarter_month = ((month - 1) // 3 + 1) * 3
    for _ in range(3):
        last_day = calendar.monthrange(year, quarter_month)[1]
        quarter_end = date(year, quarter_month, last_day)
        if quarter_end + timedelta(days=SHAREHOLDING_FILING_DAYS) <= today:
            return quarter_end
        quarter_month -= 3
        if quarter_month <= 0:
            quarter_month += 12
            year -= 1
    raise AssertionError("unreachable: a filed quarter always exists within 9 months")


def shareholding_due_slice(
    coverage: list[tuple[str, date | None]], today: date, cap: int
) -> list[str]:
    """Tonight's symbols: stocks missing the expected quarter, at most `cap`.

    `coverage` is [(symbol, latest stored quarter end | None)] ordered by
    symbol. When more stocks are due than the cap allows, the window rotates
    by day so a stock the provider has nothing for (always "due") can never
    starve the others.
    """
    expected = expected_shareholding_quarter(today)
    due = [s for s, latest in coverage if latest is None or latest < expected]
    if len(due) <= cap:
        return due
    start = (today.toordinal() * cap) % len(due)
    return (due + due)[start : start + cap]


async def _fetch_one_shareholding(provider, symbol: str) -> tuple[str, int]:
    """Fetch + upsert one symbol's quarters (per-symbol isolation, D19)."""
    drafts = await _with_retry(
        lambda: provider.get_shareholding(symbol),
        what=f"shareholding fetch for {symbol}",
    )
    if not drafts:
        return symbol, 0
    async with SessionLocal() as session:
        stock_id = await session.scalar(select(Stock.id).where(Stock.symbol == symbol))
        if stock_id is None:
            raise MarketDataError(f"Symbol {symbol} not in DB catalog")
        stored = await shareholding_repo.upsert_periods(session, stock_id, drafts)
        return symbol, stored


async def ingest_shareholding(
    provider=None,
    batch_size: int = BATCH_SIZE,
    cap: int = SHAREHOLDING_NIGHTLY_CAP,
    today: date | None = None,
) -> dict:
    """Fetch the shareholding pattern for the stocks that are due tonight.

    Upstox is the only source. Three quiet no-ops, each logged and returned
    as a zero-count result rather than an error: no Upstox token configured,
    the shareholding_periods table not migrated yet, or nothing due.
    """
    empty = {"fetched": 0, "rows": 0, "errors": 0}
    if provider is None:
        token = (settings.upstox_analytics_token or "").strip()
        if not token:
            logger.info("Shareholding ingestion skipped: no Upstox token configured.")
            return empty
        provider = UpstoxProvider(token)

    async with SessionLocal() as session:
        if not await shareholding_repo.table_exists(session):
            logger.warning(
                "Shareholding ingestion skipped: shareholding_periods is not migrated."
            )
            return empty
        coverage = await shareholding_repo.get_universe_coverage(session, UNIVERSE_NAME)

    symbols = shareholding_due_slice(coverage, today or date.today(), cap)
    if not symbols:
        logger.info("Shareholding ingestion: nothing due.")
        return empty

    rows = 0
    errors: list[str] = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_shareholding(provider, s) for s in batch),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest shareholding for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                rows += res[1]

    logger.info(
        "Shareholding ingestion done: %d symbols, %d quarters, %d errors",
        len(symbols) - len(errors), rows, len(errors),
    )
    return {"fetched": len(symbols) - len(errors), "rows": rows, "errors": len(errors)}


# --- ETF catalog ingestion (Plan 9 slice; is_etf stocks + prices) ------------

# Display names for the curated ETF list (data/ranking_exclusions.ETF_SYMBOLS
# is the single source of the symbol set — the SAME list the ranking uses to
# exclude ETFs from the equity universe, so the two can never drift).
ETF_NAMES: dict[str, str] = {
    "NIFTYBEES": "Nippon India ETF Nifty 50 BeES",
    "JUNIORBEES": "Nippon India ETF Nifty Next 50 BeES",
    "BANKBEES": "Nippon India ETF Bank BeES",
    "GOLDBEES": "Nippon India ETF Gold BeES",
    "SILVERBEES": "Nippon India Silver ETF",
    "LIQUIDBEES": "Nippon India ETF Liquid BeES",
    "HDFCNIFTY": "HDFC Nifty 50 ETF",
    "NIFTYIETF": "ICICI Prudential Nifty 50 ETF",
    "ITBEES": "Nippon India ETF IT BeES",
    "PSUBNKBEES": "Nippon India ETF PSU Bank BeES",
    "MOM100": "Motilal Oswal M100 ETF",
    "MON100": "Motilal Oswal NASDAQ 100 ETF",
    "MAFANG": "Mirae Asset NYSE FANG+ ETF",
    "MAKEINDIA": "Motilal Oswal Mfg India ETF",
    "MOM50": "Motilal Oswal M50 ETF",
    "HDFCMID150": "HDFC Nifty Midcap 150 ETF",
}


async def _ensure_etf_catalog(session) -> int:
    """Get-or-create stocks rows (is_etf=True) for the curated ETF symbols."""
    created = 0
    for bare in sorted(ETF_SYMBOLS):
        symbol = f"{bare}.NS"
        existing = await session.scalar(select(Stock).where(Stock.symbol == symbol))
        if existing is not None:
            if not existing.is_etf:
                existing.is_etf = True
            continue
        session.add(
            Stock(
                symbol=symbol,
                name=ETF_NAMES.get(bare, bare),
                is_etf=True,
            )
        )
        created += 1
    # Curated ETFs that left the list (renamed or retired) drop off the ETF
    # pages; the row and its price history are kept.
    stale = (
        await session.execute(select(Stock).where(Stock.is_etf.is_(True), Stock.active.is_(True)))
    ).scalars().all()
    for row in stale:
        bare = row.symbol.split(".")[0]
        if bare not in ETF_SYMBOLS:
            row.active = False
            row.delisted_reason = "retired"
            row.delisted_at = datetime.now(timezone.utc)
    if created:
        await session.flush()
    return created


async def ingest_etfs(
    provider: MarketDataProvider | None = None,
    batch_size: int = BATCH_SIZE,
    today: date | None = None,
) -> dict:
    """Ensure the curated ETF catalog rows exist and fetch their price history.

    ETFs reuse the EQUITY price pipeline (daily_prices via stocks rows flagged
    is_etf) but never enter universes, the screener or the /stocks list —
    they surface only through GET /etfs. Per-symbol isolation (D19).
    today is forwarded to the freshness guard (None = real clock).
    """
    provider = provider or build_default_market_provider()

    async with SessionLocal() as session:
        created = await _ensure_etf_catalog(session)
        await session.commit()
    if created:
        logger.info("ETF catalog: %d rows created", created)

    symbols = [f"{bare}.NS" for bare in sorted(ETF_SYMBOLS)]
    bars = 0
    errors: list[str] = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_symbol(provider, s, today) for s in batch),
            return_exceptions=True,
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Failed to ingest ETF prices for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                _, stored = res
                bars += stored

    logger.info(
        "ETF ingestion done: %d symbols, %d bars, %d errors",
        len(symbols) - len(errors),
        bars,
        len(errors),
    )
    return {"fetched": len(symbols) - len(errors), "bars": bars, "errors": len(errors)}


# --- Mutual-fund ingestion (Plan 8 slice: AMFI daily NAV, curated catalog) ----

async def ingest_funds(
    backfill_history: bool = False,
    client=None,
) -> dict:
    """Sync the curated fund catalog with the official AMFI NAVAll file.

    For every curated entry matched in today's file: get-or-create the fund
    row (AMFI verbatim name, plan/option) and upsert the daily NAV point
    (idempotent by fund+date). backfill_history=True additionally pulls each
    matched scheme's NAV history from api.mfapi.in (documented FALLBACK
    source, rows tagged source='mfapi') so 1m/3m/6m returns exist on day
    one; the nightly AMFI point keeps history current thereafter.
    Failures are isolated per fund (D19).
    """
    text = await fetch_amfi_navall(client=client)
    rows = parse_navall(text)
    if not rows:
        raise MarketDataError("AMFI NAVAll parsed to zero rows; refusing to sync")

    matched: list[tuple[CuratedFund, object]] = []
    unmatched: list[str] = []
    for entry in CURATED_FUNDS:
        hit = match_curated(rows, entry)
        if hit is None:
            unmatched.append(entry.match)
        else:
            matched.append((entry, hit))
    if unmatched:
        logger.warning(
            "Fund catalog: %d curated entries unmatched today: %s",
            len(unmatched), ",".join(unmatched),
        )

    synced = 0
    errors: list[str] = []
    for entry, hit in matched:
        try:
            async with SessionLocal() as session:
                fund = await fund_repo.get_or_create_fund(
                    session,
                    amfi_code=hit.code,
                    name=hit.name,
                    category=entry.category,
                    plan=hit.plan,
                    option=hit.option,
                )
                await fund_repo.upsert_navs(
                    session, fund.id, [(hit.date, hit.nav, "amfi")]
                )
                if backfill_history:
                    try:
                        history = await fetch_mfapi_history(hit.code, client=client)
                        capped = history[-MFAPI_BACKFILL_DAYS:]
                        await fund_repo.upsert_navs(
                            session, fund.id,
                            [(d, nav, "mfapi") for d, nav in capped],
                        )
                    except MarketDataError as exc:
                        # Fallback-only failure is not fatal: the AMFI NAV
                        # stands. Logged, never silent.
                        logger.warning(
                            "mfapi backfill failed for %s: %s", hit.code, exc
                        )
                await fund_repo.refresh_latest_nav(session, fund.id)
            synced += 1
        except Exception as exc:
            logger.error("Failed to ingest fund %s: %s", entry.match, exc)
            errors.append(entry.match)

    logger.info(
        "Fund ingestion done: %d synced, %d errors, %d unmatched",
        synced, len(errors), len(unmatched),
    )
    return {
        "fetched": synced,
        "rows": len(matched),
        "errors": len(errors),
        "unmatched": len(unmatched),
        "backfilled": backfill_history,
    }


# --- Retention: gated alpha-history prune (M2-T1, Plan 22 first cut) --------
#
# NOT part of the nightly _ingest_passes and never scheduled. Owner rule
# (2026-11): alpha-score pruning is NOT enabled. The function deletes nothing
# unless the caller passes the exact confirmation phrase below. There is no
# size gate on purpose: pg_database_size includes dead-tuple bloat, so any
# size threshold can be crossed without live data having grown, and a size
# gate fires unattended. Size is reported for the record only. Run manually
# via `python -m app.jobs prune-alpha --confirm DELETE-ALPHA-HISTORY`
# (recorded in job_runs like every pass), only after the owner approves.

_PRUNE_BATCH_SIZE = 5000  # short transactions; Neon connection friendly

# The exact text an operator must type. Deliberately long and specific so it
# cannot be supplied by accident or by a default argument.
PRUNE_CONFIRM_PHRASE = "DELETE-ALPHA-HISTORY"


async def prune_alpha_history_outside_top250(confirm: str | None = None) -> dict:
    """Cut alpha history to 1y outside the top-250 keep-set (Plan 22).

    Refuses (deletes NOTHING, reads nothing, reports fired=False) unless
    `confirm` equals PRUNE_CONFIRM_PHRASE. There is no automatic trigger.

    Keep-set: stocks with mcap_rank <= storage_cut_keep_top (250) keep full
    alpha history. Everyone else (rank > 250 or NULL — ranked_out rows stay
    active but unranked, and rows outside any cycle) is pruned to
    storage_cut_depth_days (366) before the cutoff date. Deletion is
    batched (short transactions), idempotent (a re-run deletes 0 rows), and
    never touches prices, statements, or any table but alpha_scores.
    """
    if confirm != PRUNE_CONFIRM_PHRASE:
        logger.info(
            "prune_alpha_history refused reason=confirmation_required deleted=0 "
            "(alpha pruning is not enabled; see jobs.py retention note)"
        )
        return {
            "fired": False,
            "reason": "confirmation_required",
            "deleted": 0,
        }

    # Size is recorded for the audit trail only; it never decides anything.
    async with SessionLocal() as session:
        size_bytes = int(
            await session.scalar(
                select(func.pg_database_size(func.current_database()))
            )
        )

    cutoff = date.today() - timedelta(days=settings.storage_cut_depth_days)
    # Prune target: every symbol NOT in the top-N keep-set. alpha_scores is
    # keyed by symbol, so the keep-set is resolved from the catalog first.
    prunable_symbols = select(Stock.symbol).where(
        or_(
            Stock.mcap_rank.is_(None),
            Stock.mcap_rank > settings.storage_cut_keep_top,
        )
    )

    total_deleted = 0
    while True:
        async with SessionLocal() as session:
            batch_ids = select(AlphaScore.id).where(
                AlphaScore.date < cutoff,
                AlphaScore.symbol.in_(prunable_symbols),
            ).limit(_PRUNE_BATCH_SIZE)
            result = await session.execute(
                delete(AlphaScore).where(AlphaScore.id.in_(batch_ids))
            )
            await session.commit()
            deleted = result.rowcount or 0
        total_deleted += deleted
        if deleted < _PRUNE_BATCH_SIZE:
            break

    logger.info(
        "prune_alpha_history fired=yes cutoff=%s deleted=%d keep_top=%d depth_days=%d",
        cutoff.isoformat(), total_deleted,
        settings.storage_cut_keep_top, settings.storage_cut_depth_days,
    )
    return {
        "fired": True,
        "db_mb": round(size_bytes / storage_svc.BYTES_PER_MB, 1),
        "cutoff": cutoff.isoformat(),
        "keep_top": settings.storage_cut_keep_top,
        "depth_days": settings.storage_cut_depth_days,
        "deleted": total_deleted,
    }


# --- Top-1000 universe ranking (M1-T2, Plan 7) -------------------------------

# Pacing for the mcap fetch phase (see _fetch_one_mcap and the rank loop for
# why). Module-level so tests can shrink them to keep the suite fast.
_MCAP_RETRY_DELAYS: tuple[float, ...] = (5.0, 15.0, 30.0)
_MCAP_RETRY_JITTER = 0.25
_MCAP_BATCH_SLEEP_S = 2.0

async def _fetch_one_mcap(
    provider: MarketDataProvider, bare_symbol: str
) -> tuple[str, float | None]:
    """Fetch one symbol's market cap for ranking (E6: fresh, never stored).

    Takes the CURRENT NSE bare symbol (the master's); provider calls use the
    ".NS" suffixed form. Raises MarketDataError upward so callers isolate
    per-symbol failures (D19); a provider-None stays None (E7 no_mcap).

    Pacing (5s/15s/30s + jitter, NOT the default 0.5s/1s): the Actions
    runner's shared IP is Yahoo-throttled hard at ~2,800 info calls (rank.yml
    run 34350500127: 2,051 of the fetches 429'd through all 3 fast retries,
    shrinking the ranked universe to 728). Slower, jittered retries give the
    rate limiter room to clear between attempts.
    """
    fundamentals = await _with_retry(
        lambda: provider.get_fundamentals(f"{bare_symbol}.NS"),
        what=f"market-cap fetch for {bare_symbol}",
        delays=_MCAP_RETRY_DELAYS,
        jitter=_MCAP_RETRY_JITTER,
    )
    return bare_symbol, fundamentals.market_cap


async def _fetch_last_bar_date(provider: MarketDataProvider, bare_symbol: str):
    """The provider's newest daily bar date for one symbol (None if no bars)."""
    bars = await _with_retry(
        lambda: provider.get_price_history(f"{bare_symbol}.NS", "1mo"),
        what=f"freshness check for {bare_symbol}",
        delays=_MCAP_RETRY_DELAYS,
        jitter=_MCAP_RETRY_JITTER,
    )
    return max((b.date for b in bars), default=None)


async def rank_universe(
    provider: MarketDataProvider | None = None,
    master_rows: list[NseMasterRow] | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """Rank the eligible NSE equity universe by market cap into 'top1000'.

    Plan 7 pipeline: NSE master -> eligibility rules E1-E12 (pure logic in
    app/services/ranking.py) -> fresh provider market caps -> rank + cutoff
    -> persist cycle, audit trail, stocks metadata and universe membership.

    Scope boundary: this pass is NEVER part of the nightly _ingest_passes or
    the in-process scheduler — it is a monthly job, runnable manually via
    `python -m app.jobs rank` (the monthly cron wiring lands in M1-T5).
    master_rows is injectable for zero-network tests; None means fetch the
    live master (fail-closed: a master outage fails the whole pass rather
    than ranking against nothing).

    Returns {"ranked", "excluded", "errors"}: errors > 0 marks the job_runs
    row 'partial' (per-symbol mcap failures are isolated, never fatal).
    """
    provider = provider or build_default_market_provider()
    started_clock = time.perf_counter()

    rows = master_rows if master_rows is not None else await fetch_master_with_retry()

    # Match the master to the catalog; create catalog rows for unseen
    # rankable symbols (IPO/new-listing path, E8), then re-match.
    async with SessionLocal() as session:
        catalog = await ranking_repo.load_catalog_facts(session)
        matches = ranking_svc.match_master_to_catalog(rows, catalog, SYMBOL_ALIASES)
        new_entries: list[tuple[str, str, str | None]] = []
        for row in rows:
            if row.symbol in matches:
                continue
            if not ranking_svc.rankable_series(row):
                continue
            if ranking_svc.curated_excluded(row) is not None:
                continue
            new_entries.append((row.symbol, row.name, row.isin))
        created = await ranking_repo.ensure_catalog_entries(session, new_entries)
        await session.commit()
    if created:
        logger.info("Ranking created %d new catalog rows", created)
        async with SessionLocal() as session:
            catalog = await ranking_repo.load_catalog_facts(session)
        matches = ranking_svc.match_master_to_catalog(rows, catalog, SYMBOL_ALIASES)

    async with SessionLocal() as session:
        price_facts, reference_dates = await ranking_repo.load_price_facts(session)

    candidates = ranking_svc.build_candidates(
        rows, catalog, matches, price_facts, symbol_aliases=SYMBOL_ALIASES
    )

    # Fresh market caps (E6) for candidates that can still rank. Per-symbol
    # isolation: a failed fetch becomes an excluded/no_mcap audit row with
    # the error in its detail, and counts toward the pass's 'errors'.
    fetch_list = [c for c in candidates if ranking_svc.needs_mcap(c)]
    mcaps: dict[str, tuple[float | None, str | None]] = {}
    errors: list[str] = []
    for i in range(0, len(fetch_list), batch_size):
        batch = fetch_list[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_mcap(provider, c.symbol) for c in batch),
            return_exceptions=True,
        )
        for c, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Market-cap fetch failed for %s: %s", c.symbol, res)
                errors.append(c.symbol)
                mcaps[c.symbol] = (None, f"{type(res).__name__}: {res}")
            else:
                mcaps[c.symbol] = (res[1], None)
        # Inter-batch pause: ~556 batches against one shared-runner IP; a
        # modest gap between batches lowers sustained request pressure on the
        # Yahoo rate limiter (rank.yml 429 storm, 2026-09-09).
        if i + batch_size < len(fetch_list):
            await asyncio.sleep(_MCAP_BATCH_SLEEP_S)
    candidates = [
        ranking_svc.with_mcap(c, *mcaps.get(c.symbol, (c.mcap, c.mcap_error)))
        for c in candidates
    ]

    # E9 guard: before calling a stock inactive on stale STORED bars, ask the
    # provider for its latest bar. Stocks outside the universe are not
    # ingested, so their stored bars age even while they trade (see
    # ranking_svc.needs_freshness_check). A failed check keeps the stored
    # facts (the old behaviour) and is logged, not counted as an error.
    recheck = [
        c for c in candidates
        if ranking_svc.needs_freshness_check(c, reference_dates)
    ]
    provider_last: dict[str, object] = {}
    for i in range(0, len(recheck), batch_size):
        batch = recheck[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_last_bar_date(provider, c.symbol) for c in batch),
            return_exceptions=True,
        )
        for c, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.warning("Freshness check failed for %s: %s", c.symbol, res)
            elif res is not None:
                provider_last[c.symbol] = res
        if i + batch_size < len(recheck):
            await asyncio.sleep(_MCAP_BATCH_SLEEP_S)
    if recheck:
        logger.info(
            "E9 freshness check: %d stale on stored bars, %d trading at the provider",
            len(recheck), len(provider_last),
        )
    candidates = [
        ranking_svc.with_provider_last_bar(c, provider_last.get(c.symbol))
        for c in candidates
    ]

    ctx = ranking_svc.RankContext(
        today=date.today(),
        reference_dates=reference_dates,
        ranked_size=RANKED_SIZE,
        symbol_aliases=SYMBOL_ALIASES,
    )
    decisions = ranking_svc.evaluate(candidates, ctx)

    cycle_date = date.today()
    mcap_asof = ranking_svc.cycle_reference_asof(reference_dates, cycle_date)
    ranked_count = sum(1 for d in decisions if d.outcome == ranking_svc.RANKED_IN)
    excluded_count = len(decisions) - ranked_count

    async with SessionLocal() as session:
        cycle = await ranking_repo.upsert_cycle(
            session, cycle_date, RANKED_UNIVERSE, mcap_asof
        )
        await ranking_repo.replace_cycle_audit(session, cycle.id, decisions)
        await ranking_repo.apply_stock_updates(session, decisions, cycle_date)
        universe = await ranking_repo.get_or_create_universe(session, RANKED_UNIVERSE)
        await ranking_repo.rebuild_universe_membership(
            session, universe.id, ranking_repo.ranked_in_ids(decisions)
        )
        await ranking_repo.finalize_cycle(
            session, cycle.id, round((time.perf_counter() - started_clock) * 1000)
        )
        await session.commit()
        summary = await ranking_repo.cycle_audit_summary(session, cycle.id)

    logger.info(
        "Ranking done: cycle_date=%s ranked=%d excluded=%d errors=%d outcomes=%s",
        cycle_date, ranked_count, excluded_count, len(errors), summary,
    )
    return {"ranked": ranked_count, "excluded": excluded_count, "errors": len(errors)}


def run_daily_ingestion() -> str:
    """Scheduled entrypoint: run all ingestion passes once.

    Runs asyncio.run here because APScheduler calls this synchronously in a
    background thread. A dedicated engine is created for the job (Phase 7 fix):
    the API process's module-global engine is bound to the uvicorn event loop,
    and reusing its asyncpg pool from this thread's fresh loop fails once the
    API has served traffic. Returns the recorded pass status ('success' |
    'partial' | 'failed') so the CLI can exit non-zero on a failed night.
    """
    return asyncio.run(_ingest_all_with_job_engine())


async def _ingest_all_with_job_engine() -> str:
    """Run the nightly passes on a job-scoped engine, then dispose of it.

    Pooled (work list item 22). The passes open a short session per symbol
    (thousands per night); with NullPool each one paid a fresh TCP + TLS +
    auth handshake to Neon. A small pool reuses connections instead, sized
    for BATCH_SIZE concurrent symbols plus the job_runs recorder. The same
    settings as the API's engine (app.db), which already pools against the
    same URL: pool_pre_ping replaces connections Neon closed during long
    provider-fetch gaps, and pool_recycle retires them before Neon's idle
    timeout. The engine is still created inside this run's event loop and
    disposed at the end, so the cross-loop problem above cannot return.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db import asyncpg_ready_url

    global SessionLocal
    engine = create_async_engine(
        asyncpg_ready_url(settings.database_url),
        pool_size=BATCH_SIZE + 2,
        max_overflow=BATCH_SIZE,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    original = SessionLocal
    SessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        return await _ingest_all()
    finally:
        SessionLocal = original
        await engine.dispose()


# --- Job-run recording (Phase 7) ---------------------------------------------

# Cap stored error text: enough for diagnosis, never an unbounded traceback
# dump (and provider errors deliberately exclude credentials already).
ERROR_SUMMARY_MAX = 500

# Result keys meaning "items processed" for the different pass shapes.
# "ranked" is the top-1000 ranking pass (M1-T2); "stored" is the live alpha
# snapshot pass (record_live_alpha_snapshots).
_PROCESSED_KEYS = ("fetched", "repaired", "warmed", "snapshots", "ranked", "stored")


async def _record_pass(name: str, run, *args, **kwargs) -> str:
    """Execute one ingestion pass inside a durable job_runs record.

    Guaranteed (PLANNING D85):
      - a pass that raises is recorded as 'failed' and does NOT stop the
        remaining passes (phase-level isolation on top of per-symbol D19);
      - per-item failures inside the pass mark the run 'partial';
      - status recording itself must never break ingestion: if the job_runs
        write fails (e.g. DB down), the pass still runs and the failure to
        record is logged as a warning.

    Returns the final status so aggregating passes can report accurately.
    """
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    logger.info("job_start job=%s", name)

    record: JobRun | None = None
    try:
        async with SessionLocal() as session:
            record = JobRun(job_name=name, status="running", started_at=started)
            session.add(record)
            await session.commit()
    except Exception as exc:
        record = None
        logger.warning(
            "job_status_unavailable job=%s stage=begin error=%s: %s",
            name, type(exc).__name__, exc,
        )

    async def _finish(status: str, processed, failed, summary: str | None) -> None:
        finished = datetime.now(timezone.utc)
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log = logger.error if status == "failed" else logger.info
        # The summary MUST appear in the log line: on a failed job it is the
        # operator's only immediate signal (the full text also lands in the
        # job_runs.error_summary column, but CI logs are read first).
        log(
            "%s job=%s status=%s duration_ms=%d processed=%s failed=%s summary=%s",
            "job_fail" if status == "failed" else "job_end",
            name, status, duration_ms, processed, failed, summary,
        )
        if record is None:
            return
        try:
            async with SessionLocal() as session:
                rec = await session.get(JobRun, record.id)
                if rec is None:
                    return
                rec.status = status
                rec.finished_at = finished
                rec.duration_ms = duration_ms
                rec.items_processed = processed
                rec.items_failed = failed
                rec.error_summary = summary[:ERROR_SUMMARY_MAX] if summary else None
                await session.commit()
        except Exception as exc:
            logger.warning(
                "job_status_unavailable job=%s stage=finish error=%s: %s",
                name, type(exc).__name__, exc,
            )

    try:
        result = await run(*args, **kwargs)
    except Exception as exc:
        summary = f"{type(exc).__name__}: {exc}"[:ERROR_SUMMARY_MAX]
        await _finish("failed", None, None, summary)
        return "failed"

    result = result or {}
    errors = int(result.get("errors", 0) or 0)
    processed = next((result[k] for k in _PROCESSED_KEYS if k in result), None)
    summary = None
    status = "success"
    if errors > 0:
        status = "partial"
        summary = f"{errors} item(s) failed"
    await _finish(status, processed, errors, summary)
    return status


# --- News retention (owner decision 2026-11-12: up to 20 articles per stock) -

NEWS_KEEP_PER_STOCK = 20


def news_ids_to_delete(
    rows: list[tuple[int, str, object]],
    symbol: str,
    name: str | None,
    generic: frozenset[str],
    keep: int = NEWS_KEEP_PER_STOCK,
) -> list[int]:
    """Article ids to delete for one stock: everything except its `keep`
    newest articles that pass the current relevance rule. rows are
    (id, title, published_at); undated articles sort oldest."""
    def sort_key(r):
        pub = r[2]
        return (pub is not None, pub or datetime.min.replace(tzinfo=timezone.utc), r[0])

    kept = 0
    delete: list[int] = []
    for art_id, title, _pub in sorted(rows, key=sort_key, reverse=True):
        if kept < keep and is_relevant_article(title, symbol, name, generic):
            kept += 1
        else:
            delete.append(art_id)
    return delete


async def prune_news(keep: int = NEWS_KEEP_PER_STOCK) -> dict:
    """Keep each stock's `keep` newest relevant articles; delete the rest
    (their sentiment rows first). Runs after ingest_news."""
    async with SessionLocal() as session:
        names = dict(
            (await session.execute(select(Stock.symbol, Stock.name))).all()
        )
        generic = generic_tokens_from_names(n for n in names.values() if n)
        symbols = (
            await session.execute(select(NewsArticle.symbol).distinct())
        ).scalars().all()

    deleted = 0
    for symbol in symbols:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(NewsArticle.id, NewsArticle.title, NewsArticle.published_at)
                    .where(NewsArticle.symbol == symbol)
                )
            ).all()
            ids = news_ids_to_delete(
                [tuple(r) for r in rows], symbol, names.get(symbol), generic, keep
            )
            if not ids:
                continue
            await session.execute(
                delete(NewsSentiment).where(NewsSentiment.article_id.in_(ids))
            )
            await session.execute(delete(NewsArticle).where(NewsArticle.id.in_(ids)))
            await session.commit()
            deleted += len(ids)
    logger.info("News retention: %d symbols, %d articles deleted (keep %d)",
                len(symbols), deleted, keep)
    return {"fetched": len(symbols), "deleted": deleted, "errors": 0}


async def _ingest_passes() -> dict:
    """All ingestion passes, each recorded and isolated (one row per pass).

    Returns child-pass failure/success counts so the top-level
    nightly_ingestion row never masks a failed pass as overall success.
    """
    every_pass = _env_flag("INGEST_ALL_PASSES")
    today = datetime.now(timezone.utc).date()
    financial_days = RESULTS_SEASON_DAYS if in_results_season(today) else WEEKLY_DAYS

    async def due(name: str, days: int) -> bool:
        if every_pass or await _pass_due(name, days):
            return True
        logger.info("%s not due tonight (runs every %d days)", name, days)
        return False

    slow = []
    for name, run in (
        ("ingest_financial_periods", ingest_financial_periods),
        ("ingest_balance_sheets", ingest_balance_sheets),
    ):
        if await due(name, financial_days):
            slow.append((name, run))
    if await due("ingest_company_profiles", WEEKLY_DAYS):
        slow.append(("ingest_company_profiles", ingest_company_profiles))

    full_alpha = await _alpha_full_backfill_due()
    alpha_pass = (
        (ALPHA_FULL_JOB, functools.partial(backfill_alpha_history, full=True))
        if full_alpha
        else ("backfill_alpha_history", functools.partial(backfill_alpha_history, full=False))
    )

    passes = (
        ("ingest_prices", ingest_universe),
        ("ingest_financials", ingest_financials),
        *slow,
        # Quarterly ownership pattern (checklist 6 step 3): a bounded slice
        # of due stocks per night; a quiet no-op without token or table.
        ("ingest_shareholding", ingest_shareholding),
        # Benchmark indexes (M1-T6): own tables, own measured contribution.
        ("ingest_benchmarks", ingest_benchmarks),
        # ETF catalog + prices (Plan 9 slice); is_etf stocks, never universes.
        ("ingest_etfs", ingest_etfs),
        # Curated fund catalog + AMFI daily NAV (Plan 8 slice).
        ("ingest_funds", ingest_funds),
        # Catch catalog stocks the universe passes dropped (renames/demergers).
        ("repair_catalog_gaps", repair_catalog_gaps),
        alpha_pass,
        # Today's live snapshot per symbol (Phase 8: GET /alpha is pure read,
        # so ingestion owns the write that keeps per-component history current).
        ("record_live_alpha_snapshots", record_live_alpha_snapshots),
        # One-year price strength, ranked across the list in one pass and
        # merged into the rows the pass above just wrote. Must follow it.
        ("record_strength_scores", record_strength_scores),
        # Plan 18: no nightly LLM pre-warm — explanations are on-demand with
        # the rule-based default; the pre-warm helper remains for manual use.
        ("ingest_news", ingest_news),
        # Owner decision 2026-11-12: up to 20 relevant articles per stock.
        ("prune_news", prune_news),
    )
    statuses = []
    for name, run in passes:
        statuses.append(await _record_pass(name, run))
    failed = statuses.count("failed")
    partial = statuses.count("partial")
    if failed == len(statuses):
        # Every pass failed: the night genuinely failed; report it as such
        # rather than as a meaningless "partial".
        raise RuntimeError(f"all {failed} ingestion passes failed")
    return {
        "fetched": statuses.count("success"),
        # Non-success child passes (failed or partial) make the wrapper
        # 'partial' via the recorder's errors>0 rule.
        "errors": failed + partial,
        "partial_passes": partial,
    }


async def _ingest_all() -> str:
    """Full nightly run.

    'failed' when every child pass failed or something outside the passes
    raised; 'partial' when any pass was partial/failed; else 'success'.

    Part F daily cycle, verified: market/fundamental ingestion (prices,
    financials, periods, profiles, benchmarks, repair, news) -> fundamental
    calculations (scores are pure reads over the snapshots) -> technical
    calculations (indicators over stored bars) -> sentiment (stored FinBERT
    aggregates) -> SignalDesk scores (backfill + live snapshots, pure writes
     of computed values) -> Altman Z-Score needs NO nightly pass (pure read
     over the stored snapshot via from_stored_snapshot; recomputes on every
     GET /stocks/{s}/altman) -> API serves latest state.
    """
    return await _record_pass("nightly_ingestion", _ingest_passes)


def start_scheduler():
    """Start the background scheduler that runs daily ingestion.

    Reliability settings (PLANNING D86): pinned to Asia/Kolkata so the 18:30
    IST after-close run is independent of the host's timezone; max_instances=1
    prevents overlapping nightly runs; coalesce=True collapses multiple missed
    firings into one; misfire_grace_time of 2 hours lets a run that was missed
    (e.g. the process restarted around 18:30) still execute shortly after
    instead of silently waiting for the next day.

    Production (Plan 21.2, D79): GitHub Actions is the ONLY scheduler. The
    scheduler object still STARTS here so /status/full keeps reporting an
    honest scheduler="running", but NO job is registered — otherwise the
    Render free instance (0.1 CPU / 512 MB) would run the 1.5-2 h nightly
    ingestion alongside Actions against the same database. The guard is the
    is_production() check: APP_ENV=production registers zero jobs; any other
    APP_ENV keeps the 18:30 IST registration for local use.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    if not settings.is_production():
        # Run once per day at 18:30 IST (after market close).
        scheduler.add_job(
            run_daily_ingestion,
            "cron",
            id="nightly_ingestion",
            name="nightly_ingestion",
            hour=18,
            minute=30,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=2 * 60 * 60,
        )
    scheduler.start()
    if settings.is_production():
        logger.info(
            "Background scheduler started with NO jobs "
            "(Actions is the scheduler in production; Plan 21.2/D79)."
        )
    else:
        logger.info("Background scheduler started (daily ingestion 18:30 Asia/Kolkata).")
    return scheduler


if __name__ == "__main__":
    import sys

    # CLI runs don't go through app.main, so configure root logging here:
    # job_start/job_end lines must be visible to an operator on the terminal.
    from app.logging_utils import configure_logging

    configure_logging()

    command = sys.argv[1] if len(sys.argv) > 1 else "backfill"
    if command == "backfill":
        # Explicit recompute of every symbol's alpha history under the
        # current formula (replaces stored technical-only snapshots per
        # symbol; live snapshots carrying a fundamental score are kept).
        # Recorded like the scheduled passes so /debug/jobs reflects it.
        status = asyncio.run(
            _record_pass(ALPHA_FULL_JOB, backfill_alpha_history, full=True)
        )
    elif command == "ingest":
        status = run_daily_ingestion()
    elif command == "rank":
        # Top-1000 universe ranking (M1-T2): fetch the NSE master, apply the
        # E1-E12 eligibility rules, rank by fresh market caps, write the
        # audit trail and the top1000 universe. Monthly cadence is wired in
        # M1-T5; manual here.
        status = asyncio.run(_record_pass("rank_universe", rank_universe))
    elif command == "etfs":
        # ETF catalog + price history (Plan 9 slice); recorded like a pass.
        status = asyncio.run(_record_pass("ingest_etfs", ingest_etfs))
    elif command == "funds":
        # Curated fund catalog + AMFI daily NAV, plus the mfapi history
        # backfill (documented fallback) on explicit runs.
        status = asyncio.run(_record_pass("ingest_funds", ingest_funds, True))
    elif command == "balance-sheets":
        # Annual balance sheets for the active universe (Altman Z-Score data).
        status = asyncio.run(_record_pass("ingest_balance_sheets", ingest_balance_sheets))
    elif command == "prune-alpha":
        # Alpha-history retention cut (M2-T1, Plan 22). NOT scheduled and NOT
        # part of the nightly passes. Refuses unless run as
        #   python -m app.jobs prune-alpha --confirm DELETE-ALPHA-HISTORY
        # and only with the owner's approval (alpha pruning is not enabled).
        confirm = None
        if "--confirm" in sys.argv:
            idx = sys.argv.index("--confirm")
            confirm = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        status = asyncio.run(
            _record_pass(
                "prune_alpha_history", prune_alpha_history_outside_top250, confirm
            )
        )
    else:
        raise SystemExit(
            f"Unknown command: {command} "
            "(use 'backfill', 'ingest', 'rank', 'etfs', 'funds', "
            "'balance-sheets' or 'prune-alpha')"
        )
    # Exit non-zero ONLY on a hard job failure so CI/workflow conclusions
    # reflect reality ('partial' stays exit 0: per-symbol provider blips are
    # recorded in job_runs as partial and must not paint the whole night red).
    raise SystemExit(1 if status == "failed" else 0)