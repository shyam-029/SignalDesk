# Request-id structured logging (Phase 2.5) + root logging (Phase 7).
#
# Concepts:
#  - ContextVar: carries the current request's id so any module (error
#    envelope builders, service loggers) can tag output with it.
#  - LogRecord factory: installs `request_id` onto EVERY log record at
#    creation time, so handlers anywhere in the tree (including test caplog)
#    see the field without per-logger plumbing. "-" outside a request.
#  - Root logger: configured once at app startup so logger.info/warning calls
#    in jobs/providers/services actually reach stderr (previously only the
#    access logger was configured and application logs were silently dropped).

import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

access_logger = logging.getLogger("access")

_configured = False


def current_request_id() -> str:
    """Return the active request id (or '-' outside a request)."""
    return request_id_var.get()


def _install_request_id_record_factory() -> None:
    """Stamp every LogRecord with the current request_id.

    setLogRecordFactory runs for every record at creation, so the attribute
    exists regardless of which logger/handler emits it. Explicit extra={...}
    values still override (access log passes its own request_id).
    """
    original = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = original(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return record

    logging.setLogRecordFactory(factory)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root + access loggers (idempotent).

    Root logger: structured key=value lines with timestamp, level, logger
    name and request_id for all application logs (jobs, providers, services).
    Access logger: one line per request (method/path/status/duration).
    """
    global _configured
    if _configured:
        return
    _configured = True

    _install_request_id_record_factory()

    fmt = "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"

    root_handler = logging.StreamHandler()
    root_handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(root_handler)

    access_handler = logging.StreamHandler()
    access_handler.setFormatter(logging.Formatter(fmt))
    access_logger.setLevel(logging.INFO)
    access_logger.addHandler(access_handler)
    access_logger.propagate = False


async def request_id_middleware(request: Request, call_next):
    """Assign a request_id, time the request, and emit a structured access log."""
    request_id = uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)
    request.state.request_id = request_id
    start = time.perf_counter()

    response = None
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        status = response.status_code if response is not None else 500
        access_logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            status,
            round(elapsed_ms, 1),
        )
        request_id_var.reset(token)
