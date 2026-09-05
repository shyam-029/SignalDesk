# Phase 6.5 Part G tests â€” news relevance, fallback, freshness. Zero network:
# feedparser is monkeypatched; relevance/freshness rules are pure.

from datetime import datetime, timedelta, timezone

import pytest

from app.providers.rss_provider import GoogleNewsRSSProvider
from app.services.news_relevance import (
    NEWS_FRESHNESS_DAYS,
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


def test_any_distinctive_token_matches():
    # Loosened (2026-09-06): one distinctive token is enough, so the research
    # page reliably shows a usable set of articles.
    assert is_relevant_article(
        "Reliance refiner margins improve", "RELIANCE.NS",
        "Reliance Industries Limited",
    )


def test_generic_noun_alone_still_rejected_without_context():
    # A generic noun that is not part of the company's distinctive tokens
    # still cannot pull articles in ("ITC" style short symbols with no name).
    assert not is_relevant_article(
        "Cement stocks rally after rate decision", "TITAN.NS",
        "Titan Company Limited",
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


def test_word_boundary_prevents_substring_hits():
    assert not is_relevant_article(
        "Titanic submarine investor files case", "TITAN.NS", "Titan Company Limited"
    )


def test_empty_title_never_relevant():
    assert not is_relevant_article("", "RELIANCE.NS", "Reliance Industries Limited")


# --- Freshness (pure) ---------------------------------------------------------


def test_freshness_window_boundary():
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    assert is_fresh(now - timedelta(days=NEWS_FRESHNESS_DAYS - 1), now=now)
    assert not is_fresh(now - timedelta(days=NEWS_FRESHNESS_DAYS + 1), now=now)
    assert not is_fresh(
        now - timedelta(days=NEWS_FRESHNESS_DAYS, minutes=1), now=now
    )


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


async def test_company_name_search_runs_first(seen_queries, monkeypatch):
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
    # The name search is always the PRIMARY (first) query.
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


async def test_thin_name_results_merge_symbol_query(seen_queries, monkeypatch):
    """Fewer than MIN_ARTICLES usable name results triggers the symbol query,
    and the union (deduplicated by URL) is returned."""
    from app.services.news_relevance import MIN_ARTICLES

    provider = GoogleNewsRSSProvider()
    name_entries = [
        _FakeEntry(f"Reliance Industries story {i}", f"https://n.com/name/{i}", _struct_ts(i + 1))
        for i in range(MIN_ARTICLES - 1)  # one short of the threshold
    ]
    symbol_entries = [
        _FakeEntry("Reliance shares rise after results", "https://n.com/sym/0", _struct_ts(1)),
        # Duplicate URL: must be dropped by the merge.
        _FakeEntry("Reliance Industries story 0", "https://n.com/name/0", _struct_ts(9)),
    ]

    def _parse(url):
        seen_queries.append(url)
        if "NSE" in url:
            return _rss_entries(symbol_entries)
        return _rss_entries(name_entries)

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", company_name="Reliance Industries Limited")
    assert len(articles) == MIN_ARTICLES  # (MIN-1) unique name + 1 new symbol hit
    assert len(seen_queries) == 2
    assert {a.url for a in articles if "/sym/" in a.url} == {"https://n.com/sym/0"}


async def test_name_search_alone_suffices_when_thick(seen_queries, monkeypatch):
    from app.services.news_relevance import MIN_ARTICLES

    provider = GoogleNewsRSSProvider()
    entries = [
        _FakeEntry(f"Reliance Industries story {i}", f"https://n.com/{i}", _struct_ts(i + 1))
        for i in range(MIN_ARTICLES)
    ]

    def _parse(url):
        seen_queries.append(url)
        return _rss_entries(entries)

    monkeypatch.setattr("app.providers.rss_provider.feedparser.parse", _parse)

    articles = await provider.fetch_articles("RELIANCE.NS", company_name="Reliance Industries Limited")
    assert len(articles) == MIN_ARTICLES
    assert len(seen_queries) == 1  # no symbol query needed


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
        _FakeEntry("Reliance Industries old story", "https://n.com/5", _struct_ts(75)),
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
            _FakeEntry("Reliance Industries ancient", "https://n.com/8", _struct_ts(120)),
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


