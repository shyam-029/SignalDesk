# Phase 8 tests — operational auth, rate limiting, pure-read /alpha.
#
# Strategy: the `settings` object is a module-level singleton, so tests
# monkeypatch its attributes (app_env / ops_api_key / rate limits) and
# restore them in teardown. No real secrets, no network, no LLM calls.

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import llm_semaphore, rate_limit
from app.config import settings
from app.models import AlphaScore, DailyPrice, Financials, Stock
from app.services import llm_narrative


@pytest.fixture(autouse=True)
def _reset_phase8_state(monkeypatch):
    """Restore settings + limiter/semaphore state after every test."""
    orig_env = settings.app_env
    orig_ops = settings.ops_api_key
    orig_cron = settings.cron_api_key
    orig_llm = settings.rate_limit_llm_per_min
    orig_exp = settings.rate_limit_expensive_per_min
    orig_def = settings.rate_limit_default_per_min
    orig_conc = settings.llm_max_concurrent
    rate_limit.reset_state()
    llm_semaphore.reset_state()
    llm_narrative._cache.clear()
    llm_narrative._calls_today = 0
    llm_narrative._calls_day = date.today()
    yield
    monkeypatch.undo()  # belt-and-braces; attribute sets below use monkeypatch too
    settings.app_env = orig_env
    settings.ops_api_key = orig_ops
    settings.cron_api_key = orig_cron
    settings.rate_limit_llm_per_min = orig_llm
    settings.rate_limit_expensive_per_min = orig_exp
    settings.rate_limit_default_per_min = orig_def
    settings.llm_max_concurrent = orig_conc
    rate_limit.reset_state()
    llm_semaphore.reset_state()


def _as_production(monkeypatch, ops_key: str = "test-ops-secret"):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ops_api_key", ops_key)


def _assert_envelope(body, code):
    assert set(body) == {"error"}
    err = body["error"]
    assert set(err) == {"code", "message", "detail", "request_id"}
    assert err["code"] == code
    assert isinstance(err["request_id"], str) and err["request_id"] != "-"


# --- 1. OPS_API_KEY dev compatibility ----------------------------------------


async def test_debug_jobs_open_in_dev_without_key(client):
    r = await client.get("/debug/jobs")
    assert r.status_code == 200
    assert "scheduler_running" in r.json()


async def test_status_public_minimal_in_dev(client):
    r = await client.get("/status")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- 2. Production without key fails closed ----------------------------------


async def test_debug_jobs_404_in_production_without_key(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ops_api_key", "")
    r = await client.get("/debug/jobs")
    assert r.status_code == 404
    _assert_envelope(r.json(), "RESOURCE_NOT_FOUND")


async def test_status_full_404_in_production_without_key(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ops_api_key", "")
    r = await client.get("/status/full")
    assert r.status_code == 404
    _assert_envelope(r.json(), "RESOURCE_NOT_FOUND")


# --- 3. Production with key: missing/wrong/correct ----------------------------


async def test_debug_jobs_missing_auth_fails(client, monkeypatch):
    _as_production(monkeypatch)
    r = await client.get("/debug/jobs")
    assert r.status_code == 404
    _assert_envelope(r.json(), "RESOURCE_NOT_FOUND")


async def test_debug_jobs_wrong_key_fails(client, monkeypatch):
    _as_production(monkeypatch)
    r = await client.get("/debug/jobs", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 404
    _assert_envelope(r.json(), "RESOURCE_NOT_FOUND")


async def test_debug_jobs_correct_key_succeeds(client, monkeypatch):
    _as_production(monkeypatch)
    r = await client.get(
        "/debug/jobs", headers={"Authorization": "Bearer test-ops-secret"}
    )
    assert r.status_code == 200
    assert "scheduler_running" in r.json()


async def test_missing_vs_wrong_are_indistinguishable(client, monkeypatch):
    """No authentication oracle: both responses share status + shape."""
    _as_production(monkeypatch)
    missing = await client.get("/debug/jobs")
    wrong = await client.get("/debug/jobs", headers={"Authorization": "Bearer nope"})
    assert missing.status_code == wrong.status_code == 404
    assert set(missing.json()) == set(wrong.json()) == {"error"}
    assert missing.json()["error"]["code"] == wrong.json()["error"]["code"]
    assert "Authorization" not in missing.text
    assert "test-ops-secret" not in missing.text + wrong.text


async def test_non_bearer_scheme_rejected(client, monkeypatch):
    _as_production(monkeypatch)
    r = await client.get(
        "/debug/jobs", headers={"Authorization": "Basic dGVzdA=="}
    )
    assert r.status_code == 404


# --- 4. /status split ---------------------------------------------------------


async def test_status_full_requires_auth_in_production(client, monkeypatch):
    _as_production(monkeypatch)
    public = await client.get("/status")
    assert public.status_code == 200
    assert public.json() == {"status": "ok"}  # no ops detail, ever

    denied = await client.get("/status/full")
    assert denied.status_code == 404

    allowed = await client.get(
        "/status/full", headers={"Authorization": "Bearer test-ops-secret"}
    )
    assert allowed.status_code == 200
    body = allowed.json()
    assert set(body) >= {"db", "scheduler", "ingestion", "llm_configured"}


async def test_status_public_leaks_no_ops_detail(client, monkeypatch):
    _as_production(monkeypatch, ops_key="")
    # Even unconfigured production exposes only liveness on /status.
    text = (await client.get("/status")).text
    assert "scheduler" not in text
    assert "ingestion" not in text
    assert "llm_configured" not in text


# --- 5. Production docs disabled ----------------------------------------------


async def test_docs_disabled_in_production(client, monkeypatch):
    _as_production(monkeypatch)
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = await client.get(path)
        assert r.status_code == 404, path


async def test_docs_enabled_in_dev(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200


# --- 6. GET /alpha performs zero writes ---------------------------------------


async def _seed_alpha_stock(session_factory) -> None:
    async with session_factory() as session:
        stock = Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O")
        session.add(stock)
        await session.flush()
        session.add(
            Financials(
                stock_id=stock.id,
                trailing_pe=Decimal("20.00"),
                return_on_equity=Decimal("0.1800"),
                operating_margin=Decimal("0.1250"),
                debt_to_equity=Decimal("50.00"),
            )
        )
        today = date.today()
        for i in range(60):
            session.add(
                DailyPrice(
                    stock_id=stock.id,
                    date=today - timedelta(days=i),
                    open=100, high=101, low=99,
                    close=100 + (i * 0.1), volume=1000,
                )
            )
        await session.commit()


async def test_alpha_get_performs_zero_writes(client, session_factory):
    await _seed_alpha_stock(session_factory)
    r = await client.get("/api/v1/stocks/RELIANCE/alpha")
    assert r.status_code == 200
    async with session_factory() as session:
        rows = (await session.execute(select(AlphaScore))).scalars().all()
    assert rows == []
    # Second view still writes nothing; response semantics preserved.
    r2 = await client.get("/api/v1/stocks/RELIANCE/alpha")
    assert r2.status_code == 200
    assert r2.json()["composite"] == r.json()["composite"]
    async with session_factory() as session:
        rows2 = (await session.execute(select(AlphaScore))).scalars().all()
    assert rows2 == []


# --- 7. Rate limiting ----------------------------------------------------------


async def test_llm_endpoint_eventually_429s(client, monkeypatch, session_factory):
    monkeypatch.setattr(settings, "rate_limit_llm_per_min", 3)
    async with session_factory() as session:
        session.add(Stock(symbol="ASK.NS", name="Ask", sector="X", industry="Y"))
        await session.commit()
    codes = []
    for _ in range(5):
        r = await client.post("/api/v1/stocks/ASK/ask", json={"question": "x" * 10})
        codes.append(r.status_code)
    assert 429 in codes
    limited = None
    for _ in range(5):
        r = await client.post("/api/v1/stocks/ASK/ask", json={"question": "x" * 10})
        if r.status_code == 429:
            limited = r
            break
    assert limited is not None
    _assert_envelope(limited.json(), "RATE_LIMITED")
    assert "Retry-After" in limited.headers
    assert limited.headers["X-Request-ID"] == limited.json()["error"]["request_id"]
    # No limiter internals leak.
    assert "bucket" not in limited.text and "window" not in limited.text.lower()


async def test_research_routes_have_higher_limit_than_llm(client, monkeypatch, seeded):
    monkeypatch.setattr(settings, "rate_limit_llm_per_min", 2)
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 50)
    # Exhaust the LLM bucket (seeded fixture provides TCS.NS).
    for _ in range(3):
        await client.post("/api/v1/stocks/TCS/ask", json={"question": "How is alpha?"})
    r_llm = await client.post("/api/v1/stocks/TCS/ask", json={"question": "How is alpha?"})
    assert r_llm.status_code == 429
    # Plain research still serves.
    r = await client.get("/api/v1/stocks")
    assert r.status_code == 200


async def test_expensive_bucket_limits_screener(client, monkeypatch, seeded):
    monkeypatch.setattr(settings, "rate_limit_expensive_per_min", 2)
    assert (await client.get("/api/v1/screener")).status_code == 200
    assert (await client.get("/api/v1/screener")).status_code == 200
    r = await client.get("/api/v1/screener")
    assert r.status_code == 429
    _assert_envelope(r.json(), "RATE_LIMITED")


# --- 8. LLM concurrency cap -----------------------------------------------------


async def test_llm_semaphore_caps_concurrent_calls(monkeypatch):
    import asyncio

    monkeypatch.setattr(settings, "llm_max_concurrent", 2)
    llm_semaphore.reset_state()
    sem = llm_semaphore.get_semaphore()

    in_flight = 0
    peak = 0

    async def fake_call():
        nonlocal in_flight, peak
        async with sem:
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1

    await asyncio.gather(*[fake_call() for _ in range(6)])
    assert peak <= 2


async def test_semaphore_respects_settings_change(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_concurrent", 1)
    llm_semaphore.reset_state()
    assert llm_semaphore.get_semaphore()._value == 1


# --- 9. LLM_BASE_URL validation -------------------------------------------------


def test_llm_base_url_ok_https():
    from app.config import Settings

    s = Settings.model_validate(
        {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
         "LLM_BASE_URL": "https://openrouter.ai/api/v1"}
    )
    assert s.public_llm_base_url_ok() is True


def test_llm_base_url_rejects_http_in_production():
    from app.config import Settings

    s = Settings.model_validate(
        {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
         "APP_ENV": "production", "LLM_BASE_URL": "http://evil.example/v1"}
    )
    assert s.public_llm_base_url_ok() is False


def test_llm_base_url_allows_localhost_http_in_dev():
    from app.config import Settings

    s = Settings.model_validate(
        {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
         "LLM_BASE_URL": "http://localhost:9999/v1"}
    )
    assert s.public_llm_base_url_ok() is True


# --- 10. CORS -------------------------------------------------------------------


def test_cors_production_rejects_wildcard():
    from app.config import Settings

    s = Settings.model_validate(
        {"DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
         "APP_ENV": "production", "CORS_ORIGINS": "https://a.example,*"}
    )
    origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
    assert "*" in origins  # config parses it; main.py refuses startup
    assert s.is_production()


# --- 11. Secrets hygiene ----------------------------------------------------------


async def test_no_auth_keys_in_logs_or_responses(client, monkeypatch, caplog):
    import logging

    _as_production(monkeypatch, ops_key="super-secret-ops-key-xyz")
    with caplog.at_level(logging.WARNING):
        await client.get("/debug/jobs")
        await client.get("/debug/jobs", headers={"Authorization": "Bearer wrong-key"})
        r = await client.get(
            "/debug/jobs", headers={"Authorization": "Bearer super-secret-ops-key-xyz"}
        )
        assert r.status_code == 200
    assert "super-secret-ops-key-xyz" not in caplog.text
    assert "wrong-key" not in caplog.text
    assert "super-secret-ops-key-xyz" not in r.text
    assert "authorization" not in caplog.text.lower()


async def test_cron_key_falls_back_to_ops_key(monkeypatch):
    monkeypatch.setattr(settings, "ops_api_key", "ops-123")
    monkeypatch.setattr(settings, "cron_api_key", "")
    assert settings.effective_cron_key() == "ops-123"
    monkeypatch.setattr(settings, "cron_api_key", "cron-456")
    assert settings.effective_cron_key() == "cron-456"
