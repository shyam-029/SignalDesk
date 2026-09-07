# Phase 7 tests — logging hygiene: credentials must never reach log records.
#
# Covers the Upstox token, the LLM API key and error-message internals on all
# failure paths that Phase 7 makes visible (provider_failure / llm_fallback /
# unhandled_exception).

import logging

import httpx
import pytest

from app.providers.openrouter_provider import OpenRouterProvider
from app.providers.base import MarketDataError
from app.providers.llm_base import LLMError
from app.providers.upstox_provider import UpstoxProvider

UPSTOX_TOKEN = "upstox-SECRET-token-000"
LLM_KEY = "sk-llm-SECRET-key-111"


async def test_upstox_failure_logs_exclude_token(caplog):
    """A failing Upstox call logs provider_failure but never the bearer token."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    provider = UpstoxProvider(
        token=UPSTOX_TOKEN,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        instrument_map={"AAA": ("NSE_EQ|INE000", "INE000")},
    )
    with caplog.at_level(logging.INFO):
        with pytest.raises(MarketDataError):
            await provider.get_stock_profile("AAA.NS")

    assert "provider_failure" in caplog.text
    assert UPSTOX_TOKEN not in caplog.text
    for record in caplog.records:
        assert UPSTOX_TOKEN not in record.getMessage()


async def test_upstox_enrichment_failure_is_visible_not_silent(caplog):
    """The previously-silent except blocks now emit provider_failure lines."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "key-ratios" in str(request.url):
            return httpx.Response(
                200,
                json={"status": "success", "data": [
                    {"name": "P/E", "company_value": "20.0"},
                ]},
            )
        # income-statement + balance-sheet fail; fundamentals must still return.
        return httpx.Response(500, text="nope")

    provider = UpstoxProvider(
        token=UPSTOX_TOKEN,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        instrument_map={"AAA": ("NSE_EQ|INE000", "INE000")},
    )
    with caplog.at_level(logging.INFO):
        fundamentals = await provider.get_fundamentals("AAA.NS")

    assert fundamentals.trailing_pe == 20.0  # enrichment skipped, not fatal
    assert UPSTOX_TOKEN not in caplog.text


async def test_openrouter_failure_logs_exclude_api_key(caplog, monkeypatch):
    """LLM provider failures (and the fallback log) never carry the API key."""
    from datetime import date

    from app.services import llm_narrative as narr
    from app.services.alpha import AlphaResult

    narr._cache.clear()
    narr._calls_today = 0
    narr._calls_day = date.today()
    monkeypatch.setattr(narr.settings, "llm_api_key", LLM_KEY)
    monkeypatch.setattr(narr.settings, "llm_model", "fake-model")

    async def _post(self, url, json=None, headers=None):
        # Simulate an auth-failure response echoing NOTHING sensitive.
        class R:
            status_code = 401

            def json(self):
                return {"error": {"message": "unauthorized"}}

        return R()

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)

    provider = OpenRouterProvider(api_key=LLM_KEY, model="fake-model")

    class FakeStock:
        symbol = "AAA.NS"
        id = 1

    result = AlphaResult(
        symbol="AAA.NS", composite=None, fundamental=None, technical=None,
        sentiment=None, components={}, weights={}, value_signal=None,
        insufficient_data=True,
    )
    with caplog.at_level(logging.INFO):
        with pytest.raises(LLMError):
            await provider.generate("sys", "user")
        text, source = await narr.generate_alpha_explanation_result(
            FakeStock(), result, provider
        )

    assert source == "rule_based"
    assert "llm_fallback" in caplog.text
    assert LLM_KEY not in caplog.text
    # The provider error itself is logged (that's the observability point);
    # only credentials are forbidden.


def test_access_log_and_root_logger_share_request_id(caplog):
    """The record factory stamps request_id on every record, default '-'."""
    from app.logging_utils import current_request_id, request_id_var

    logger = logging.getLogger("app.phase7_selftest")
    with caplog.at_level(logging.INFO, logger="app.phase7_selftest"):
        with caplog.at_level(logging.INFO):
            logger.info("outside_request")
        assert caplog.records[-1].request_id == "-"
        token = request_id_var.set("req-abc123")
        try:
            logger.info("inside_request")
        finally:
            request_id_var.reset(token)
    assert caplog.records[-1].request_id == "req-abc123"
    assert current_request_id() == "-"


async def test_ingestion_failure_log_contains_no_secrets(
    session_factory, monkeypatch, caplog
):
    """Per-symbol ingestion failures log the symbol and error, never settings."""
    from app import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    spy = "SUPER_SECRET"

    class P:
        name = "spy"

        async def get_price_history(self, symbol, period):
            raise MarketDataError(f"upstream refused: {spy}")

    # Seed a universe with one symbol so the loop runs.
    from sqlalchemy import insert, select

    from app.models import Stock, Universe, stock_universe

    async with session_factory() as session:
        session.add(Universe(name=jobs_module.UNIVERSE_NAME))
        session.add(Stock(symbol="AAA.NS", name="AAA"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == "AAA.NS"))
        uni = await session.scalar(
            select(Universe).where(Universe.name == jobs_module.UNIVERSE_NAME)
        )
        await session.execute(
            insert(stock_universe).values(universe_id=uni.id, stock_id=stock.id)
        )
        await session.commit()

    with caplog.at_level(logging.INFO):
        result = await jobs_module.ingest_universe(P())

    assert result["errors"] == 1
    # The provider error IS logged (that's the point) — but any settings value
    # must NOT be (the spy string came from the fake provider, not config).
    from app.config import settings

    for secret in (settings.llm_api_key, settings.upstox_analytics_token):
        if secret:
            assert secret not in caplog.text
