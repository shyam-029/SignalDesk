# News relevance + freshness rules (Phase 6.5 Part G, widened 2026-09-06) —
# pure functions, no I/O.
#
# Why this exists: the ingestion used to search Google News by the bare
# trading symbol ("RELIANCE NSE"), which drags in articles about other
# companies and generic matches. Ingestion now searches by the company's
# full name first, falls back to (and then merges with) the symbol query
# until enough usable articles exist, and post-filters every result through
# these rules. The bias is still toward precision over a bare symbol search,
# but the rules are deliberately looser than the original all-tokens rule so
# the research page reliably shows at least a handful of articles.

import re
from datetime import datetime, timedelta, timezone

# The freshness window (product decision 2026-09-06, widened from ~30 days so
# the research page reliably shows a usable set of articles).
NEWS_FRESHNESS_DAYS = 60

# Minimum usable articles per fetch before the provider merges in the
# symbol-query results as well (product decision 2026-09-06).
MIN_ARTICLES = 8

# Corporate/legal suffixes and filler words that never identify a company.
_CORPORATE_STOPWORDS = {
    "limited", "ltd", "llp", "company", "co", "corp", "corporation",
    "inc", "incorporated", "the", "and", "of",
}


def distinctive_tokens(company_name: str) -> list[str]:
    """Meaningful, lowercase tokens of a company name.

    Corporate suffixes ("Limited", "Corp") are dropped; single characters
    are dropped ("L" in "L&T"). Returns [] when nothing distinctive remains.
    """
    tokens = re.findall(r"[a-z0-9]+", (company_name or "").lower())
    return [
        t for t in tokens
        if t not in _CORPORATE_STOPWORDS and len(t) >= 2
    ]


def _contains_token(haystack: str, token: str) -> bool:
    """Whole-token containment (letters/digits count as token characters)."""
    pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def is_relevant_article(title: str, symbol: str, company_name: str | None) -> bool:
    """Decide whether a headline is about the given company.

    Rules (an article is relevant when ANY holds):
      1. It contains the bare trading symbol as a standalone token, and the
         symbol is long enough to be discriminative (>= 4 chars).
      2. It contains ANY distinctive company-name token, word-bounded. The
         filter was loosened from "all tokens" to "any token" (product
         decision 2026-09-06) after the strict rule starved the research
         page down to 1-2 articles; the multi-token names still disambiguate
         far better than a bare generic noun, and the source queries already
         bias results toward the company.
    """
    title_l = (title or "").lower()
    if not title_l:
        return False

    bare_symbol = (symbol or "").split(".")[0].lower()
    if bare_symbol and len(bare_symbol) >= 4 and _contains_token(title_l, bare_symbol):
        return True

    if not company_name:
        return False

    tokens = distinctive_tokens(company_name)
    if not tokens:
        return False

    return any(_contains_token(title_l, token) for token in tokens)


def is_fresh(
    published_at: datetime | None,
    now: datetime | None = None,
    days: int = NEWS_FRESHNESS_DAYS,
) -> bool:
    """True when the article is inside the freshness window (or undated).

    Naive datetimes are treated as UTC (Google News RSS timestamps are UTC
    and the ingestion pipeline stores timezone-aware values).
    """
    if published_at is None:
        return True
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return published_at >= now - timedelta(days=days)
