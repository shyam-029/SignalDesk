# FastAPI application entry point — assembles the app, handlers, and scheduler.
#
# Concepts:
#  - lifespan: a context manager that runs startup/shutdown code (the modern
#    replacement for the deprecated on_event). We start the background scheduler
#    on startup and shut it down on exit.
#  - include_router: mounts the stocks router under the /api/v1 prefix.
#  - add_exception_handler: registers our custom error handlers so routers can
#    just raise custom exceptions.

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.errors import (
    NotFoundError,
    ValidationError,
    generic_handler,
    insufficient_data_handler,
    no_peers_handler,
    not_found_handler,
    validation_handler,
)
from app.jobs import start_scheduler
from app.logging_utils import request_id_middleware
from app.routers import alpha, fundamentals, news, scores, screener, stocks, valuation
from app.services.valuation import InsufficientDataError, NoPeersError


def _configure_logging() -> None:
    """Emit structured key=value log lines so request ids/latency are greppable."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s method=%(method)s path=%(path)s "
            "status=%(status)s duration_ms=%(duration_ms)s %(message)s"
        )
    )
    access = logging.getLogger("access")
    access.setLevel(logging.INFO)
    access.addHandler(handler)
    access.propagate = False


_configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the background scheduler on startup; stop it on shutdown."""
    scheduler = start_scheduler()
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title="SignalDesk API", version="0.1.0", lifespan=lifespan)
app.middleware("http")(request_id_middleware)

# Register the error-handling convention.
app.add_exception_handler(NotFoundError, not_found_handler)
app.add_exception_handler(ValidationError, validation_handler)
app.add_exception_handler(NoPeersError, no_peers_handler)
app.add_exception_handler(InsufficientDataError, insufficient_data_handler)
app.add_exception_handler(Exception, generic_handler)

# Mount API routes.
app.include_router(stocks.router, prefix="/api/v1")
app.include_router(fundamentals.router, prefix="/api/v1")
app.include_router(scores.router, prefix="/api/v1")
app.include_router(valuation.router, prefix="/api/v1")
app.include_router(screener.router, prefix="/api/v1")
app.include_router(news.router, prefix="/api/v1")
app.include_router(alpha.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}