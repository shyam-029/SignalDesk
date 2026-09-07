# Per-IP rate limiting (Phase 8) — in-process fixed windows.
#
# Concept: a fixed-window counter per (client IP, bucket). Each request
# consumes one token from its bucket; when the window's allowance is spent,
# the request is rejected with RateLimitError (→ 429 envelope + Retry-After).
# Buckets: "llm" (strictest: ask/explain/alpha-explanation), "expensive"
# (screener + heavy series fan-out), "default" (plain research reads).
#
# Scope warning: this limiter is IN-PROCESS (a module-level dict). It is
# correct for the current single-process Phase 8 deployment. With multiple
# replicas, load balancers, or a sleep-tolerant host that restarts often,
# move to shared storage (Redis) — per-process counters under-count.
#
# Privacy: buckets are keyed by client IP only. No user identity, no request
# bodies, no headers are stored. Stale buckets are pruned lazily on access.

import time

from app.config import settings
from app.errors import RateLimitError

# bucket name -> (limit per 60s). Limits come from settings at check time so
# tests can monkeypatch them without reimporting this module.
_BUCKETS = ("llm", "expensive", "default")

_WINDOW_SECONDS = 60

# (bucket, ip) -> [window_start_monotonic, count]
_state: dict[tuple[str, str], list[float]] = {}


def _limit_for(bucket: str) -> int:
    if bucket == "llm":
        return settings.rate_limit_llm_per_min
    if bucket == "expensive":
        return settings.rate_limit_expensive_per_min
    return settings.rate_limit_default_per_min


def _client_ip(request) -> str:
    """Best-effort client IP: X-Forwarded-For first hop, else transport peer.

    Only the leftmost forwarded entry is used (the client-facing proxy's
    claim). Never stored beyond the counter dict; never logged here.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return str(host or "unknown")[:64]


def reset_state() -> None:
    """Test hook: clear all counters."""
    _state.clear()


def check(request, bucket: str = "default") -> None:
    """Consume one token; raise RateLimitError when the window is exhausted.

    Raises RateLimitError with retry_after = seconds until the window rolls.
    Never raises for unknown bucket names (falls back to "default").
    """
    if bucket not in _BUCKETS:
        bucket = "default"
    limit = max(1, int(_limit_for(bucket)))
    now = time.monotonic()
    key = (bucket, _client_ip(request))
    entry = _state.get(key)
    if entry is None or now - entry[0] >= _WINDOW_SECONDS:
        _state[key] = [now, 1]
        _prune(now)
        return
    if entry[1] >= limit:
        retry_after = max(1, int(_WINDOW_SECONDS - (now - entry[0])) + 1)
        raise RateLimitError(
            "Rate limit exceeded. Please retry shortly.", retry_after=retry_after
        )
    entry[1] += 1


def _prune(now: float) -> None:
    """Drop expired windows so the dict stays bounded (lazy, amortized)."""
    if len(_state) < 4096:
        return
    expired = [k for k, (start, _) in _state.items() if now - start >= _WINDOW_SECONDS]
    for k in expired:
        del _state[k]
