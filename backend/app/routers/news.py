# News + sentiment endpoints for a stock.

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.common import resolve_stock
from app.repositories import news as news_repo

router = APIRouter(prefix="/stocks", tags=["news"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class NewsArticleResponse(BaseModel):
    id: int
    source: str
    title: str
    url: str
    published_at: str | None
    sentiment: str | None = None  # label if scored, else None


class NewsListResponse(BaseModel):
    items: list[NewsArticleResponse]


class SentimentResponse(BaseModel):
    symbol: str
    score: float
    label: str
    count: int


@router.get("/{symbol}/news", response_model=NewsListResponse)
async def get_news(
    symbol: str,
    session: SessionDep,
    limit: int = Query(20, ge=1, le=50),
) -> NewsListResponse:
    """Return recent news articles for a stock, newest first."""
    stock = await resolve_stock(session, symbol)
    articles = await news_repo.get_articles(session, stock.symbol, limit)
    return NewsListResponse(
        items=[
            NewsArticleResponse(
                id=a.id,
                source=a.source,
                title=a.title,
                url=a.url,
                published_at=a.published_at.isoformat() if a.published_at else None,
                sentiment=a.sentiment.label if a.sentiment else None,
            )
            for a in articles
        ]
    )


@router.get("/{symbol}/sentiment", response_model=SentimentResponse)
async def get_sentiment(symbol: str, session: SessionDep) -> SentimentResponse:
    """Return aggregate FinBERT sentiment for a stock's recent news."""
    stock = await resolve_stock(session, symbol)
    summary = await news_repo.get_sentiment_summary(session, stock.symbol)
    if summary is None:
        return SentimentResponse(symbol=stock.symbol, score=0.0, label="neutral", count=0)
    return SentimentResponse(
        symbol=stock.symbol,
        score=summary["score"],
        label=summary["label"],
        count=summary["count"],
    )