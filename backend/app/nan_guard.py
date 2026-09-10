# API-boundary NaN guard (incident 2026-09-09, defense-in-depth layer).
#
# The diagnosed leak (yfinance ex-dividend rows → NaN OHLC bars) is closed at
# the provider and the upserts, but any *future* path that lets a non-finite
# float reach a response must not serialize as an invalid JSON literal.
# Two failure shapes exist on this stack:
#   - pydantic response_model routes: pydantic v2 already renders NaN as
#     null (honest but silent),
#   - dict-returning routes: FastAPI's JSONResponse uses json.dumps with
#     allow_nan=True, emitting the literal NaN/-Infinity, which browsers'
#     JSON.parse REJECTS — the frontend sees an unparseable body.
# This middleware scrubs non-finite floats (NaN/±Infinity) to null in every
# JSON response and logs when it fires, so a new leak is visible in the logs
# instead of corrupting clients. Normal responses take a byte-pass-through
# fast path (single isinstance check on the raw body).

import json
import logging
import math

from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_NON_FINITE_LITERALS = (b"NaN", b"Infinity")


def scrub_non_finite(value):
    """Recursively replace non-finite floats (NaN/±inf) with None.

    A non-computable metric presented as null matches the app's honest-null
    convention; an invalid JSON literal presented to a browser is a fault.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: scrub_non_finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_non_finite(v) for v in value]
    return value


def _rebuild(response: Response, body: bytes, media_type: str) -> Response:
    """Clone a response around new body bytes, dropping the stale length."""
    headers = {
        k: v for k, v in response.headers.items() if k.lower() != "content-length"
    }
    return Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        media_type=media_type,
    )


async def nan_guard_middleware(request: Request, call_next):
    """Scrub NaN/Infinity literals out of JSON responses (defense-in-depth)."""
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("application/json"):
        return response

    body = b"".join([chunk async for chunk in response.body_iterator])
    if not body:
        return _rebuild(response, body, content_type)

    if not any(marker in body for marker in _NON_FINITE_LITERALS):
        # Fast path: already strict JSON — pass the bytes through untouched.
        return _rebuild(response, body, content_type)

    # parse_constant catches the NaN/Infinity/-Infinity literals; the
    # recursive scrub then catches overflow floats json.loads can produce
    # from huge exponents (e.g. 1e400) without hitting parse_constant.
    data = json.loads(body, parse_constant=lambda _name: None)
    data = scrub_non_finite(data)
    clean = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
    logger.warning(
        "nan_scrub path=%s status=%d replaced non-finite JSON literals",
        request.url.path,
        response.status_code,
    )
    return _rebuild(response, clean, content_type)
