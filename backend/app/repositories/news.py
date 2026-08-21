# News repository — read queries for the /news and /sentiment endpoints.

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import NewsArticle, NewsSentiment


async def get_articles(
    session: AsyncSession, symbol: str, limit: int
) -> list[NewsArticle]:
    """Return a symbol's articles, newest first, eager-loading sentiment."""
    result = await session.execute(
        select(NewsArticle)
        .options(selectinload(NewsArticle.sentiment))
        .where(NewsArticle.symbol == symbol)
        .order_by(NewsArticle.published_at.desc().nulls_last(), NewsArticle.id.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def get_sentiment_summary(
    session: AsyncSession, symbol: str, window: int | None = None
) -> dict | None:
    """Aggregate sentiment for a symbol over a recent window.

    Returns {score, label, count} or None if no scored articles exist.
    score is the mean confidence weighted by label sign: positive=+1,
    negative=-1, neutral=0, mapped to a -1..+1 range.
    """
    q = (
        select(
            func.count(NewsSentiment.id).label("count"),
            func.sum(
                case(
                    (NewsSentiment.label == "positive", NewsSentiment.score),
                    (NewsSentiment.label == "negative", -NewsSentiment.score),
                    else_=0,
                )
            ).label("net"),
        )
        .join(NewsArticle, NewsArticle.id == NewsSentiment.article_id)
        .where(NewsArticle.symbol == symbol)
    )
    row = (await session.execute(q)).one()
    count = row.count
    if not count:
        return None

    net = float(row.net or 0.0)
    score = round(net / count, 4)  # -1..+1

    if score > 0.1:
        label = "positive"
    elif score < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return {"score": score, "label": label, "count": count}