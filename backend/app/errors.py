# Error handling convention (PLANNING §11).
#
# Concepts:
#  - Custom exceptions: distinct types for distinct failure modes. Routers just
#    `raise` them; central handlers in main.py convert them to HTTP responses.
#  - Error envelope: every error returns the SAME JSON shape so clients can
#    parse consistently: { "error": { code, message, detail, request_id } }.
#  - FastAPI's own RequestValidationError / HTTPException are also wrapped in
#    the envelope so no error path leaks a different shape.

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.logging_utils import current_request_id, request_id_var
from app.services.valuation import InsufficientDataError, NoPeersError

logger = logging.getLogger(__name__)

# --- Custom exceptions (map to HTTP status codes) ---


class NotFoundError(Exception):
    """Resource does not exist. Maps to 404."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class ValidationError(Exception):
    """Request validation failed. Maps to 422.

    `code` allows a more specific machine-readable error code than the
    generic VALIDATION_ERROR (e.g. ASK_BLOCKED for provider safety filters).
    """

    def __init__(
        self,
        message: str,
        detail: dict | None = None,
        code: str = "VALIDATION_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}
        self.code = code


# --- Helpers to build the envelope ---


def _request_id(request: Request | None = None) -> str:
    """Request id for the envelope.

    Prefers the ContextVar; falls back to request.state (the catch-all 500
    handler runs in ServerErrorMiddleware, OUTSIDE the request-id
    middleware, where the ContextVar has already been reset).
    """
    rid = current_request_id()
    if rid == "-" and request is not None:
        rid = getattr(request.state, "request_id", "-")
    return rid


def _envelope(code: str, message: str, detail: dict, request: Request | None = None) -> dict:
    """Build the standard error envelope body, tagged with the request id."""
    return {
        "error": {
            "code": code,
            "message": message,
            "detail": detail,
            "request_id": _request_id(request),
        }
    }


def _json_response(
    status: int, code: str, message: str, detail: dict, request: Request | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status, content=_envelope(code, message, detail, request)
    )


# --- Exception handlers (registered in main.py) ---


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Convert NotFoundError into a 404 with the standard envelope."""
    return _json_response(404, "RESOURCE_NOT_FOUND", exc.message, exc.detail)


async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Convert ValidationError into a 422 with the standard envelope."""
    return _json_response(422, exc.code, exc.message, exc.detail)


async def no_peers_handler(request: Request, exc: NoPeersError) -> JSONResponse:
    """Convert NoPeersError (empty peer set) into a 409 with the envelope."""
    return _json_response(409, "NO_PEERS", str(exc), {})


async def insufficient_data_handler(
    request: Request, exc: InsufficientDataError
) -> JSONResponse:
    """Convert InsufficientDataError into a 422 with the envelope."""
    return _json_response(422, "INSUFFICIENT_DATA", str(exc), {})


async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """FastAPI request parsing errors (bad types, missing params) -> 422 envelope.

    The detail lists which fields failed, never raw request payloads.
    """
    fields = sorted({str(err.get("loc", [""])[-1]) for err in exc.errors()})
    return _json_response(
        422,
        "VALIDATION_ERROR",
        "Request failed validation.",
        {"fields": fields},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """FastAPI/Starlette HTTPExceptions (404 unknown route, 405, ...) -> envelope."""
    code_by_status = {
        404: "RESOURCE_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
    }
    code = code_by_status.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = str(exc.detail) if exc.detail else "Request failed."
    return _json_response(exc.status_code, code, message, {})


async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the exception; return a clean, detail-free 500 envelope."""
    request_id = _request_id(request)
    # Rebind the ContextVar for this log call: the catch-all runs outside the
    # request-id middleware, where the ContextVar is already reset.
    token = request_id_var.set(request_id)
    try:
        logger.exception(
            "unhandled_exception request_id=%s path=%s method=%s error_type=%s",
            request_id,
            request.url.path,
            request.method,
            type(exc).__name__,
        )
    finally:
        request_id_var.reset(token)
    return _json_response(
        500, "INTERNAL_ERROR", "An unexpected error occurred.", {}, request
    )
