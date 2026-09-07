# Phase 7 tests — GET /debug/jobs.
#
# Seeds job_runs rows directly and checks the operational view: last run per
# job, scheduler liveness, and that nothing sensitive is exposed.

from datetime import datetime, timezone

from app.models import JobRun


async def _seed_runs(session_factory) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                JobRun(
                    job_name="ingest_prices", status="success",
                    started_at=datetime(2026, 9, 6, 18, 30, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 9, 6, 18, 44, tzinfo=timezone.utc),
                    duration_ms=840000, items_processed=250, items_failed=0,
                ),
                JobRun(
                    job_name="ingest_news", status="partial",
                    started_at=datetime(2026, 9, 6, 18, 50, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 9, 6, 18, 55, tzinfo=timezone.utc),
                    duration_ms=300000, items_processed=240, items_failed=10,
                    error_summary="10 item(s) failed",
                ),
            ]
        )
        await session.commit()


async def test_debug_jobs_shape_and_content(client, session_factory):
    await _seed_runs(session_factory)
    r = await client.get("/debug/jobs")
    assert r.status_code == 200
    body = r.json()

    assert isinstance(body["scheduler_running"], bool)
    by_name = {j["job_name"]: j for j in body["jobs"]}
    assert "ingest_prices" in by_name

    run = by_name["ingest_prices"]["last_run"]
    assert run["status"] == "success"
    assert run["items_processed"] == 250
    assert run["duration_ms"] == 840000

    news = by_name["ingest_news"]["last_run"]
    assert news["status"] == "partial"
    assert news["items_failed"] == 10
    assert "item(s) failed" in news["error_summary"]


async def test_debug_jobs_empty_db(client):
    r = await client.get("/debug/jobs")
    assert r.status_code == 200
    body = r.json()
    # Jobs are listed even with no recorded history.
    assert any(j["job_name"] == "nightly_ingestion" for j in body["jobs"])
    for job in body["jobs"]:
        assert job["last_run"] is None or isinstance(job["last_run"], dict)


async def test_debug_jobs_exposes_no_secrets(client, session_factory):
    """The response keys are a fixed allow-list; no env/credentials appear."""
    from app.config import settings

    await _seed_runs(session_factory)
    r = await client.get("/debug/jobs")
    text = r.text
    assert "api_key" not in text
    assert "token" not in text.lower()
    assert "Authorization" not in text
    assert "database_url" not in text
    if settings.upstox_analytics_token:
        assert settings.upstox_analytics_token not in text
    if settings.llm_api_key:
        assert settings.llm_api_key not in text
    # Row keys are limited to the curated summary shape.
    key_allowlist = {
        "job_name", "status", "started_at", "finished_at", "duration_ms",
        "items_processed", "items_failed", "error_summary",
    }
    for job in r.json()["jobs"]:
        assert set(job) == {"job_name", "last_run", "next_run_at"}
        if job["last_run"] is not None:
            assert set(job["last_run"]) == key_allowlist


async def test_debug_jobs_include_failed_run(client, session_factory):
    async with session_factory() as session:
        session.add(
            JobRun(
                job_name="ingest_prices", status="failed",
                started_at=datetime(2026, 9, 7, 18, 30, tzinfo=timezone.utc),
                finished_at=datetime(2026, 9, 7, 18, 31, tzinfo=timezone.utc),
                duration_ms=60000,
                error_summary="MarketDataError: provider down",
            )
        )
        await session.commit()
    r = await client.get("/debug/jobs")
    by_name = {j["job_name"]: j for j in r.json()["jobs"]}
    assert by_name["ingest_prices"]["last_run"]["status"] == "failed"
    assert "MarketDataError" in by_name["ingest_prices"]["last_run"]["error_summary"]


async def test_debug_jobs_latest_run_wins(client, session_factory):
    """Two runs of the same job: only the newest is surfaced."""
    await _seed_runs(session_factory)
    async with session_factory() as session:
        session.add(
            JobRun(
                job_name="ingest_prices", status="failed",
                started_at=datetime(2026, 9, 7, 18, 30, tzinfo=timezone.utc),
                finished_at=datetime(2026, 9, 7, 18, 31, tzinfo=timezone.utc),
                duration_ms=60000,
            )
        )
        await session.commit()
    r = await client.get("/debug/jobs")
    by_name = {j["job_name"]: j for j in r.json()["jobs"]}
    runs = [j for j in r.json()["jobs"] if j["job_name"] == "ingest_prices"]
    assert len(runs) == 1
    assert by_name["ingest_prices"]["last_run"]["status"] == "failed"


async def test_scheduler_state_defaults_when_not_started(client, session_factory):
    """Without the app lifespan (tests), the scheduler is honestly 'stopped'."""
    await _seed_runs(session_factory)
    r = await client.get("/debug/jobs")
    assert r.json()["scheduler_running"] is False
    for job in r.json()["jobs"]:
        assert job["next_run_at"] is None
