# FastAPI application entry point — assembles the app, handlers, and scheduler.
#
# Concepts:
#  - lifespan: a context manager that runs startup/shutdown code (the modern
#    replacement for the deprecated on_event). We start the background scheduler
#    on startup and shut it down on exit.
#  - include_router: mounts the routers under the /api/v1 prefix (debug router
#    is operational, mounted at the root without the API version).
#  - add_exception_handler: registers our custom error handlers so routers can
#    just raise custom exceptions; FastAPI's own validation/HTTP errors are
#    wrapped in the same envelope.
#
# Health semantics (Phase 7):
#  - GET /health  = pure liveness ("the process is alive"). Always 200.
#  - GET /status  = readiness: DB reachable, scheduler alive, ingestion fresh,
#    LLM configured. Optional components degrade the status, never crash it.

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.errors import (
    NotFoundError,
    ValidationError,
    generic_handler,
    http_exception_handler,
    insufficient_data_handler,
    no_peers_handler,
    not_found_handler,
    request_validation_handler,
    validation_handler,
)
from app.jobs import start_scheduler
from app.logging_utils import configure_logging, request_id_middleware
from app.repositories import job_runs as job_runs_repo
from app.routers import alpha, ask, debug, explain, fundamentals, history, news, scores, screener, stocks, technicals, valuation
from app.services.valuation import InsufficientDataError, NoPeersError

logger = logging.getLogger(__name__)

# Ingestion is considered stale when no run succeeded within this window
# (daily job + one full missed day of tolerance).
INGESTION_STALE_AFTER_SECONDS = 48 * 60 * 60

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the background scheduler on startup; stop it on shutdown.

    The scheduler handle is stored on app.state so operational endpoints
    (/debug/jobs, /status) can report scheduler liveness.
    """
    scheduler = start_scheduler()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title="SignalDesk API", version="0.1.0", lifespan=lifespan)
app.middleware("http")(request_id_middleware)

# Browser origins allowed to call the API (from CORS_ORIGINS in .env).
# Empty config disables CORS entirely (e.g. same-origin deployments).
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

# Register the error-handling convention (own exceptions + FastAPI's native
# errors, all in the same envelope).
app.add_exception_handler(NotFoundError, not_found_handler)
app.add_exception_handler(ValidationError, validation_handler)
app.add_exception_handler(NoPeersError, no_peers_handler)
app.add_exception_handler(InsufficientDataError, insufficient_data_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)
# Starlette's HTTPException base covers routing 404s/405s AND FastAPI's own
# HTTPException subclass.
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_handler)

# Mount API routes.
app.include_router(stocks.router, prefix="/api/v1")
app.include_router(fundamentals.router, prefix="/api/v1")
app.include_router(scores.router, prefix="/api/v1")
app.include_router(valuation.router, prefix="/api/v1")
app.include_router(screener.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(alpha.router, prefix="/api/v1")
app.include_router(technicals.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(ask.router, prefix="/api/v1")
app.include_router(explain.router, prefix="/api/v1")
# Operational endpoint: intentionally not under /api/v1 (not a public
# product API). Unauthenticated while the deployment is local-only;
# restrict it before any public deployment (see PLANNING D90).
app.include_router(debug.router)


@app.get("/health")
async def health() -> dict:
    """Liveness check: the process is up. Dependency state lives on /status."""
    return {"status": "ok"}


@app.get("/status")
async def status(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict:
    """Readiness/operational status.

    Each check is independent and fault-tolerant: an unavailable component
    degrades the overall state instead of failing the request.
      db          - reachable via a trivial SELECT 1
      scheduler   - the APScheduler background scheduler is running
      ingestion   - last recorded job_run, plus `stale` when the last
                    successful run is older than INGESTION_STALE_AFTER_SECONDS
      llm         - configured as a boolean (never the key or model endpoint)
    """
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("status_check db=down error=%s", type(exc).__name__)

    scheduler = getattr(app.state, "scheduler", None)
    scheduler_running = bool(scheduler is not None and scheduler.running)

    last_ingestion_at = None
    ingestion_stale: bool | None = None
    if db_ok:
        try:
            last_run = await job_runs_repo.last_successful_run(
                session, job_name="ingest_prices"
            )
        except Exception as exc:
            logger.warning(
                "status_check job_runs_unavailable error=%s", type(exc).__name__
            )
            last_run = None
        if last_run is not None and last_run.finished_at is not None:
            last_ingestion_at = last_run.finished_at.isoformat()
            age = datetime.now(timezone.utc) - last_run.finished_at
            ingestion_stale = age.total_seconds() > INGESTION_STALE_AFTER_SECONDS
        elif last_run is None:
            ingestion_stale = None  # never run: unknown, not "stale"

    degraded = not db_ok or not scheduler_running or ingestion_stale is True
    return {
        "status": "degraded" if degraded else "ok",
        "db": "up" if db_ok else "down",
        "scheduler": "running" if scheduler_running else "stopped",
        "ingestion": {
            "last_success_at": last_ingestion_at,
            "stale": ingestion_stale,
            "stale_after_seconds": INGESTION_STALE_AFTER_SECONDS,
        },
        "llm_configured": bool(settings.llm_api_key and settings.llm_model),
    }