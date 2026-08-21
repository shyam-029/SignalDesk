# Error handling convention (PLANNING §11).
#
# Concepts:
#  - Custom exceptions: distinct types for distinct failure modes. Routers just
#    `raise` them; central handlers in main.py convert them to HTTP responses.
#  - Error envelope: every error returns the SAME JSON shape so clients can
#    parse consistently: { "error": { code, message, detail } }.

from fastapi import Request
from fastapi.responses import JSONResponse

from app.logging_utils import current_request_id
from app.services.valuation import InsufficientDataError, NoPeersError

# --- Custom exceptions (map to HTTP status codes) ---


class NotFoundError(Exception):
    """Resource does not exist. Maps to 404."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class ValidationError(Exception):
    """Request validation failed. Maps to 422."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


# --- Helpers to build the envelope ---


def _envelope(code: str, message: str, detail: dict) -> dict:
    """Build the standard error envelope body, tagged with the request id."""
    return {
        "error": {
            "code": code,
            "message": message,
            "detail": detail,
            "request_id": current_request_id(),
        }
    }


def _json_response(status: int, code: str, message: str, detail: dict) -> JSONResponse:
    return JSONResponse(
        status_code=status, content=_envelope(code, message, detail)
    )


# --- Exception handlers (registered in main.py) ---


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Convert NotFoundError into a 404 with the standard envelope."""
    return _json_response(404, "RESOURCE_NOT_FOUND", exc.message, exc.detail)


async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Convert ValidationError into a 422 with the standard envelope."""
    return _json_response(422, "VALIDATION_ERROR", exc.message, exc.detail)


async def no_peers_handler(request: Request, exc: NoPeersError) -> JSONResponse:
    """Convert NoPeersError (empty peer set) into a 409 with the envelope."""
    return _json_response(409, "NO_PEERS", str(exc), {})


async def insufficient_data_handler(
    request: Request, exc: InsufficientDataError
) -> JSONResponse:
    """Convert InsufficientDataError into a 422 with the envelope."""
    return _json_response(422, "INSUFFICIENT_DATA", str(exc), {})


async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: any unhandled error becomes a clean 500 envelope."""
    return _json_response(
        500, "INTERNAL_ERROR", "An unexpected error occurred.", {}
    )