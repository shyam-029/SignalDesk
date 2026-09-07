# Server-side data-freshness classification (Phase 7).
#
# One small, testable classifier shared by the API. Statuses:
#   current     - the timestamp is within the domain's TTL
#   stale       - a real timestamp exists but is older than the TTL
#   unavailable - there is no trustworthy timestamp at all (never fabricated)
#
# TTLs are per data domain; prices tolerate ~3 days so weekends and market
# holidays are not misreported as staleness. The news domain mirrors the
# existing 60-day ingestion/display window in the news service.

from datetime import date, datetime, time, timedelta, timezone

FRESH_CURRENT = "current"
FRESH_STALE = "stale"
FRESH_UNAVAILABLE = "unavailable"

PRICE_TTL = timedelta(days=3)
FUNDAMENTALS_TTL = timedelta(days=30)
NEWS_TTL = timedelta(days=60)
ALPHA_TTL = timedelta(days=2)


def _to_aware(ts: datetime | date) -> datetime:
    return (
        datetime.combine(ts, time.min, tzinfo=timezone.utc)
        if isinstance(ts, date) and not isinstance(ts, datetime)
        else ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    )


def classify(
    timestamp: datetime | date | None,
    ttl: timedelta,
    now: datetime | None = None,
) -> str:
    """Classify a timestamp as current / stale / unavailable.

    A missing timestamp is `unavailable` — the absence of a timestamp is
    never reported as fresh, and no timestamp is ever invented.
    """
    if timestamp is None:
        return FRESH_UNAVAILABLE
    now = now or datetime.now(timezone.utc)
    return FRESH_STALE if now - _to_aware(timestamp) > ttl else FRESH_CURRENT


def is_stale(
    timestamp: datetime | date | None,
    ttl: timedelta,
    now: datetime | None = None,
) -> bool | None:
    """Boolean convenience: True = stale, False = fresh, None = no timestamp."""
    status = classify(timestamp, ttl, now)
    if status == FRESH_UNAVAILABLE:
        return None
    return status == FRESH_STALE
