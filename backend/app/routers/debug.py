# GET /debug/jobs — operational visibility into scheduled jobs (Phase 7).
#
# Answers: what jobs exist, when each last ran, did it succeed, how long did
# it take, how much was processed, what failed, when is the next run.
#
# Security boundary: this endpoint returns ONLY the curated job_runs fields
# (name/status/timestamps/counts/truncated error_summary) plus scheduler
# liveness. It never exposes environment variables, credentials, request
# payloads, or arbitrary database contents. It is currently unauthenticated
# because the deployment is local-only; it MUST be restricted (or removed
# from the public surface) when the app is deployed (Phase 8 hardening).

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories import job_runs as job_repo

router = APIRouter(tags=["debug"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class JobRunInfo(BaseModel):
    job_name: str
    status: str
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    items_processed: int | None
    items_failed: int | None
    error_summary: str | None


class JobStatus(BaseModel):
    job_name: str
    last_run: JobRunInfo | None
    next_run_at: str | None  # from the live scheduler, when scheduled


class DebugJobsResponse(BaseModel):
    scheduler_running: bool
    jobs: list[JobStatus]


@router.get("/debug/jobs", response_model=DebugJobsResponse)
async def debug_jobs(request: Request, session: SessionDep) -> DebugJobsResponse:
    """Latest recorded run per job + scheduler liveness/next run times."""
    latest = await job_repo.latest_runs(session)

    # Scheduler state: the scheduler instance lives on app.state (lifespan).
    # Outside the app lifespan (tests, CLI) it is absent — report honestly.
    scheduler = getattr(request.app.state, "scheduler", None)
    scheduler_running = bool(scheduler is not None and scheduler.running)
    next_runs: dict[str, str | None] = {}
    if scheduler_running:
        for job in scheduler.get_jobs():
            trigger = getattr(job, "next_run_time", None)
            next_runs[job.name] = trigger.isoformat() if trigger else None

    # The scheduled name is the entrypoint; recorded names are the passes.
    names = sorted(set(latest) | set(next_runs) | {"nightly_ingestion"})
    jobs: list[JobStatus] = []
    for name in names:
        run = latest.get(name)
        jobs.append(
            JobStatus(
                job_name=name,
                last_run=(
                    JobRunInfo(**job_repo.summarize(run)) if run is not None else None
                ),
                next_run_at=next_runs.get(name),
            )
        )

    return DebugJobsResponse(
        scheduler_running=scheduler_running,
        jobs=jobs,
    )
