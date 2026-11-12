# News relevance + freshness rules (Phase 6.5 Part G, widened 2026-09-06,
# rewritten 2026-11-11) — pure functions, no I/O.
#
# Why the 2026-11-11 rewrite: the 2026-09-06 rule accepted a headline when it
# contained ANY single word of the company name. That attached articles to
# the wrong stock whenever a name word is also an ordinary word, a person, a
# place or another organisation. Measured on stored headlines: ACC (US
# college sports, Bangladesh's Anti-Corruption Commission, the Asian Cricket
# Council), Trent (the TV show "Will Trent", Gary Trent Jr., Stoke-on-Trent),
# Eternal ("eternal life", a video game), State Bank of India (any "bank"
# headline), HDFC Bank (any "bank").
#
# The rule now weighs the signal:
#   STRONG (relevant on its own)
#     - the name's distinctive words appear together, in order
#       ("HDFC Bank", "State Bank of India", "Vodafone Idea");
#     - for a multi-word name, one of its non-generic words appears
#       ("InterGlobe", "Polycab", "Pidilite"): a brand word of a multi-word
#       name is rarely an ordinary word.
#   AMBIGUOUS (relevant only next to a market word: shares, stock, Q2,
#   crore, results, NSE, ...)
#     - the single word of a one-word name ("ACC", "Trent", "Eternal");
#     - the trading symbol ("INDIGO", "SBIN") or the name's initials ("SBI").
#   NEVER ON THEIR OWN
#     - generic words shared by many company names ("bank", "india",
#       "industries", group names like "tata" or "adani"). Callers can pass
#       the catalog's own generic words (generic_tokens_from_names).

import re
from collections import Counter
from collections.abc import Iterable
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

# Words common to many Indian listed-company names, plus business-group
# names shared by several listed companies. They never identify one company
# alone; a phrase containing them still can ("HDFC Bank", "Tata Motors").
GENERIC_NAME_TOKENS = frozenset({
    "bank", "india", "indian", "industries", "industry", "finance",
    "financial", "services", "service", "power", "energy", "steel", "motors",
    "motor", "capital", "housing", "holdings", "holding", "enterprises",
    "enterprise", "infra", "infrastructure", "global", "international",
    "national", "technologies", "technology", "tech", "systems", "solutions",
    "products", "chemicals", "chemical", "pharma", "pharmaceuticals", "life",
    "insurance", "general", "state", "new", "united", "hindustan", "bharat",
    "investment", "investments", "securities", "realty", "developers",
    "engineering", "electricals", "electric", "foods", "food", "textiles",
    "cement", "cements", "paper", "oil", "gas", "petroleum", "ports",
    "logistics", "media", "communications", "entertainment", "healthcare",
    "hospitals", "labs", "laboratories", "aviation", "airlines", "metals",
    "minerals", "mining", "agro", "sugar", "tea", "auto", "tyres", "cables",
    "wires", "consumer", "retail", "fashion", "home", "homes", "estates",
    "projects", "constructions", "construction", "green", "solar",
    "renewable", "renewables", "digital", "software", "networks", "telecom",
    "railway", "railways", "rail", "catering", "tourism", "travel", "hotels",
    "mutual", "fund", "asset", "management", "credit", "loans", "money",
    "first", "one", "great", "eastern", "western", "southern", "northern",
    "tata", "adani", "bajaj", "birla", "aditya", "mahindra", "godrej", "jsw",
    "jindal", "reliance", "hinduja", "murugappa", "torrent", "piramal",
    "shriram", "muthoot", "lodha", "essar", "vedanta",
})

# Words that put a headline in a market/company-news context.
MARKET_CONTEXT_WORDS = frozenset({
    "share", "shares", "stock", "stocks", "nse", "bse", "nifty", "sensex",
    "q1", "q2", "q3", "q4", "fy25", "fy26", "fy27", "quarter", "quarterly",
    "results", "result", "earnings", "profit", "profits", "loss", "revenue",
    "revenues", "ebitda", "margin", "margins", "crore", "cr", "lakh", "rs",
    "inr", "dividend", "bonus", "split", "buyback", "ipo", "listing",
    "target", "targets", "brokerage", "brokerages", "rating", "upgrade",
    "downgrade", "buy", "sell", "rally", "rallies", "surges", "slumps",
    "jumps", "falls", "gains", "valuation", "investors", "stake", "acquisition",
    "acquires", "merger", "demerger", "order", "orders", "contract", "board",
    "ceo", "md", "chairman", "founder", "ltd", "limited", "shareholders",
    "outlook", "guidance", "sales", "volumes", "capex", "plant", "growth",
    "demand", "analyst", "analysts", "investor", "acquisitions", "expansion",
    "fmcg", "cfo", "director", "appoints", "f&o",
})
_RUPEE = "₹"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def distinctive_tokens(company_name: str) -> list[str]:
    """Meaningful, lowercase tokens of a company name.

    Corporate suffixes ("Limited", "Corp") are dropped; single characters
    are dropped ("L" in "L&T"). Returns [] when nothing distinctive remains.
    """
    return [
        t for t in _tokens(company_name)
        if t not in _CORPORATE_STOPWORDS and len(t) >= 2
    ]


def generic_tokens_from_names(names: Iterable[str], min_names: int = 3) -> frozenset[str]:
    """Name words shared by at least `min_names` catalog companies, plus the
    built-in generic list. A word on many company names cannot identify one."""
    df: Counter[str] = Counter()
    for name in names:
        df.update(set(distinctive_tokens(name)))
    return GENERIC_NAME_TOKENS | {t for t, n in df.items() if n >= min_names}


def _contains_token(haystack: str, token: str) -> bool:
    """Whole-token containment (letters/digits count as token characters)."""
    pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _contains_sequence(tokens: list[str], seq: list[str]) -> bool:
    n = len(seq)
    return n > 0 and any(tokens[i : i + n] == seq for i in range(len(tokens) - n + 1))


def has_market_context(title: str) -> bool:
    if _RUPEE in (title or ""):
        return True
    return any(t in MARKET_CONTEXT_WORDS for t in _tokens(title))


def is_relevant_article(
    title: str,
    symbol: str,
    company_name: str | None,
    generic_tokens: frozenset[str] = GENERIC_NAME_TOKENS,
) -> bool:
    """Decide whether a headline is about the given company (see module notes)."""
    title_l = (title or "").lower()
    if not title_l:
        return False
    title_toks = [t for t in _tokens(title_l) if t not in _CORPORATE_STOPWORDS]
    name_toks = distinctive_tokens(company_name or "")

    # STRONG 1: the whole distinctive name, in order (stopwords ignored on
    # both sides, so "State Bank of India" matches "State Bank Of India").
    if len(name_toks) >= 2 and _contains_sequence(title_toks, name_toks):
        return True

    specific = [t for t in name_toks if t not in generic_tokens]

    # STRONG 2: a multi-word name's own brand word.
    if len(name_toks) >= 2 and any(
        len(t) >= 4 and _contains_token(title_l, t) for t in specific
    ):
        return True

    # AMBIGUOUS signals: need a market word next to them.
    ambiguous: set[str] = set()
    if len(name_toks) == 1 and specific:
        ambiguous.add(specific[0])
    bare_symbol = (symbol or "").split(".")[0].lower()
    if len(bare_symbol) >= 3:  # the stock's own ticker, even if a common word
        ambiguous.add(bare_symbol)
    if len(name_toks) >= 2:
        initials = "".join(t[0] for t in name_toks)
        if len(initials) >= 3:
            ambiguous.add(initials)
    if any(_contains_token(title_l, t) for t in ambiguous):
        return has_market_context(title)
    return False


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
