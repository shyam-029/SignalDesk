# Per-stock page snapshots (owner request 2026-11-12: "make stock pages fast
# for a first-time visitor, free now and in the long term").
#
# After each nightly ingest, .github/workflows/ingest.yml (stock-snapshots job) runs
#   python -m app.services.stock_snapshot <out_dir>
# which writes <out_dir>/stock/<SYMBOL>.json for every listed stock and
# uploads them to a private Cloudflare R2 bucket. The frontend Worker serves
# /snapshot/stock/<SYMBOL>.json from that bucket, and the stock page seeds
# its query cache from it, the same way the landing page uses landing.json
# (services/landing_snapshot.py). The page renders at once even while Render
# sleeps; the hooks still refresh from the API in the background.
#
# File format (same as the landing snapshot):
#   {"version": 1, "generated_at": "...", "symbol": "RELIANCE",
#    "queries": [{"key": [...TanStack Query key...], "data": {...}}]}
# Every `data` is produced by calling the app's own route in-process, so it
# is exactly what that endpoint returns. A route that fails for a stock (no
# peers, a multiple the stock lacks) is left out; the page then fetches that
# one query from the API as before.
#
# What is deliberately NOT included (free-tier budget, measured 2026-11-12
# on RELIANCE):
#   - alpha/history (~28 KB) and technicals/series (~50 KB): 75% of a full
#     page's bytes. With them, 1,000 stocks a night would pull ~3 GB a month
#     out of Neon (free plan: 5 GB). Without them, ~0.7 GB. Both charts sit
#     lower on the page and load live.
#   - alpha/explanation: calls an LLM on a cache miss; never batch it.
#   - non-default tabs (other price ranges, financials views): loaded live
#     when a visitor clicks them.

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.batch_memo import MEMO_KEY

SNAPSHOT_VERSION = 1
# Parallel stocks. Each stock's calls run one after another on ONE database
# session, so this is also the number of database connections the batch
# holds (Neon's free compute allows ~100; the live API keeps its own pool).
CONCURRENCY = 24

# Speed (first run 2026-11-12 took >27 min at 6 stocks with a session per
# call): the job runs on GitHub's US runners, a long round trip from the
# database, so its time is almost all waiting. A session per stock (instead
# of per request) drops the per-request pre-ping, BEGIN and ROLLBACK round
# trips and lets repeated lookups (the stock row) come from the session's
# identity map; more stocks in parallel overlaps the remaining waits.
_stock_session: ContextVar[AsyncSession | None] = ContextVar("_stock_session", default=None)
# The batch engine's session factory (set by main()/install_shared_sessions).
_batch_factory: async_sessionmaker[AsyncSession] | None = None


def install_shared_sessions(app, factory: async_sessionmaker[AsyncSession]) -> None:
    """Point the app's get_session at the batch sessions (main() and tests)."""
    global _batch_factory
    from app.db import get_session

    _batch_factory = factory
    app.dependency_overrides[get_session] = shared_session


def stock_queries(symbol: str) -> list[tuple[list[Any], str]]:
    """(frontend query key, API path under /api/v1) for one stock page.

    Keys must match the hooks in frontend/src/lib/hooks.ts with the stock
    page's default arguments; frontend/src/__tests__/stockSnapshot.test.tsx
    checks the same keys from the frontend side.
    """
    s = quote(symbol, safe="")
    return [
        (["stock-detail", symbol], f"/stocks/{s}"),
        (["performance", symbol], f"/stocks/{s}/performance"),
        (["alpha", symbol], f"/stocks/{s}/alpha"),
        (["company-profile", symbol], f"/stocks/{s}/profile"),
        (["prices", symbol, "6mo"], f"/stocks/{s}/prices?range=6mo&resample=1d"),
        (["technicals", symbol], f"/stocks/{s}/technicals"),
        (["valuation", symbol, "PE"], f"/stocks/{s}/valuation?metric=PE"),
        (["valuation", symbol, "EV_EBITDA"], f"/stocks/{s}/valuation?metric=EV_EBITDA"),
        (["valuation", symbol, "PB"], f"/stocks/{s}/valuation?metric=PB"),
        (["valuation", symbol, "PS"], f"/stocks/{s}/valuation?metric=PS"),
        (["fundamentals", symbol], f"/stocks/{s}/fundamentals"),
        (["scores", symbol], f"/stocks/{s}/scores"),
        (["altman", symbol], f"/stocks/{s}/altman"),
        (["financials-history", symbol, "quarterly"], f"/stocks/{s}/financials/history?period_type=quarterly"),
        (["peers", symbol], f"/stocks/{s}/peers"),
        (["news", symbol, 12], f"/stocks/{s}/news?limit=12"),
        (["sentiment", symbol], f"/stocks/{s}/sentiment"),
        # One small row; feeds the ratings strip at the top of the page.
        (["strength", symbol], f"/stocks/{s}/strength"),
    ]


def canonical(symbol: str) -> str:
    """The frontend's normalizeSymbol: upper case, no .NS suffix."""
    s = symbol.strip().upper()
    return s[:-3] if s.endswith(".NS") else s


async def shared_session() -> AsyncIterator[AsyncSession]:
    """get_session override for the batch: the current stock's session.

    Installed only by main(); tests and the live API never use it.
    """
    session = _stock_session.get()
    if session is not None:
        yield session
        return
    # Outside a stock (listing the universe): a short-lived session of its own.
    if _batch_factory is None:
        raise RuntimeError("stock snapshot: shared_session used without a batch factory")
    async with _batch_factory() as own:
        yield own


async def build_one(
    client: httpx.AsyncClient,
    symbol: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    """Call one stock's routes. With a session_factory, all of them share one
    session (main() points get_session at it); without, each request uses
    the app's normal dependency."""
    queries: list[dict[str, Any]] = []
    if session_factory is None:
        for key, path in stock_queries(symbol):
            r = await client.get(f"/api/v1{path}")
            if r.status_code == 200:
                queries.append({"key": key, "data": r.json()})
    else:
        async with session_factory() as session:
            # Repeated reads within this stock are answered once
            # (repositories/batch_memo.py); the live API never sets this.
            session.info[MEMO_KEY] = {}
            token = _stock_session.set(session)
            try:
                for key, path in stock_queries(symbol):
                    r = await client.get(f"/api/v1{path}")
                    if r.status_code == 200:
                        queries.append({"key": key, "data": r.json()})
                    elif r.status_code >= 500:
                        # A failed statement aborts the transaction; reset it
                        # so the stock's remaining calls still work.
                        await session.rollback()
            finally:
                _stock_session.reset(token)
    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": symbol,
        "queries": queries,
    }


async def list_symbols(client: httpx.AsyncClient) -> list[str]:
    """Every stock the site lists (the ranked universe), canonical form."""
    symbols: list[str] = []
    page = 1
    while True:
        r = await client.get(f"/api/v1/stocks?page={page}&limit=100")
        r.raise_for_status()
        items = r.json().get("items") or []
        symbols += [canonical(i["symbol"]) for i in items]
        if len(items) < 100:
            return sorted(set(symbols))
        page += 1


async def build_all(
    app,
    out_dir: Path,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> tuple[int, int]:
    """Write one file per stock. Returns (written, failed)."""
    target = out_dir / "stock"
    target.mkdir(parents=True, exist_ok=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://snapshot.internal", timeout=120
    ) as client:
        symbols = await list_symbols(client)
        sem = asyncio.Semaphore(CONCURRENCY)
        written = failed = 0

        async def one(sym: str) -> None:
            nonlocal written, failed
            async with sem:
                try:
                    body = await build_one(client, sym, session_factory)
                except Exception as exc:  # one bad stock never stops the run
                    failed += 1
                    print(f"FAILED {sym}: {type(exc).__name__}", flush=True)
                    return
            if not any(q["key"][0] == "stock-detail" for q in body["queries"]):
                failed += 1
                print(f"SKIPPED {sym}: no stock detail", flush=True)
                return
            (target / f"{sym}.json").write_text(
                json.dumps(body, separators=(",", ":")), encoding="utf-8"
            )
            written += 1

        await asyncio.gather(*(one(s) for s in symbols))
    return written, failed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m app.services.stock_snapshot <out_dir>")
        return 2
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings
    from app.db import asyncpg_ready_url
    from app.main import app

    # In-process calls all come from one "client"; lift the per-IP limits
    # for this batch process only (the live API keeps its own settings).
    # rate_limit reads these on every request.
    settings.rate_limit_default_per_min = 1_000_000
    settings.rate_limit_expensive_per_min = 1_000_000

    async def run() -> tuple[int, int]:
        # A batch-only engine: no pre-ping (connections are used back to
        # back), one connection per parallel stock.
        engine = create_async_engine(
            asyncpg_ready_url(settings.database_url),
            pool_pre_ping=False,
            pool_size=CONCURRENCY,
            max_overflow=0,
        )
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        install_shared_sessions(app, factory)
        try:
            return await build_all(app, Path(argv[1]), factory)
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    written, failed = asyncio.run(run())
    print(f"stock snapshots: {written} written, {failed} failed or skipped")
    # Publish nothing if most stocks failed (e.g. the database was down).
    return 0 if written > 0 and failed <= max(25, written // 10) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
