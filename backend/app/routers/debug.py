# GET /debug/jobs — operational visibility into scheduled jobs (Phase 7).
#
# Answers: what jobs exist, when each last ran, did it succeed, how long did
# it take, how much was processed, what failed, when is the next run.
#
# Security boundary: this endpoint returns ONLY the curated job_runs fields
# (name/status/timestamps/counts/truncated error_summary) plus scheduler
# liveness. It never exposes environment variables, credentials, request
# payloads, or arbitrary database contents. Phase 8: requires OPS_API_KEY
# (404 otherwise — unauthenticated callers cannot confirm the path exists).
# In non-production without a configured key, local access stays open.

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_ops_key
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
async def debug_jobs(
    request: Request, session: SessionDep, _authed: None = Depends(require_ops_key)
) -> DebugJobsResponse:
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


# --- Client-IP header shape (work list item 15) -------------------------------
#
# The rate limiter keys on the first X-Forwarded-For entry, which a client
# can forge. Render does not document how its proxy forwards the client IP,
# so this operator-only probe MEASURES it without exposing any address:
# every answer is a count, a header NAME, or a yes/no comparison against
# values the caller itself supplied (X-Probe-Spoof: the fake address it put
# in X-Forwarded-For; X-Probe-Caller: its own public IP). No IP value is ever
# returned or logged.

_FORWARDING_HEADERS = (
    "x-forwarded-for",
    "x-real-ip",
    "true-client-ip",
    "cf-connecting-ip",
    "forwarded",
    "x-envoy-external-address",
)


class ClientIpShape(BaseModel):
    headers_present: list[str]
    x_forwarded_for_entries: int
    xff_first_is_spoof: bool
    xff_last_is_spoof: bool
    xff_first_is_caller: bool
    xff_last_is_caller: bool
    # header name -> does its value equal the caller's real IP / the spoof?
    header_is_caller: dict[str, bool]
    header_is_spoof: dict[str, bool]
    transport_peer_is_caller: bool


@router.get("/debug/client-ip-shape", response_model=ClientIpShape)
async def client_ip_shape(
    request: Request, _authed: None = Depends(require_ops_key)
) -> ClientIpShape:
    spoof = request.headers.get("x-probe-spoof", "").strip()
    caller = request.headers.get("x-probe-caller", "").strip()
    xff = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    present = [h for h in _FORWARDING_HEADERS if h in request.headers]

    def eq(value: str, expected: str) -> bool:
        return bool(expected) and value.strip() == expected

    singles = [h for h in present if h not in ("x-forwarded-for", "forwarded")]
    peer = getattr(getattr(request, "client", None), "host", "") or ""
    return ClientIpShape(
        headers_present=present,
        x_forwarded_for_entries=len(xff),
        xff_first_is_spoof=bool(xff) and eq(xff[0], spoof),
        xff_last_is_spoof=bool(xff) and eq(xff[-1], spoof),
        xff_first_is_caller=bool(xff) and eq(xff[0], caller),
        xff_last_is_caller=bool(xff) and eq(xff[-1], caller),
        header_is_caller={h: eq(request.headers[h], caller) for h in singles},
        header_is_spoof={h: eq(request.headers[h], spoof) for h in singles},
        transport_peer_is_caller=eq(peer, caller),
    )
