# News repository — read queries for the /news and /sentiment endpoints.

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import NewsArticle, NewsSentiment, Stock
from app.services.news_relevance import generic_tokens_from_names, is_relevant_article

# Read-time relevance (2026-11-11): articles stored under the old, looser
# rule stay in the table (no deletion) but are filtered by the current rule
# wherever they are shown or aggregated. The catalog's generic name words
# are cached per process and refreshed hourly.
_GENERIC_TTL_S = 3600
_generic_cache: tuple[float, frozenset[str]] | None = None


def reset_cache() -> None:
    """Test hook."""
    global _generic_cache
    _generic_cache = None


async def _generic_tokens(session: AsyncSession) -> frozenset[str]:
    global _generic_cache
    now = time.monotonic()
    if _generic_cache and now - _generic_cache[0] < _GENERIC_TTL_S:
        return _generic_cache[1]
    names = (await session.execute(select(Stock.name).where(Stock.active.is_(True)))).scalars()
    tokens = generic_tokens_from_names(n for n in names if n)
    _generic_cache = (now, tokens)
    return tokens


async def _relevance_check(session: AsyncSession, symbol: str):
    """A title -> bool filter for this symbol under the current rule."""
    name = await session.scalar(select(Stock.name).where(Stock.symbol == symbol))
    generic = await _generic_tokens(session)
    return lambda title: is_relevant_article(title, symbol, name, generic)


async def get_articles(
    session: AsyncSession,
    symbol: str,
    limit: int,
    fresh_days: int | None = None,
) -> list[NewsArticle]:
    """Return a symbol's articles, newest first, eager-loading sentiment.

    fresh_days applies the display freshness window (approximately 30 days
    per the product plan): dated articles older than the window are hidden.
    Undated articles cannot be proven stale and are kept. Pass None to
    disable the window entirely.
    """
    q = (
        select(NewsArticle)
        .options(selectinload(NewsArticle.sentiment))
        .where(NewsArticle.symbol == symbol)
    )
    if fresh_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=fresh_days)
        q = q.where(
            (NewsArticle.published_at.is_(None)) | (NewsArticle.published_at >= cutoff)
        )
    # Over-fetch, then drop articles the current relevance rule rejects.
    q = q.order_by(
        NewsArticle.published_at.desc().nulls_last(), NewsArticle.id.desc()
    ).limit(limit * 4)
    relevant = await _relevance_check(session, symbol)
    result = await session.execute(q)
    return [a for a in result.scalars() if relevant(a.title)][:limit]


async def get_sentiment_summary(
    session: AsyncSession, symbol: str, window: int | None = None
) -> dict | None:
    """Aggregate sentiment for a symbol over a recent window.

    Returns {score, label, count} or None if no scored articles exist.
    score is the mean confidence weighted by label sign: positive=+1,
    negative=-1, neutral=0, mapped to a -1..+1 range.
    """
    rows = (
        await session.execute(
            select(NewsArticle.title, NewsSentiment.label, NewsSentiment.score)
            .select_from(NewsSentiment)
            .join(NewsArticle, NewsArticle.id == NewsSentiment.article_id)
            .where(NewsArticle.symbol == symbol)
        )
    ).all()
    relevant = await _relevance_check(session, symbol)
    signed = {"positive": 1.0, "negative": -1.0}
    kept = [r for r in rows if relevant(r.title)]
    count = len(kept)
    if not count:
        return None
    net = sum(signed.get(r.label, 0.0) * float(r.score or 0.0) for r in kept)

    score = round(net / count, 4)  # -1..+1

    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return {"score": score, "label": label, "count": count}