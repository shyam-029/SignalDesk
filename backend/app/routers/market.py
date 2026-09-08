# Market dashboard endpoints — index cards + market-wide news (Plan 16 slice).
#
# GET /benchmarks   stored index cards: latest close, day change, 90d sparkline
# GET /market/news  latest articles across the ingested universe (newest first)
#
# Both read ONLY stored rows (benchmarks/benchmark_prices, news_articles) —
# no provider calls on request paths.

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import BenchmarkPrice, NewsArticle
from app.repositories.benchmarks import list_benchmarks

router = APIRouter(tags=["market"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SPARKLINE_POINTS = 90


class BenchmarkCard(BaseModel):
    symbol: str
    name: str | None
    latest_close: float | None
    change_pct: float | None
    as_of: str | None
    # Oldest-first closes for the dashboard sparkline (up to 90 points).
    sparkline: list[float]


class BenchmarkListResponse(BaseModel):
    items: list[BenchmarkCard]


class MarketNewsItem(BaseModel):
    id: int
    symbol: str
    title: str
    source: str
    url: str
    published_at: str | None
    sentiment: str | None


class MarketNewsResponse(BaseModel):
    items: list[MarketNewsItem]


@router.get("/benchmarks", response_model=BenchmarkListResponse)
async def list_benchmark_cards(session: SessionDep) -> BenchmarkListResponse:
    """Stored index cards for the markets dashboard (close, day change, spark)."""
    benchmarks = await list_benchmarks(session)
    cards: list[BenchmarkCard] = []
    for b in benchmarks:
        rows = (
            await session.execute(
                select(BenchmarkPrice)
                .where(BenchmarkPrice.benchmark_id == b.id)
                .order_by(BenchmarkPrice.date.desc())
                .limit(SPARKLINE_POINTS)
            )
        ).scalars().all()
        rows = sorted(rows, key=lambda r: r.date)
        latest = rows[-1] if rows else None
        prev = rows[-2] if len(rows) > 1 else None
        change_pct = None
        if latest is not None and prev is not None and prev.close:
            change_pct = round(
                (float(latest.close) - float(prev.close)) / float(prev.close) * 100, 2
            )
        cards.append(
            BenchmarkCard(
                symbol=b.symbol,
                name=b.name,
                latest_close=float(latest.close) if latest else None,
                change_pct=change_pct,
                as_of=latest.date.isoformat() if latest else None,
                sparkline=[float(r.close) for r in rows],
            )
        )
    return BenchmarkListResponse(items=cards)


@router.get("/market/news", response_model=MarketNewsResponse)
async def market_news(
    session: SessionDep,
    limit: int = Query(20, ge=1, le=50),
) -> MarketNewsResponse:
    """Most recent articles across the ingested universe, newest first."""
    rows = (
        await session.execute(
            select(NewsArticle)
            .options(selectinload(NewsArticle.sentiment))
            .order_by(NewsArticle.published_at.desc().nulls_last(), NewsArticle.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return MarketNewsResponse(
        items=[
            MarketNewsItem(
                id=a.id,
                symbol=a.symbol,
                title=a.title,
                source=a.source,
                url=a.url,
                published_at=a.published_at.isoformat() if a.published_at else None,
                sentiment=a.sentiment.label if a.sentiment else None,
            )
            for a in rows
        ]
    )
