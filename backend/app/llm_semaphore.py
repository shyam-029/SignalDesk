# LLM provider concurrency guard (Phase 8) — one semaphore per process.
#
# Concept: asyncio.Semaphore caps SIMULTANEOUS provider calls. Rate limits
# bound requests/minute; this bounds concurrent in-flight LLM calls so a
# burst of cache-miss ask/explain requests cannot open N parallel provider
# connections (cost + free-model 429s + event-loop pileup). Cached,
# scope-rejected, and insufficient-evidence answers never touch the
# semaphore — they return before any provider call. The daily budget counter
# in llm_narrative is unchanged (calls/day); this adds calls/AT-ONCE.
#
# Scope: in-process, like the rate limiter and the daily cap. A restart
# resets it; multiple replicas each get their own. Shared-Redis coordination
# is the Semester-2/multi-replica answer, not Phase 8.

import asyncio

from app.config import settings

_semaphore: asyncio.Semaphore | None = None
_semaphore_capacity: int | None = None


def get_semaphore() -> asyncio.Semaphore:
    """Return the process-wide LLM semaphore, sized from settings.

    Rebuilt when settings.llm_max_concurrent changes (tests monkeypatch it).
    """
    global _semaphore, _semaphore_capacity
    capacity = max(1, int(settings.llm_max_concurrent))
    if _semaphore is None or _semaphore_capacity != capacity:
        _semaphore = asyncio.Semaphore(capacity)
        _semaphore_capacity = capacity
    return _semaphore


def reset_state() -> None:
    """Test hook: drop the cached semaphore so the next caller rebuilds it."""
    global _semaphore, _semaphore_capacity
    _semaphore = None
    _semaphore_capacity = None
