# Request-id structured logging.
#
# A contextvar carries the current request's id so any module (including the
# error envelope builders) can tag its output with it. The ASGI middleware logs
# one structured line per request (method, path, status, duration, request_id).

import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

access_logger = logging.getLogger("access")


def current_request_id() -> str:
    """Return the active request id (or '-' outside a request)."""
    return request_id_var.get()


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
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round(elapsed_ms, 1),
            },
        )
        request_id_var.reset(token)