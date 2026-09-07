# Operational auth (Phase 8) — shared-secret Bearer dependencies.
#
# Concept: HTTP Bearer auth without user accounts. The client sends
# `Authorization: Bearer <key>`; we compare against the configured secret
# with secrets.compare_digest (constant-time, no timing oracle). There is no
# user table, no session, no JWT — SignalDesk stays a public read-only
# research app; these keys gate OPERATIONAL endpoints only (/debug/jobs,
# full /status) plus any future cron trigger.
#
# Security rules enforced here:
#  - Missing vs wrong credentials produce the IDENTICAL response (no oracle).
#  - The Authorization header value is never logged; configured keys are
#    never logged, never echoed, never placed in error detail.
#  - In non-production (APP_ENV != production) with no key configured, the
#    dependencies pass through so local dev/tests stay frictionless.
#  - In production without a configured key, everything fails CLOSED: every
#    request is denied (callers should additionally hide the route as 404).

import logging
import secrets

from fastapi import Request

from app.config import settings
from app.errors import NotFoundError, OpsNotConfigured

logger = logging.getLogger(__name__)


def _bearer_token(request: Request) -> str:
    """Extract the Bearer token, or "" when absent/malformed.

    Never logs the header value. Scheme comparison is case-insensitive
    per RFC 6750; anything else (Basic, missing, garbage) yields "".
    """
    header = request.headers.get("authorization", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        return ""
    return credentials.strip()


def _check_key(provided: str, expected: str) -> bool:
    """Constant-time comparison; False when either side is empty."""
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)


def _open_dev_mode() -> bool:
    """True when unauthenticated local access is allowed.

    Open only when NOT production AND no operational secret is configured.
    Setting a key in development immediately enforces it (lets developers
    exercise the production path locally).
    """
    return not settings.is_production() and not settings.ops_auth_configured()


async def require_ops_key(request: Request) -> None:
    """FastAPI dependency gating operational endpoints on OPS_API_KEY.

    Raises NotFoundError (→ 404 envelope) on failure so unauthenticated
    callers cannot confirm the operational path exists. Raises
    OpsNotConfigured when production has no key (main.py maps it to 404).
    """
    if _open_dev_mode():
        return
    expected = settings.ops_api_key
    if not expected:
        # Production without a key: fail closed, log key TYPE only.
        logger.warning("ops_auth denied reason=not_configured path=%s", request.url.path)
        raise OpsNotConfigured()
    if _check_key(_bearer_token(request), expected):
        return
    logger.warning("ops_auth denied path=%s", request.url.path)
    raise NotFoundError("Not found")


async def require_cron_key(request: Request) -> None:
    """FastAPI dependency gating cron triggers on CRON_API_KEY.

    Falls back to OPS_API_KEY when CRON_API_KEY is unset
    (see Settings.effective_cron_key). Same 404-on-failure semantics.
    """
    if _open_dev_mode():
        return
    expected = settings.effective_cron_key()
    if not expected:
        logger.warning("cron_auth denied reason=not_configured path=%s", request.url.path)
        raise OpsNotConfigured()
    if _check_key(_bearer_token(request), expected):
        return
    logger.warning("cron_auth denied path=%s", request.url.path)
    raise NotFoundError("Not found")
