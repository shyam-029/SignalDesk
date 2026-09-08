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
#  - GET /status  = public minimal liveness-equivalent in production; the full
#    readiness detail (db/scheduler/ingestion/llm) requires OPS_API_KEY.
#
# Hardening semantics (Phase 8):
#  - API docs (/docs, /redoc, /openapi.json) are disabled in production.
#  - /debug/jobs requires OPS_API_KEY (404 otherwise — no oracle).
#  - Per-IP rate limiting: LLM routes strictest, expensive fan-out medium,
#    plain reads highest. 429s use the standard error envelope + Retry-After.
#  - CORS in production requires explicit origins; "*" is rejected at startup.
#  - An unsafe (non-https) LLM_BASE_URL fails startup in production so
#    prompts can never travel over cleartext from a misconfigured deploy.

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import rate_limit
from app.auth import require_ops_key
from app.config import settings
from app.db import get_session
from app.errors import (
    NotFoundError,
    OpsNotConfigured,
    RateLimitError,
    ValidationError,
    _envelope,
    access_logger,
    generic_handler,
    http_exception_handler,
    insufficient_data_handler,
    no_peers_handler,
    not_found_handler,
    ops_not_configured_handler,
    rate_limit_handler,
    request_validation_handler,
    validation_handler,
)
from app.jobs import start_scheduler
from app.logging_utils import configure_logging, request_id_middleware
from app.repositories import job_runs as job_runs_repo
from app.routers import alpha, altman, ask, debug, etfs, explain, fundamentals, funds, history, market, news, scores, screener, stocks, technicals, valuation
from app.services.valuation import InsufficientDataError, NoPeersError

logger = logging.getLogger(__name__)

# Ingestion is considered stale when no run succeeded within this window
# (daily job + one full missed day of tolerance).
INGESTION_STALE_AFTER_SECONDS = 48 * 60 * 60

configure_logging()

# Phase 8 startup guards (fail closed, before the app serves traffic):
#  - Production refuses a non-https LLM gateway so prompts can never travel
#    over cleartext from a misconfigured deploy. Dev keeps localhost http
#    (stub servers in tests).
#  - Production refuses CORS "*" so browsers never get a wildcard policy.
if settings.is_production() and not settings.public_llm_base_url_ok():
    raise RuntimeError(
        "Refusing to start: LLM_BASE_URL must be https:// in production "
        f"(got {settings.llm_base_url!r})."
    )

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if settings.is_production() and "*" in _cors_origins:
    raise RuntimeError("Refusing to start: CORS_ORIGINS must not contain '*' in production.")

_docs_enabled = not settings.is_production()


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


app = FastAPI(
    title="SignalDesk API",
    version="0.1.0",
    lifespan=lifespan,
    # Phase 8: API docs are a dev/test tool. Disabled in production so the
    # schema (full route + model surface) is not served to scanners.
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
app.middleware("http")(request_id_middleware)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Per-IP fixed-window limits (Phase 8; in-process, see app/rate_limit.py).

    Bucket selection: LLM routes (ask/explain/alpha-explanation) strictest;
    screener + heavy fan-out routes medium; everything else default. The
    middleware runs OUTSIDE the error handlers' usual path, so a 429 is
    built directly with the envelope helper instead of raising.
    """
    path = request.url.path
    if request.method == "POST" and (path.endswith("/ask") or path.endswith("/explain")):
        bucket = "llm"
    elif path.endswith("/alpha/explanation"):
        bucket = "llm"
    elif (
        path.endswith("/screener")
        or path.endswith("/technicals/series")
        or path.endswith("/alpha/history")
        or path.endswith("/financials/history")
    ):
        bucket = "expensive"
    else:
        bucket = "default"
    try:
        rate_limit.check(request, bucket)
    except RateLimitError as exc:
        # The 429 short-circuits BEFORE request_id_middleware runs (the rate
        # limiter was registered later, so it is outermost), so mint the id
        # here and stamp it on both the envelope body and the header.
        # Also emit the access line here — the inner access logging never runs
        # for short-circuited responses, and 429s are operator-relevant.
        rid = uuid.uuid4().hex[:12]
        request.state.request_id = rid
        access_logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            path,
            429,
            0.0,
        )
        body = _envelope(
            "RATE_LIMITED", exc.message, {"retry_after": exc.retry_after}, request
        )
        body["error"]["request_id"] = rid
        response = JSONResponse(status_code=429, content=body)
        response.headers["Retry-After"] = str(exc.retry_after)
        response.headers["X-Request-ID"] = rid
        return response
    return await call_next(request)


@app.middleware("http")
async def production_docs_guard(request: Request, call_next):
    """Hide API docs in production even if the app object predates the env.

    The constructor already disables /docs, /redoc and /openapi.json when
    APP_ENV=production at import time (the real-deploy path). This runtime
    guard covers the same rule per request so the invariant holds regardless
    of import order — and so tests can exercise it by monkeypatching settings.
    """
    if settings.is_production() and request.url.path in (
        "/docs",
        "/redoc",
        "/openapi.json",
    ):
        rid = uuid.uuid4().hex[:12]
        request.state.request_id = rid
        body = _envelope(404, "Not found.", {}, request)
        body["error"]["request_id"] = rid
        response = JSONResponse(status_code=404, content=body)
        response.headers["X-Request-ID"] = rid
        return response
    return await call_next(request)

# Browser origins allowed to call the API (from CORS_ORIGINS in .env).
# Empty config disables CORS entirely (e.g. same-origin deployments).
# Production requires explicit origins ("*" fails startup above). Methods
# stay GET+POST (the app's actual methods); headers stay the two the app
# uses (JSON bodies + ops Bearer key). No credentials/cookies anywhere.
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

# Register the error-handling convention (own exceptions + FastAPI's native
# errors, all in the same envelope).
app.add_exception_handler(NotFoundError, not_found_handler)
app.add_exception_handler(OpsNotConfigured, ops_not_configured_handler)
app.add_exception_handler(RateLimitError, rate_limit_handler)
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
app.include_router(altman.router, prefix="/api/v1")
app.include_router(etfs.router, prefix="/api/v1")
app.include_router(funds.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(valuation.router, prefix="/api/v1")
app.include_router(screener.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(alpha.router, prefix="/api/v1")
app.include_router(technicals.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(ask.router, prefix="/api/v1")
app.include_router(explain.router, prefix="/api/v1")
# Operational endpoint: intentionally not under /api/v1 (not a public
# product API). Phase 8: requires OPS_API_KEY (the debug router declares the
# dependency; unauthenticated callers get a 404 with no oracle).
app.include_router(debug.router)


@app.get("/health")
async def health() -> dict:
    """Liveness check: the process is up. Dependency state lives on /status."""
    return {"status": "ok"}


@app.get("/status")
async def status_public() -> dict:
    """Minimal public status (Phase 8): liveness-equivalent, no ops detail.

    Public callers learn only that the process answers. Database state,
    scheduler state, ingestion timestamps and LLM configuration are exposed
    ONLY on /status/full with OPS_API_KEY.
    """
    return {"status": "ok"}


@app.get("/status/full")
async def status_full(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _authed: None = Depends(require_ops_key),
) -> dict:
    """Full readiness/operational status (OPS_API_KEY required).

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