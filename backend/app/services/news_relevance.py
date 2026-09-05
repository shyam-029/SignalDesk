# News relevance + freshness rules (Phase 6.5 Part G) — pure functions, no I/O.
#
# Why this exists: the ingestion used to search Google News by the bare
# trading symbol ("RELIANCE NSE"), which drags in articles about other
# companies and generic matches. Ingestion now searches by the company's
# full name first and post-filters every result (name search AND symbol
# fallback) through these rules, biasing hard toward precision: an article
# that might be about a different company is dropped rather than shown.
#
# Rules (an article is relevant when ANY holds):
#   1. It contains the bare trading symbol as a standalone token, and the
#      symbol is long enough to be discriminative (>= 4 chars). Short tickers
#      ("LT", "ITC") match too many unrelated tokens, so they only pass via
#      rule 2/3.
#   2. It contains the full normalized company-name phrase.
#   3. It contains ALL distinctive company-name tokens (word-bounded).
#      Requiring all tokens is what blocks generic nouns ("bank", "oil")
#      and names of other companies ("HDFC" vs "HDFC Bank", "LT Foods" vs
#      "Larsen & Toubro"). The cost is occasional false negatives ("SBI"
#      without the full "State Bank of India"), which we accept: the
#      full-name search query already biases titles toward the full name.
#
# Freshness: the product plan fixes an approximately 30-day news window.
# Dated articles older than the window are dropped at ingestion and at the
# endpoint. Undated articles cannot be proven stale and are kept.

import re
from datetime import datetime, timedelta, timezone

# The approximately 30-day freshness window (product plan, Phase 6.5).
NEWS_FRESHNESS_DAYS = 30

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
    """Decide whether a headline is about the given company (see module doc)."""
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

    # All distinctive tokens present anywhere in the title, each as a whole
    # token (this also covers the full normalized phrase, with or without
    # the original separators).
    return all(_contains_token(title_l, token) for token in tokens)


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
