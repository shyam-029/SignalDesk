# Item 14: the screener analyses the universe once per data change, not per
# request, and returns exactly what the old per-request loop returned.

from datetime import datetime, timezone

from app.models import JobRun
from app.services import analysis, screener_cache


def _count_analyses(monkeypatch) -> list[int]:
    calls = [0]
    real = analysis.analyze_stock

    async def counting(session, stock):
        calls[0] += 1
        return await real(session, stock)

    monkeypatch.setattr(analysis, "analyze_stock", counting)
    return calls


async def test_repeat_requests_reuse_the_snapshot(client, seeded, monkeypatch):
    calls = _count_analyses(monkeypatch)

    first = await client.get("/api/v1/screener")
    assert first.status_code == 200
    built = calls[0]
    assert built == first.json()["total"] == 2  # seeded: RELIANCE, TCS

    # Different filters/sorts/pages: no re-analysis, same underlying rows.
    for params in (
        {"sort": "symbol", "direction": "desc"},
        {"sector": "IT"},
        {"page": 2, "limit": 1},
    ):
        r = await client.get("/api/v1/screener", params=params)
        assert r.status_code == 200
    assert calls[0] == built


async def test_a_finished_job_rebuilds_the_snapshot(client, seeded, session_factory, monkeypatch):
    calls = _count_analyses(monkeypatch)
    await client.get("/api/v1/screener")
    built = calls[0]

    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        session.add(JobRun(job_name="nightly_ingestion", status="success",
                           started_at=now, finished_at=now))
        await session.commit()

    await client.get("/api/v1/screener")
    assert calls[0] == 2 * built  # rebuilt once
    await client.get("/api/v1/screener")
    assert calls[0] == 2 * built  # and reused again


async def test_snapshot_expires_after_max_age(client, seeded, monkeypatch):
    calls = _count_analyses(monkeypatch)
    await client.get("/api/v1/screener")
    built = calls[0]
    monkeypatch.setattr(screener_cache, "SNAPSHOT_MAX_AGE_SECONDS", 0)
    await client.get("/api/v1/screener")
    assert calls[0] == 2 * built


async def test_rows_match_direct_analysis(client, seeded, session_factory):
    """The cached table is field-for-field what analyze_stock returns."""
    r = await client.get("/api/v1/screener", params={"limit": 250})
    items = {i["symbol"]: i for i in r.json()["items"]}

    from sqlalchemy import select

    from app.models import Stock

    async with session_factory() as session:
        stocks = (await session.execute(select(Stock))).scalars().all()
        for stock in stocks:
            a = await analysis.analyze_stock(session, stock)
            assert items[a.symbol] == {
                "symbol": a.symbol,
                "name": a.name,
                "sector": a.sector,
                "industry": a.industry,
                "profitability": a.profitability,
                "solvency": a.solvency,
                "valuation_status": a.valuation_status,
                "margin_pct": a.margin_pct,
            }
