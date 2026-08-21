# News provider interface (swappable news sources, mirrors MarketDataProvider).

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Article:
    """One news article about a symbol."""

    symbol: str
    source: str
    title: str
    url: str
    published_at: datetime | None
    content: str | None = None


class NewsProvider(ABC):
    """Contract every news source must implement."""

    @abstractmethod
    async def fetch_articles(self, symbol: str, limit: int = 20) -> list[Article]:
        """Return recent articles for a symbol (newest first).

        Args:
            symbol: fully-qualified symbol, e.g. "RELIANCE.NS".
            limit: maximum number of articles to return.

        Returns:
            Chronologically-sorted (newest-first) list of Article objects.
        """
        ...