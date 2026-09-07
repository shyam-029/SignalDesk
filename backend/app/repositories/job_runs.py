# Job-run history queries (Phase 7).
#
# The scheduler records one row per pass execution; these helpers read that
# history for /debug/jobs and /status without exposing raw table access.

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobRun


async def latest_runs(session: AsyncSession) -> dict[str, JobRun]:
    """Return the most recent JobRun per job_name (by started_at)."""
    latest_started = (
        select(JobRun.job_name, func.max(JobRun.started_at).label("max_started"))
        .group_by(JobRun.job_name)
        .subquery()
    )
    rows = (
        await session.execute(
            select(JobRun).join(
                latest_started,
                (JobRun.job_name == latest_started.c.job_name)
                & (JobRun.started_at == latest_started.c.max_started),
            )
        )
    ).scalars().all()
    return {run.job_name: run for run in rows}


async def last_successful_run(
    session: AsyncSession, job_name: str | None = None
) -> JobRun | None:
    """Most recent run that succeeded fully or partially (data was written).

    Optionally scoped to one job (e.g. the core price pass, which drives the
    ingestion-staleness signal on /status).
    """
    q = (
        select(JobRun)
        .where(JobRun.status.in_(("success", "partial")))
        .order_by(JobRun.finished_at.desc())
        .limit(1)
    )
    if job_name is not None:
        q = q.where(JobRun.job_name == job_name)
    return (await session.execute(q)).scalars().first()


def summarize(run: JobRun) -> dict:
    """Serialize a JobRun for API responses (safe fields only)."""
    return {
        "job_name": run.job_name,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "items_processed": run.items_processed,
        "items_failed": run.items_failed,
        "error_summary": run.error_summary,
    }
