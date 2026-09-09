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
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone
from typing import TypeVar

from sqlalchemy import delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.config import settings
from app.data.funds import CURATED_FUNDS, MFAPI_BACKFILL_DAYS
from app.data.ranking_exclusions import ETF_SYMBOLS
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
from app.providers.base import Fundamentals, MarketDataProvider
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
from app.providers.sentiment import FinBERTScorer, Sentiment
from app.providers.upstox_provider import SYMBOL_ALIASES
from app.providers.yfinance_provider import MarketDataError, YFinanceProvider
from app.repositories import balance_sheets as bs_repo
from app.repositories import benchmarks as benchmark_repo
from app.repositories import company_profiles as profile_repo
from app.repositories import funds as fund_repo
from app.repositories import ranking as ranking_repo
from app.services import ranking as ranking_svc

logger = logging.getLogger(__name__)

UNIVERSE_NAME = "top1000"  # M1-T3 cutover: nightly ingestion reads the ranked
# top-1000 universe (was "nifty250"). Ranked-out / excluded catalog stocks
# are intentionally outside this path: they keep every stored row, and the
# repair_catalog_gaps pass still refreshes them when they have gaps.
PERIOD = "2y"  # how much price history to fetch on each run
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
) -> T:
    """Retry a provider call with exponential backoff on MarketDataError.

    Only MarketDataError (transient provider/network failures) is retried;
    other exceptions propagate immediately. After the final attempt the last
    error is re-raised so callers can isolate it per symbol (D19).
    """
    for attempt in range(retries + 1):
        try:
            return await fetch()
        except MarketDataError as exc:
            if attempt >= retries:
                raise
            delay = base_delay * (2**attempt)
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


async def _fetch_one_symbol(
    provider: MarketDataProvider, symbol: str
) -> tuple[str, int]:
    """Fetch and upsert one symbol's history. Returns (symbol, bars_inserted).

    Raises MarketDataError upward so callers can isolate failures per symbol.
    """
    bars = await _with_retry(
        lambda: provider.get_price_history(symbol, PERIOD),
        what=f"price fetch for {symbol}",
    )
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
        # On conflict with (stock_id, date), overwrite the existing bar.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_prices_stock_date",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        await session.execute(stmt)
        await session.commit()
        return symbol, len(bars)


async def ingest_universe(
    provider: MarketDataProvider | None = None, batch_size: int = BATCH_SIZE
) -> dict:
    """Fetch + upsert price history for every symbol in the active universe.

    Processes symbols in bounded batches (asyncio.gather) for rate-limit safety.
    A failure in one symbol is logged and isolated; the run continues.
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

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_fetch_one_symbol(provider, s) for s in batch),
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

    logger.info(
        "Ingestion done: %d symbols, %d bars, %d errors, %d skipped",
        len(symbols) - len(errors),
        total_bars,
        len(errors),
        skipped,
    )
    return {
        "fetched": len(symbols) - len(errors),
        "bars": total_bars,
        "errors": len(errors),
        "skipped": skipped,
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
        stmt = stmt.on_conflict_do_update(
            constraint="uq_financial_periods_stock_period",
            set_={
                "revenue": stmt.excluded.revenue,
                "net_income": stmt.excluded.net_income,
                "operating_margin": stmt.excluded.operating_margin,
                "net_margin": stmt.excluded.net_margin,
                "eps": stmt.excluded.eps,
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
    """
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


async def _backfill_one_alpha(symbol: str) -> int:
    """Retroactively compute alpha snapshots for every stored trading day.

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
    Existing snapshots for the symbol are replaced so the whole series is
    recomputed under the current formula.
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
        composite, _ = _renormalized(fundamental, scored["score"], sentiment)
        if composite is None:
            continue
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
                "components_json": scored.get("components") or {},
            }
        )

    if not rows:
        return 0

    # Replace the symbol's TECHNICAL-ONLY snapshots: the series is recomputed
    # under the current formula, so stale rows must not survive the run. Rows
    # that carry a genuine live fundamental score (written by /alpha page
    # views) are PRESERVED — wiping them every night would make per-component
    # history impossible. Only reached when there is something to insert.
    async with SessionLocal() as session:
        await session.execute(
            delete(AlphaScore).where(
                AlphaScore.symbol == symbol, AlphaScore.fundamental.is_(None)
            )
        )
        await session.commit()
        return await alpha_repo.upsert_snapshots_bulk(session, rows)


async def record_live_alpha_snapshot(symbol: str) -> bool:
    """Persist today's computed alpha snapshot for one symbol (Phase 8).

    Ownership of snapshot writes moved here from GET /alpha (which is now
    pure read). Called by the ingestion pathway — currently the nightly
    backfill sweep covers history; this helper covers the "today" row so a
    day's live view still accumulates per-component history without any
    request-time write. Returns True when a snapshot was stored.
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
        await alpha_repo.upsert_snapshot(
            session,
            symbol=stock.symbol,
            snapshot_date=date.today(),
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


async def backfill_alpha_history(batch_size: int = BATCH_SIZE) -> dict:
    """Retroactively backfill alpha snapshots for the whole active universe.

    Idempotent: existing technical-only rows are recomputed; full live
    snapshots (with a fundamental score) are preserved. Failures are
    isolated per symbol (D19).
    """
    async with SessionLocal() as session:
        symbols = await _get_universe_symbols(session)

    total = 0
    errors: list[str] = []
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        results = await asyncio.gather(
            *(_backfill_one_alpha(s) for s in batch), return_exceptions=True
        )
        for symbol, res in zip(batch, results):
            if isinstance(res, Exception):
                logger.error("Alpha backfill failed for %s: %s", symbol, res)
                errors.append(symbol)
            else:
                total += res

    logger.info(
        "Alpha history backfill done: %d snapshots, %d errors", total, len(errors)
    )
    return {"snapshots": total, "errors": len(errors)}


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
            await session.execute(select(Stock).where(price_gap | financials_gap | profile_gap))
        ).scalars().all()

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
    "ICICINIFTY": "ICICI Prudential Nifty 50 ETF",
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
    if created:
        await session.flush()
    return created


async def ingest_etfs(
    provider: MarketDataProvider | None = None, batch_size: int = BATCH_SIZE
) -> dict:
    """Ensure the curated ETF catalog rows exist and fetch their price history.

    ETFs reuse the EQUITY price pipeline (daily_prices via stocks rows flagged
    is_etf) but never enter universes, the screener or the /stocks list —
    they surface only through GET /etfs. Per-symbol isolation (D19).
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
            *(_fetch_one_symbol(provider, s) for s in batch),
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


# --- Top-1000 universe ranking (M1-T2, Plan 7) -------------------------------

async def _fetch_one_mcap(
    provider: MarketDataProvider, bare_symbol: str
) -> tuple[str, float | None]:
    """Fetch one symbol's market cap for ranking (E6: fresh, never stored).

    Takes the CURRENT NSE bare symbol (the master's); provider calls use the
    ".NS" suffixed form. Raises MarketDataError upward so callers isolate
    per-symbol failures (D19); a provider-None stays None (E7 no_mcap).
    """
    fundamentals = await _with_retry(
        lambda: provider.get_fundamentals(f"{bare_symbol}.NS"),
        what=f"market-cap fetch for {bare_symbol}",
    )
    return bare_symbol, fundamentals.market_cap


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
    candidates = [
        ranking_svc.with_mcap(c, *mcaps.get(c.symbol, (c.mcap, c.mcap_error)))
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


def run_daily_ingestion() -> None:
    """Scheduled entrypoint: run all ingestion passes once.

    Runs asyncio.run here because APScheduler calls this synchronously in a
    background thread. A dedicated engine is created for the job (Phase 7 fix):
    the API process's module-global engine is bound to the uvicorn event loop,
    and reusing its asyncpg pool from this thread's fresh loop fails once the
    API has served traffic.
    """
    asyncio.run(_ingest_all_with_job_engine())


async def _ingest_all_with_job_engine() -> None:
    """Run the nightly passes on a job-scoped engine, then dispose of it."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.db import asyncpg_ready_url

    global SessionLocal
    engine = create_async_engine(
        asyncpg_ready_url(settings.database_url), poolclass=NullPool
    )
    original = SessionLocal
    SessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        await _ingest_all()
    finally:
        SessionLocal = original
        await engine.dispose()


# --- Job-run recording (Phase 7) ---------------------------------------------

# Cap stored error text: enough for diagnosis, never an unbounded traceback
# dump (and provider errors deliberately exclude credentials already).
ERROR_SUMMARY_MAX = 500

# Result keys meaning "items processed" for the different pass shapes.
# "ranked" is the top-1000 ranking pass (M1-T2).
_PROCESSED_KEYS = ("fetched", "repaired", "warmed", "snapshots", "ranked")


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
        log(
            "%s job=%s status=%s duration_ms=%d processed=%s failed=%s",
            "job_fail" if status == "failed" else "job_end",
            name, status, duration_ms, processed, failed,
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


async def _ingest_passes() -> dict:
    """All ingestion passes, each recorded and isolated (one row per pass).

    Returns child-pass failure/success counts so the top-level
    nightly_ingestion row never masks a failed pass as overall success.
    """
    passes = (
        ("ingest_prices", ingest_universe),
        ("ingest_financials", ingest_financials),
        ("ingest_financial_periods", ingest_financial_periods),
        ("ingest_balance_sheets", ingest_balance_sheets),
        ("ingest_company_profiles", ingest_company_profiles),
        # Benchmark indexes (M1-T6): own tables, own measured contribution.
        ("ingest_benchmarks", ingest_benchmarks),
        # ETF catalog + prices (Plan 9 slice); is_etf stocks, never universes.
        ("ingest_etfs", ingest_etfs),
        # Curated fund catalog + AMFI daily NAV (Plan 8 slice).
        ("ingest_funds", ingest_funds),
        # Catch catalog stocks the universe passes dropped (renames/demergers).
        ("repair_catalog_gaps", repair_catalog_gaps),
        ("backfill_alpha_history", backfill_alpha_history),
        # Today's live snapshot per symbol (Phase 8: GET /alpha is pure read,
        # so ingestion owns the write that keeps per-component history current).
        ("record_live_alpha_snapshots", record_live_alpha_snapshots),
        # Plan 18: no nightly LLM pre-warm — explanations are on-demand with
        # the rule-based default; the pre-warm helper remains for manual use.
        ("ingest_news", ingest_news),
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


async def _ingest_all() -> None:
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
    await _record_pass("nightly_ingestion", _ingest_passes)


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
        asyncio.run(_record_pass("backfill_alpha_history", backfill_alpha_history))
    elif command == "ingest":
        run_daily_ingestion()
    elif command == "rank":
        # Top-1000 universe ranking (M1-T2): fetch the NSE master, apply the
        # E1-E12 eligibility rules, rank by fresh market caps, write the
        # audit trail and the top1000 universe. Monthly cadence is wired in
        # M1-T5; manual here.
        asyncio.run(_record_pass("rank_universe", rank_universe))
    elif command == "etfs":
        # ETF catalog + price history (Plan 9 slice); recorded like a pass.
        asyncio.run(_record_pass("ingest_etfs", ingest_etfs))
    elif command == "funds":
        # Curated fund catalog + AMFI daily NAV, plus the mfapi history
        # backfill (documented fallback) on explicit runs.
        asyncio.run(_record_pass("ingest_funds", ingest_funds, True))
    elif command == "balance-sheets":
        # Annual balance sheets for the active universe (Altman Z-Score data).
        asyncio.run(_record_pass("ingest_balance_sheets", ingest_balance_sheets))
    else:
        raise SystemExit(
            f"Unknown command: {command} "
            "(use 'backfill', 'ingest', 'rank', 'etfs', 'funds' or 'balance-sheets')"
        )