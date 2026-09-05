# Google News RSS news provider.
#
# Search strategy (Phase 6.5 Part G): the PRIMARY query is the company's
# full name when the caller supplies one; only when that produces no usable
# (relevant) results does the provider fall back to the bare-symbol query
# ("RELIANCE NSE") it used previously. BOTH result sets pass the same
# relevance filter (services/news_relevance.py) and the approximately
# 30-day freshness window before being returned, so false positives and
# stale articles are dropped either way. Nothing is fabricated: an empty
# result means no usable articles were found.
#
# feedparser is synchronous, so we run it via asyncio.to_thread (same
# pattern as yfinance) to keep the event loop responsive.

import asyncio
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser

from app.providers.news_base import Article, NewsProvider
from app.services.news_relevance import is_fresh, is_relevant_article


class NewsProviderError(Exception):
    """Raised when a news source fails for a specific symbol."""


class GoogleNewsRSSProvider(NewsProvider):
    """News source backed by Google News RSS feeds."""

    _BASE_URL = (
        "https://news.google.com/rss/search"
        "?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    @staticmethod
    def _symbol_query(symbol: str) -> str:
        # "RELIANCE.NS" -> "RELIANCE" ; feed queries don't accept the suffix.
        return symbol.split(".")[0]

    def _fetch_entries(self, query: str) -> list:
        """Run one RSS query and return its raw entries (sync)."""
        url = self._BASE_URL.format(query=quote(query))
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:  # network/parse errors from feedparser
            raise NewsProviderError(f"RSS fetch failed: {exc}") from exc
        if parsed is None or not parsed.entries:
            return []
        return list(parsed.entries)

    @staticmethod
    def _to_article(entry, symbol: str) -> Article | None:
        """Convert one RSS entry to an Article (None when unusable)."""
        title = (entry.get("title") or "").strip()
        url = entry.get("link") or ""
        if not title or not url:
            return None
        published = None
        if entry.get("published_parsed"):
            from calendar import timegm
            from datetime import datetime

            published = datetime.fromtimestamp(
                timegm(entry.published_parsed), tz=timezone.utc
            )
        return Article(
            symbol=symbol,
            source="Google News",
            title=title,
            url=url,
            published_at=published,
            content=None,
        )

    async def fetch_articles(
        self, symbol: str, limit: int = 20, company_name: str | None = None
    ) -> list[Article]:
        def _fetch() -> list[Article]:
            # PRIMARY: the company's full name, post-filtered for relevance
            # and freshness. The extra keyword used to be appended to the
            # symbol query; the full name is discriminative on its own.
            if company_name:
                entries = self._fetch_entries(company_name)
                articles = [
                    a for a in (self._to_article(e, symbol) for e in entries)
                    if a is not None
                    and is_relevant_article(a.title, symbol, company_name)
                    and is_fresh(a.published_at)
                ]
                if articles:
                    return articles[:limit]

            # FALLBACK: bare-symbol query, same relevance filter + window.
            entries = self._fetch_entries(f"{self._symbol_query(symbol)} NSE")
            articles = [
                a for a in (self._to_article(e, symbol) for e in entries)
                if a is not None
                and is_relevant_article(a.title, symbol, company_name)
                and is_fresh(a.published_at)
            ]
            return articles[:limit]

        return await asyncio.to_thread(_fetch)
