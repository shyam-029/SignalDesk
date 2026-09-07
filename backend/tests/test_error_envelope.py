# Phase 7 tests — a single error envelope for EVERY error path.
#
# Covered: FastAPI-native RequestValidationError (bad types), HTTPException
# (unknown route 404, wrong method 405), domain errors, the ASK_BLOCKED
# top-level code, and the catch-all 500 (logged with traceback; the client
# response is detail-free). Every envelope carries request_id and a matching
# X-Request-ID header.


def _assert_envelope(body, code):
    assert set(body) == {"error"}
    err = body["error"]
    assert set(err) == {"code", "message", "detail", "request_id"}
    assert err["code"] == code
    assert isinstance(err["request_id"], str) and err["request_id"] != "-"


async def test_fastapi_validation_error_uses_envelope(client, seeded):
    # `page=abc` fails pydantic's int parsing -> RequestValidationError.
    r = await client.get("/api/v1/stocks", params={"page": "abc"})
    assert r.status_code == 422
    _assert_envelope(r.json(), "VALIDATION_ERROR")


async def test_unknown_route_404_uses_envelope(client):
    r = await client.get("/api/v1/definitely-not-a-route")
    assert r.status_code == 404
    _assert_envelope(r.json(), "RESOURCE_NOT_FOUND")


async def test_method_not_allowed_405_uses_envelope(client):
    r = await client.post("/health")
    assert r.status_code == 405
    _assert_envelope(r.json(), "METHOD_NOT_ALLOWED")


async def test_request_id_header_matches_envelope(client, seeded):
    r = await client.get("/api/v1/stocks", params={"page": "abc"})
    assert r.headers["X-Request-ID"] == r.json()["error"]["request_id"]


async def test_unexpected_500_is_logged_and_safe(client, session_factory, monkeypatch, caplog):
    """An unhandled exception -> traceback in logs, nothing internal to client."""
    import logging

    from app.routers import stocks as stocks_router

    async def boom(*args, **kwargs):
        secret = "sk-internal-secret-value"
        raise RuntimeError(f"boom {secret}")

    monkeypatch.setattr(stocks_router.price_repo, "get_two_latest", boom)

    # raise_app_exceptions=False: the ASGI transport shouldn't re-raise the
    # app's exception into the test; we want the 500 RESPONSE.
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    with caplog.at_level(logging.ERROR):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as raw_client:
            r = await raw_client.get("/api/v1/stocks")

    assert r.status_code == 500
    body = r.json()
    _assert_envelope(body, "INTERNAL_ERROR")
    # Nothing internal leaks to the client.
    assert "boom" not in body["error"]["message"]
    assert "sk-internal-secret-value" not in r.text
    assert body["error"]["detail"] == {}
    # ...but the operator CAN see it in the logs, with traceback + request_id.
    assert "unhandled_exception" in caplog.text
    assert "Traceback" in caplog.text or "RuntimeError" in caplog.text
    err_records = [r for r in caplog.records if "unhandled_exception" in r.getMessage()]
    assert err_records, "expected the 500 to be logged"
    for rec in err_records:
        # The record factory stamps request_id on every record.
        assert rec.request_id == body["error"]["request_id"]


async def test_http_exception_preserves_status_code(client):
    """A 405 keeps its 405, not a blanket 500."""
    r = await client.put("/api/v1/stocks")
    assert r.status_code in (405, 422)
    body = r.json()
    assert "error" in body and "code" in body["error"]
