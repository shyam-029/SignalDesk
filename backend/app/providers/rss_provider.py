# Google News RSS news provider.
#
# Search strategy (Phase 6.5 Part G, widened 2026-09-06): the PRIMARY query
# is the company's full name when the caller supplies one. When that yields
# fewer than MIN_ARTICLES usable results, the bare-symbol query
# ("RELIANCE NSE") runs as well and the two result sets are merged
# (deduplicated by URL) so the research page reliably shows a usable set of
# articles within the freshness window. EVERY result passes the same
# relevance filter (services/news_relevance.py) and the freshness window
# before being returned. Nothing is fabricated: an empty result means no
# usable articles were found.
#
# feedparser is synchronous, so we run it via asyncio.to_thread (same
# pattern as yfinance) to keep the event loop responsive.

import asyncio
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser

from app.providers.news_base import Article, NewsProvider
from app.services.news_relevance import (
    MIN_ARTICLES,
    is_fresh,
    is_relevant_article,
)


class NewsProviderError(Exception):
    """Raised when a news source fails for a specific symbol."""


class GoogleNewsRSSProvider(NewsProvider):
    """News source backed by Google News RSS feeds."""

    _BASE_URL = (
        "https://news.google.com/rss/search"
        "?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    # Per-query fetch size: wide enough that the filtered union reaches the
    # minimum usable set for most symbols.
    _FETCH_SIZE = 40

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

    def _usable_articles(
        self, entries: list, symbol: str, company_name: str | None
    ) -> list[Article]:
        """Convert entries and keep only relevant, fresh, well-formed ones."""
        articles: list[Article] = []
        for entry in entries:
            article = self._to_article(entry, symbol)
            if article is None:
                continue
            if not is_relevant_article(article.title, symbol, company_name):
                continue
            if not is_fresh(article.published_at):
                continue
            articles.append(article)
        return articles

    async def fetch_articles(
        self, symbol: str, limit: int = 20, company_name: str | None = None
    ) -> list[Article]:
        def _fetch() -> list[Article]:
            # PRIMARY: the company's full name, post-filtered for relevance
            # and freshness.
            articles: list[Article] = []
            seen_urls: set[str] = set()
            if company_name:
                articles = self._usable_articles(
                    self._fetch_entries(company_name)[: self._FETCH_SIZE],
                    symbol,
                    company_name,
                )
                seen_urls = {a.url for a in articles}

            # MERGE: when the name search alone is thin, also run the
            # symbol query and union the results (dedup by URL) instead of
            # showing a starved feed. Same filter on both sets.
            if len(articles) < MIN_ARTICLES:
                fallback = self._usable_articles(
                    self._fetch_entries(
                        f"{self._symbol_query(symbol)} NSE"
                    )[: self._FETCH_SIZE],
                    symbol,
                    company_name,
                )
                for article in fallback:
                    if article.url not in seen_urls:
                        seen_urls.add(article.url)
                        articles.append(article)

            # Newest first, then cap.
            articles.sort(
                key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            return articles[:limit]

        return await asyncio.to_thread(_fetch)
