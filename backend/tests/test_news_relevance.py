# Phase 6.5 Part G tests â€” news relevance, fallback, freshness. Zero network:
# feedparser is monkeypatched; relevance/freshness rules are pure.

from datetime import datetime, timedelta, timezone

import pytest

from app.providers.rss_provider import GoogleNewsRSSProvider
from app.services.news_relevance import (
    is_fresh,
    is_relevant_article,
)


# --- Relevance rules (pure) ---------------------------------------------------


def test_full_company_name_tokens_match():
    assert is_relevant_article(
        "Reliance Industries posts record quarterly profit",
        "RELIANCE.NS",
        "Reliance Industries Limited",
    )


def test_all_distinctive_tokens_required():
    # "Industries" is distinctive here (only suffixes are stop words): the
    # title must contain both tokens of the name.
    assert is_relevant_article(
        "Reliance Industries wins green energy approval", "RELIANCE.NS",
        "Reliance Industries Limited",
    )
    # Bare brand token without the rest still matches when the name has one
    # distinctive token after suffix removal.
    assert is_relevant_article(
        "Reliance refiner margins improve", "RELIANCE.NS",
        "Reliance Industries Limited",
    )


def test_generic_noun_rejected():
    # An article about banks in general must not land on HDFC Bank.
    assert not is_relevant_article(
        "Bank stocks rally after rate decision", "HDFCBANK.NS",
        "HDFC Bank Limited",
    )


def test_unrelated_symbol_match_rejected():
    # "LT Foods" mentions the LT ticker but is a different company.
    assert not is_relevant_article(
        "LT Foods quarterly profit rises", "LT.NS",
        "Larsen & Toubro Limited",
    )
    # And a real Larsen & Toubro headline passes via its name tokens.
    assert is_relevant_article(
        "Larsen & Toubro wins order", "LT.NS", "Larsen & Toubro Limited",
    )


def test_parent_company_confusion_blocked():
    # "HDFC" alone (the former parent) is not HDFC Bank.
    assert not is_relevant_article(
        "HDFC sells stake in subsidiary", "HDFCBANK.NS", "HDFC Bank Limited",
    )


def test_long_symbol_mention_is_enough():
    assert is_relevant_article(
        "SBIN cuts lending rate", "SBIN.NS", "State Bank of India",
    )
    # But only the full name saves short-symbol articles.
    assert is_relevant_article(
        "State Bank of India cuts lending rate", "SBIN.NS",
        "State Bank of India",
    )


def test_short_symbol_alone_is_not_enough():
    # Bare "ITC" without the company name context is not trusted for a
    # 3-character symbol.
    assert not is_relevant_article("ITC mode enabled", "ITC.NS", None)


def test_word_boundary_prevents_substring_hits():
    assert not is_relevant_article(
        "Titanic submarine investor files case", "TITAN.NS", "Titan Company Limited"
    )


def test_empty_title_never_relevant():
    assert not is_relevant_article("", "RELIANCE.NS", "Reliance Industries Limited")


# --- Freshness (pure) ---------------------------------------------------------


def test_freshness_window_boundary():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    assert is_fresh(now - timedelta(days=29), now=now)
    assert not is_fresh(now - timedelta(days=31), now=now)
    assert not is_fresh(now - timedelta(days=30, minutes=1), now=now)


def test_freshness_undated_article_kept():
    assert is_fresh(None)


def test_freshness_naive_datetime_treated_as_utc():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 1)  # naive, just before the cutoff
    assert is_fresh(naive, now=now)
    old_naive = datetime(2026, 7, 1)
    assert not is_fresh(old_naive, now=now)


# --- Provider behavior (feedparser mocked) ------------------------------------


class _FakeEntry:
    """Mimics a feedparser entry: dict-style attribute access."""

    def __init__(self, title: str, link: str, published_parsed=None):
        self.title = title
        self.link = link
        self.published_parsed = published_parsed

    def get(self, key, default=None):
        return getattr(self, key, default)


def _rss_entries(entries):
    class _Parsed:
        pass

    parsed = _Parsed()
    parsed.entries = entries
    return parsed


def _ts(days_ago: int):
    from calendar import timegm

    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return timegm(dt.timetuple())


def _struct_ts(days_ago: int):
    """struct_time like feedparser's published_parsed, N days before now."""
    from time import gmtime

    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return gmtime(dt.timestamp())


@pytest.fixture()
def seen_queries(monkeypatch):
    queries = []

    def _fake_parse(url):
        queries.append(url)
        return _rss_entries([])

    monkeypatch.setattr(
        "app.providers.rss_provider.feedparser.parse", _fake_parse
    )
    return queries


async def test_company_name_search_used_first(seen_queries, monkeypatch):
    provider = GoogleNewsRSSProvider()
    entries = [
        _FakeEntry("Reliance Industries raises guidance", "https://n.com/1", _struct_ts(1)),
    ]

    def _parse(url):
        seen_queries.append(url)
        return _rss_entries(entries if "Reliance+Industries" in url or "Reliance%20Industries" in url else [])

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", company_name="Reliance Industries Limited")
    assert len(articles) == 1
    assert articles[0].title == "Reliance Industries raises guidance"
    # The fallback symbol query must NOT have run: the name search produced
    # usable results.
    assert len(seen_queries) == 1
    assert "NSE" not in seen_queries[0]


async def test_fallback_to_symbol_query_when_name_search_empty(seen_queries, monkeypatch):
    provider = GoogleNewsRSSProvider()

    def _parse(url):
        seen_queries.append(url)
        if "NSE" in url:
            return _rss_entries([
                _FakeEntry("Reliance Industries names new CFO", "https://n.com/2", _struct_ts(2)),
            ])
        return _rss_entries([])  # name search returns nothing

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", company_name="Reliance Industries Limited")
    assert len(articles) == 1
    assert len(seen_queries) == 2
    assert "NSE" in seen_queries[1]


async def test_fallback_results_also_filtered(seen_queries, monkeypatch):
    provider = GoogleNewsRSSProvider()

    def _parse(url):
        seen_queries.append(url)
        if "NSE" in url:
            return _rss_entries([
                # Unrelated to Reliance: must be dropped by the same filter.
                _FakeEntry("Cricket team posts huge total", "https://n.com/3", _struct_ts(1)),
                _FakeEntry("Reliance Industries board meets", "https://n.com/4", _struct_ts(1)),
            ])
        return _rss_entries([])

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", company_name="Reliance Industries Limited")
    assert [a.title for a in articles] == ["Reliance Industries board meets"]


async def test_stale_articles_dropped(seen_queries, monkeypatch):
    provider = GoogleNewsRSSProvider()
    entries = [
        _FakeEntry("Reliance Industries old story", "https://n.com/5", _struct_ts(45)),
        _FakeEntry("Reliance Industries fresh story", "https://n.com/6", _struct_ts(3)),
    ]

    def _parse(url):
        seen_queries.append(url)
        return _rss_entries(entries)

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", company_name="Reliance Industries Limited")
    assert [a.title for a in articles] == ["Reliance Industries fresh story"]


async def test_stale_name_results_trigger_fallback(seen_queries, monkeypatch):
    """Name search whose ONLY hits are stale yields no usable results, so the
    provider must fall back to the symbol query (freshness counts as unusable)."""
    provider = GoogleNewsRSSProvider()

    def _parse(url):
        seen_queries.append(url)
        if "NSE" in url:
            return _rss_entries([
                _FakeEntry("Reliance Industries from fallback", "https://n.com/7", _struct_ts(2)),
            ])
        return _rss_entries([
            _FakeEntry("Reliance Industries ancient", "https://n.com/8", _struct_ts(90)),
        ])

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", company_name="Reliance Industries Limited")
    assert [a.title for a in articles] == ["Reliance Industries from fallback"]
    assert len(seen_queries) == 2


async def test_limit_respected(seen_queries, monkeypatch):
    provider = GoogleNewsRSSProvider()
    entries = [
        _FakeEntry(f"Reliance Industries story {i}", f"https://n.com/{i}", _struct_ts(1))
        for i in range(10)
    ]

    def _parse(url):
        seen_queries.append(url)
        return _rss_entries(entries)

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", limit=3, company_name="Reliance Industries Limited")
    assert len(articles) == 3

