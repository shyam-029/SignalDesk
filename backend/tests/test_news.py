# Phase 3 tests â€” news + sentiment. All network-free:
#  - FakeNewsProvider (no RSS) + FakeScorer (no FinBERT) are used everywhere.
#  - DB writes go to signaldesk_test via session_factory / monkeypatched SessionLocal.

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

import app.jobs as jobs_module
from app.jobs import ingest_news
from app.models import NewsArticle, NewsSentiment, Stock, Universe, stock_universe
from app.providers.news_base import Article, NewsProvider
from app.providers.sentiment import Sentiment
from app.providers.yfinance_provider import MarketDataError


class FakeNewsProvider(NewsProvider):
    """Deterministic provider: returns fixed articles; can be told to fail."""

    def __init__(self, fail_symbol: str | None = None):
        self.fail_symbol = fail_symbol
        self.company_names: dict[str, str | None] = {}
        self._titles = [
            "Company posts record profits and raises guidance",
            "Analysts downgrade the stock after weak quarter",
            "Board announces share buyback",
        ]

    async def fetch_articles(
        self, symbol: str, limit: int = 20, company_name: str | None = None
    ) -> list[Article]:
        self.company_names[symbol] = company_name
        if symbol == self.fail_symbol:
            raise MarketDataError(f"simulated news failure for {symbol}")
        return [
            Article(
                symbol=symbol,
                source="Test",
                title=t,
                url=f"https://example.com/{symbol}/{i}",
                published_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            )
            for i, t in enumerate(self._titles[:limit])
        ]


class FakeScorer:
    """Deterministic scorer mapping known titles to fixed sentiments."""

    def __init__(self):
        self.calls = 0

    async def score_text_async(self, text: str) -> Sentiment:
        self.calls += 1
        if "profits" in text or "buyback" in text:
            return Sentiment(label="positive", score=0.95)
        return Sentiment(label="negative", score=0.90)


async def _seed_stock_and_universe(session_factory, symbol="RELIANCE.NS") -> None:
    async with session_factory() as session:
        s = Stock(symbol=symbol, name="Reliance", sector="E", industry="O")
        session.add(s)
        await session.flush()
        universe = await session.scalar(
            select(Universe).where(Universe.name == "nifty250")
        )
        if universe is None:
            universe = Universe(name="nifty250")
            session.add(universe)
            await session.flush()
        await session.execute(
            stock_universe.insert().values(universe_id=universe.id, stock_id=s.id)
        )
        await session.commit()


# --- Ingestion ----------------------------------------------------------------


async def test_ingest_news_inserts_and_scores(session_factory, monkeypatch):
    await _seed_stock_and_universe(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    result = await ingest_news(FakeNewsProvider(), FakeScorer(), batch_size=10)
    assert result["inserted"] == 3
    assert result["scored"] == 3
    assert result["errors"] == 0

    async with session_factory() as session:
        articles = (await session.execute(select(NewsArticle))).scalars().all()
        sentiments = (await session.execute(select(NewsSentiment))).scalars().all()
        assert len(articles) == 3
        assert len(sentiments) == 3
        labels = {s.label for s in sentiments}
        assert labels == {"positive", "negative"}


async def test_ingest_news_idempotent(session_factory, monkeypatch):
    """Re-running must not duplicate articles or re-score them."""
    await _seed_stock_and_universe(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    scorer = FakeScorer()

    r1 = await ingest_news(FakeNewsProvider(), scorer, batch_size=10)
    r2 = await ingest_news(FakeNewsProvider(), scorer, batch_size=10)

    assert r1["inserted"] == 3
    assert r2["inserted"] == 0  # all URLs already present
    assert r2["scored"] == 0    # all already scored
    assert scorer.calls == 3    # only the first run scored

    async with session_factory() as session:
        assert (await session.scalar(select(NewsArticle.id).limit(1))) is not None
        assert len((await session.execute(select(NewsArticle))).scalars().all()) == 3
        assert len((await session.execute(select(NewsSentiment))).scalars().all()) == 3


async def test_ingest_news_isolates_failures(session_factory, monkeypatch):
    """A failing symbol must not abort the run (D19)."""
    await _seed_stock_and_universe(session_factory, "RELIANCE.NS")
    await _seed_stock_and_universe(session_factory, "TCS.NS")
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    provider = FakeNewsProvider(fail_symbol="RELIANCE.NS")
    result = await ingest_news(provider, FakeScorer(), batch_size=10)
    assert result["errors"] == 1
    assert result["inserted"] == 3  # TCS still ingested


# --- Endpoints ----------------------------------------------------------------


async def _seed_news(session_factory) -> None:
    # Recent, timezone-aware dates so the freshness window never ages out.
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        a1 = NewsArticle(symbol="RELIANCE.NS", source="Test", title="Profits up",
                         url="https://e.com/1", published_at=now - timedelta(days=1))
        a2 = NewsArticle(symbol="RELIANCE.NS", source="Test", title="Stock drops",
                         url="https://e.com/2", published_at=now - timedelta(days=2))
        session.add_all([a1, a2])
        await session.flush()
        session.add_all([
            NewsSentiment(article_id=a1.id, label="positive", score=0.95, model="ProsusAI/finbert"),
            NewsSentiment(article_id=a2.id, label="negative", score=0.90, model="ProsusAI/finbert"),
        ])
        session.add(Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O"))
        await session.commit()


async def test_news_endpoint(client, session_factory):
    await _seed_news(session_factory)
    r = await client.get("/api/v1/stocks/RELIANCE/news")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    # Newest first (Profits up published 08-18)
    assert body["items"][0]["title"] == "Profits up"
    assert body["items"][0]["sentiment"] == "positive"
    assert body["items"][1]["sentiment"] == "negative"


async def test_news_endpoint_unknown_symbol_404(client, session_factory):
    await _seed_news(session_factory)
    r = await client.get("/api/v1/stocks/ZZZ/news")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_sentiment_endpoint(client, session_factory):
    await _seed_news(session_factory)
    r = await client.get("/api/v1/stocks/RELIANCE/sentiment")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert body["count"] == 2
    # net = 0.95 + (-0.90) = 0.05 -> /2 = 0.025 -> neutral
    assert body["label"] == "neutral"
    assert abs(body["score"]) <= 0.1


async def test_sentiment_endpoint_no_news(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="NEW.NS", name="New", sector="X", industry="Y"))
        await session.commit()
    r = await client.get("/api/v1/stocks/NEW/sentiment")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["label"] == "neutral"
