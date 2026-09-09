# start_scheduler environment-gating tests (M1-T5, Plan 21.2 / D79).
#
# GitHub Actions is the ONLY production scheduler. The in-process APScheduler
# must register the nightly ingestion job in development (local convenience)
# and register NOTHING in production, while still STARTING in production so
# /status/full keeps reporting an honest scheduler="running" (main.py reads
# app.state.scheduler.running). A production deployment that silently ran the
# 1.5-2 h nightly ingestion on the Render free instance (0.1 CPU / 512 MB)
# alongside Actions is exactly the regression these tests pin shut.

from app import jobs
from app.config import settings


def test_start_scheduler_registers_nightly_job_in_development(monkeypatch):
    """Development (default APP_ENV): exactly the 18:30 IST nightly job."""
    monkeypatch.setattr(settings, "app_env", "development")
    scheduler = jobs.start_scheduler()
    try:
        assert scheduler.running
        assert [job.id for job in scheduler.get_jobs()] == ["nightly_ingestion"]
    finally:
        scheduler.shutdown(wait=False)


def test_start_scheduler_starts_with_no_jobs_in_production(monkeypatch):
    """APP_ENV=production: scheduler alive, ZERO jobs registered."""
    monkeypatch.setattr(settings, "app_env", "production")
    scheduler = jobs.start_scheduler()
    try:
        assert scheduler.running
        assert scheduler.get_jobs() == []
    finally:
        scheduler.shutdown(wait=False)
