# Google News RSS news provider.
#
# Free, no API key, reliable. Query = "<company query> NSE/BSE". We search by
# the bare symbol (e.g. "RELIANCE") because RSS feeds don't accept "RELIANCE.NS".
# feedparser is synchronous, so we run it via asyncio.to_thread (same pattern as
# yfinance) to keep the event loop responsive.

import asyncio
from urllib.parse import quote

import feedparser

from app.providers.news_base import Article, NewsProvider


class NewsProviderError(Exception):
    """Raised when a news source fails for a specific symbol."""


class GoogleNewsRSSProvider(NewsProvider):
    """News source backed by Google News RSS feeds."""

    _BASE_URL = (
        "https://news.google.com/rss/search"
        "?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    @staticmethod
    def _query_for(symbol: str) -> str:
        # "RELIANCE.NS" -> "RELIANCE" ; feed queries don't accept the suffix.
        return symbol.split(".")[0]

    async def fetch_articles(self, symbol: str, limit: int = 20) -> list[Article]:
        def _fetch() -> list[Article]:
            query = quote(f"{self._query_for(symbol)} NSE")
            url = self._BASE_URL.format(query=query)
            try:
                parsed = feedparser.parse(url)
            except Exception as exc:  # network/parse errors from feedparser
                raise NewsProviderError(
                    f"RSS fetch failed for {symbol}: {exc}"
                ) from exc

            if parsed is None or not parsed.entries:
                return []

            articles: list[Article] = []
            for entry in parsed.entries[:limit]:
                published = None
                if entry.get("published_parsed"):
                    from calendar import timegm
                    from datetime import datetime, timezone

                    published = datetime.fromtimestamp(
                        timegm(entry.published_parsed), tz=timezone.utc
                    )
                articles.append(
                    Article(
                        symbol=symbol,
                        source="Google News",
                        title=(entry.get("title") or "").strip(),
                        url=entry.get("link") or "",
                        published_at=published,
                        content=None,
                    )
                )
            return articles

        return await asyncio.to_thread(_fetch)