# Item 13: GET /api/v1/landing bundles the landing page's queries, each
# exactly as its own endpoint returns it, and is rebuilt only when a job
# finishes.

from datetime import datetime, timezone

from app.models import JobRun
from app.services import landing_snapshot


def _by_key(body):
    return {tuple(q["key"]): q["data"] for q in body["queries"]}


async def test_entries_equal_the_real_endpoints(client, seeded):
    r = await client.get("/api/v1/landing")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == landing_snapshot.SNAPSHOT_VERSION
    assert body["generated_at"]

    got = _by_key(body)
    assert got, "seeded data should produce at least some entries"
    paths = {tuple(k): p for k, p in landing_snapshot.LANDING_QUERIES}
    for key, data in got.items():
        direct = await client.get(f"/api/v1{paths[key]}")
        assert direct.status_code == 200
        assert direct.json() == data, key

    # The seeded universe has prices and listings, so these must be present.
    assert ("benchmarks",) in got
    assert ("stocks", 1, 50, None, "market_cap", "desc", None) in got
    assert ("prices", "RELIANCE", "6mo") in got


async def test_failed_queries_are_left_out(client, seeded, monkeypatch):
    monkeypatch.setattr(
        landing_snapshot,
        "LANDING_QUERIES",
        [(["benchmarks"], "/benchmarks"), (["stock-detail", "NOPE"], "/stocks/NOPE")],
    )
    body = (await client.get("/api/v1/landing")).json()
    assert [q["key"] for q in body["queries"]] == [["benchmarks"]]


async def test_reused_until_a_job_finishes(client, seeded, session_factory, monkeypatch):
    builds = [0]
    real = landing_snapshot._build

    async def counting(app):
        builds[0] += 1
        return await real(app)

    monkeypatch.setattr(landing_snapshot, "_build", counting)

    await client.get("/api/v1/landing")
    await client.get("/api/v1/landing")
    assert builds[0] == 1

    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        session.add(JobRun(job_name="nightly_ingestion", status="success",
                           started_at=now, finished_at=now))
        await session.commit()

    await client.get("/api/v1/landing")
    assert builds[0] == 2


async def test_cacheable_like_other_reads(client, seeded):
    r = await client.get("/api/v1/landing")
    assert "max-age=60" in r.headers["cache-control"]
