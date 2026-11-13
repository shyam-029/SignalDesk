# Landing-page snapshot (work list item 13).
#
# The landing page used to make about eight API calls to Render on first
# load (benchmarks, two stock lists, and RELIANCE's detail, alpha,
# technicals and prices). On a cold Render instance that left it blank for
# ~40 s.
#
# GET /api/v1/landing returns all of them in one response:
#   {"version": 1, "generated_at": "...", "queries": [{"key": [...], "data": {...}}]}
# Each entry's `key` is the frontend's TanStack Query key for that call, and
# `data` is exactly what the matching endpoint returns. The responses are
# produced by calling the app's own routes in-process, so the shapes can
# never drift from the real endpoints.
#
# The same JSON is fetched nightly by .github/workflows/ingest.yml (landing-snapshot job)
# and committed as frontend/public/snapshot/landing.json, so Cloudflare
# serves it as a static file with no Render call at all. The frontend seeds
# its query cache from that file and then refreshes from the API as usual.
#
# Freshness: like the screener cache, rebuilt when the newest finished
# job_runs row changes, or after SNAPSHOT_MAX_AGE_SECONDS. In-process memory;
# a restart rebuilds on the first request.

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobRun

SNAPSHOT_VERSION = 1
SNAPSHOT_MAX_AGE_SECONDS = 60 * 60

PREVIEW_SYMBOL = "RELIANCE"

# (frontend query key, API path under /api/v1). Keys must match the hooks in
# frontend/src/lib/hooks.ts; frontend/src/__tests__/landingSnapshot.test.tsx
# checks the same list from the frontend side.
LANDING_QUERIES: list[tuple[list[Any], str]] = [
    (["benchmarks"], "/benchmarks"),
    (
        ["stocks", 1, 50, None, "market_cap", "desc", None],
        "/stocks?page=1&limit=50&sort=market_cap&direction=desc",
    ),
    (
        ["stocks", 1, 8, None, "market_cap", "desc", None],
        "/stocks?page=1&limit=8&sort=market_cap&direction=desc",
    ),
    (["stock-detail", PREVIEW_SYMBOL], f"/stocks/{PREVIEW_SYMBOL}"),
    (["alpha", PREVIEW_SYMBOL], f"/stocks/{PREVIEW_SYMBOL}/alpha"),
    (["technicals", PREVIEW_SYMBOL], f"/stocks/{PREVIEW_SYMBOL}/technicals"),
    (
        ["prices", PREVIEW_SYMBOL, "6mo"],
        f"/stocks/{PREVIEW_SYMBOL}/prices?range=6mo&resample=1d",
    ),
]


@dataclass
class _Snapshot:
    stamp: object
    built_at: float
    body: dict[str, Any]


_snapshot: _Snapshot | None = None
_lock: asyncio.Lock | None = None


def reset_cache() -> None:
    """Test hook: forget the snapshot (and the lock, which is loop-bound)."""
    global _snapshot, _lock
    _snapshot = None
    _lock = None


async def _data_stamp(session: AsyncSession) -> object:
    return await session.scalar(select(func.max(JobRun.finished_at)))


def _is_fresh(snap: _Snapshot | None, stamp: object) -> bool:
    return (
        snap is not None
        and snap.stamp == stamp
        and time.monotonic() - snap.built_at < SNAPSHOT_MAX_AGE_SECONDS
    )


async def _build(app: FastAPI) -> dict[str, Any]:
    """Call each landing endpoint in-process and collect the successes.

    A failing call (for example no prices stored yet) is left out instead of
    failing the whole snapshot: the frontend then simply fetches that one
    query from the API as it always did.
    """
    queries: list[dict[str, Any]] = []
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://landing.internal") as c:
        for key, path in LANDING_QUERIES:
            r = await c.get(f"/api/v1{path}")
            if r.status_code == 200:
                queries.append({"key": key, "data": r.json()})
    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "queries": queries,
    }


async def get_snapshot(session: AsyncSession, app: FastAPI) -> dict[str, Any]:
    global _snapshot, _lock
    stamp = await _data_stamp(session)
    if _is_fresh(_snapshot, stamp):
        return _snapshot.body  # type: ignore[union-attr]
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _is_fresh(_snapshot, stamp):
            return _snapshot.body  # type: ignore[union-attr]
        body = await _build(app)
        _snapshot = _Snapshot(stamp=stamp, built_at=time.monotonic(), body=body)
        return body
