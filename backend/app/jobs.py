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
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import (
    AlphaScore,
    DailyPrice,
    FinancialPeriod,
    Financials,
    NewsArticle,
    NewsSentiment,
    Stock,
    Universe,
    stock_universe,
)
from app.providers.base import Fundamentals, MarketDataProvider
from app.providers.factory import build_default_market_provider
from app.providers.news_base import Article, NewsProvider
from app.providers.rss_provider import GoogleNewsRSSProvider, NewsProviderError
from app.providers.sentiment import FinBERTScorer, Sentiment
from app.providers.yfinance_provider import MarketDataError, YFinanceProvider

logger = logging.getLogger(__name__)

UNIVERSE_NAME = "nifty250"  # the widest active catalog (50 -> 100 -> 250 ladder)
PERIOD = "2y"  # how much price history to fetch on each run
BATCH_SIZE = 5  # concurrent symbols per batch (respect provider rate limits)

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

        stmt = pg_insert(Financials).values(
            _financials_row(stock_id, fundamentals)
        )
        # One row per stock: overwrite the snapshot on conflict. Also refresh
        # updated_at so staleness signals stay truthful across re-ingests.
        set_ = {
            k: getattr(stmt.excluded, k)
            for k in _financials_row(stock_id, fundamentals)
            if k != "stock_id"
        }
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
    technical score; the per-component history fills in only as genuine live
    snapshots accumulate from /alpha. Existing snapshots for the symbol are
    replaced so the whole series is recomputed under the current formula;
    live /alpha requests rebuild today's snapshot on the next page view.
    """
    from app.repositories import alpha as alpha_repo
    from app.repositories import financials as fin_repo
    from app.repositories import news as news_repo
    from app.services import indicators, scores as score_svc
    from app.services.alpha import _mean_of, _renormalized

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

        # Latest known fundamental score (slow-moving: quarterly snapshot).
        fundamental: int | None = None
        fundamentals = await fin_repo.get_financials(session, stock)
        if fundamentals is not None:
            profit = score_svc.profitability_score(fundamentals)
            solvency = score_svc.solvency_score(fundamentals)
            fundamental = _mean_of(profit.score, solvency.score)

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

    # Replace the symbol's snapshots: the series is recomputed under the
    # current formula, so stale rows must not survive the run. Only reached
    # when there is something to insert.
    async with SessionLocal() as session:
        await session.execute(delete(AlphaScore).where(AlphaScore.symbol == symbol))
        await session.commit()
        return await alpha_repo.upsert_snapshots_bulk(session, rows)


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


def run_daily_ingestion() -> None:
    """Scheduled entrypoint: run price + financials ingestion once.

    Runs asyncio.run here because APScheduler calls this synchronously.
    """
    asyncio.run(_ingest_all())


async def _ingest_all() -> None:
    """Run all ingestion passes (prices, financials, history, alpha, news)."""
    await ingest_universe()
    await ingest_financials()
    await ingest_financial_periods()
    await backfill_alpha_history()
    await ingest_news()


def start_scheduler() -> None:
    """Start a background scheduler that runs daily ingestion."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    # Run once per day at 18:30 (after market close, IST ~18:30).
    scheduler.add_job(run_daily_ingestion, "cron", hour=18, minute=30)
    scheduler.start()
    logger.info("Background scheduler started (daily ingestion at 18:30).")
    return scheduler


if __name__ == "__main__":
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else "backfill"
    if command == "backfill":
        # Explicit recompute of every symbol's alpha history under the
        # current formula (replaces stored snapshots per symbol).
        asyncio.run(backfill_alpha_history())
    elif command == "ingest":
        run_daily_ingestion()
    else:
        raise SystemExit(f"Unknown command: {command} (use 'backfill' or 'ingest')")