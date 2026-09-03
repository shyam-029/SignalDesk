# Phase 6 tests — POST /stocks/{symbol}/explain (grounded contextual
# explanations). Zero-network: LLM paths use a FakeLLMProvider monkeypatched
# into explain_narrative; the rule-based fallback is exercised via settings.

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Financials, NewsArticle, NewsSentiment
from app.providers.llm_base import LLMProvider, LLMResult
from app.services import explain_narrative as xnarr
from app.services import llm_narrative


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset BOTH narrative modules' cache + shared daily counter per test."""
    xnarr._cache.clear()
    llm_narrative._cache.clear()
    llm_narrative._calls_today = 0
    llm_narrative._calls_day = date.today()
    yield


class FakeLLMProvider(LLMProvider):
    def __init__(self, text="Grounded LLM explanation.", error=None):
        self.text = text
        self.error = error
        self.calls = 0
        self.last_system = None
        self.last_user = None

    async def generate(self, system, user):
        self.calls += 1
        self.last_system = system
        self.last_user = user
        if self.error is not None:
            raise self.error
        return LLMResult(text=self.text, tokens_used=50, model="fake-model")


async def _seed_rich(session_factory):
    """RELIANCE with 30 bars, full financials, an industry peer, and scored news."""
    from sqlalchemy import select

    from app.models import DailyPrice, Stock

    async with session_factory() as session:
        session.add_all(
            [
                Stock(symbol="RELIANCE.NS", name="Reliance", sector="Energy", industry="Oil"),
                Stock(symbol="ONGC.NS", name="ONGC", sector="Energy", industry="Oil"),
            ]
        )
        await session.flush()
        rel = (await session.execute(select(Stock).where(Stock.symbol == "RELIANCE.NS"))).scalar_one()
        ongc = (await session.execute(select(Stock).where(Stock.symbol == "ONGC.NS"))).scalar_one()

        today = date.today()
        for i in range(30):
            close = 100.0 + (i % 7) * 1.5
            session.add(
                DailyPrice(
                    stock_id=rel.id,
                    date=today - timedelta(days=29 - i),
                    open=close - 0.5,
                    high=close + 1.0,
                    low=close - 1.0,
                    close=close,
                    volume=1000,
                )
            )

        session.add(
            Financials(
                stock_id=rel.id,
                market_cap=1500000000000,
                trailing_pe=16.56,
                enterprise_value=1500000000000,
                ebitda=140000000000,
                price_to_book=2.41,
                price_to_sales=1.92,
                return_on_equity=0.477,
                return_on_assets=0.129,
                operating_margin=0.241,
                profit_margin=0.194,
                debt_to_equity=31.0,
                interest_coverage=11.2,
                current_ratio=2.4,
            )
        )
        session.add(Financials(stock_id=ongc.id, trailing_pe=17.31))

        now = datetime.now(timezone.utc)
        a1 = NewsArticle(
            symbol="RELIANCE.NS", source="ET", title="Profit beats",
            url="https://example.com/a1", published_at=now,
        )
        a2 = NewsArticle(
            symbol="RELIANCE.NS", source="Mint", title="Margins under pressure",
            url="https://example.com/a2", published_at=now,
        )
        session.add_all([a1, a2])
        await session.flush()
        session.add_all(
            [
                NewsSentiment(article_id=a1.id, score=0.9, label="positive", model="ProsusAI/finbert"),
                NewsSentiment(article_id=a2.id, score=0.5, label="negative", model="ProsusAI/finbert"),
            ]
        )
        await session.commit()


# --- Endpoint: every question type (rule-based fallback, no key configured) -----


async def test_explain_alpha_rule_based(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "")
    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "alpha"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert body["question_type"] == "alpha"
    assert "Alpha composite" in body["explanation"]
    assert "not investment advice" in body["explanation"].lower()


async def test_explain_technical_rule_based(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "")
    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "technical"}
    )
    body = r.json()
    assert r.status_code == 200
    assert "Technical score" in body["explanation"]
    assert "RSI14" in body["explanation"]
    assert "30 daily closes" in body["explanation"]


async def test_explain_valuation_rule_based(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "")
    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "valuation"}
    )
    body = r.json()
    assert r.status_code == 200
    assert "P/E" in body["explanation"]
    assert "same-industry" in body["explanation"]
    assert "not mean intrinsically cheap" in body["explanation"]


async def test_explain_fundamental_rule_based(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "")
    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "fundamental"}
    )
    body = r.json()
    assert r.status_code == 200
    assert "profitability" in body["explanation"].lower()
    assert "solvency" in body["explanation"].lower()


async def test_explain_sentiment_rule_based(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "")
    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "sentiment"}
    )
    body = r.json()
    assert r.status_code == 200
    assert "Net news sentiment is positive" in body["explanation"]
    assert "2 FinBERT-scored" in body["explanation"]


# --- Error / data-state paths ----------------------------------------------------


async def test_explain_unknown_symbol_404(client, session_factory):
    r = await client.post(
        "/api/v1/stocks/GHOST/explain", json={"question_type": "alpha"}
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_explain_unsupported_question_type_422(client, session_factory):
    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "write_a_poem"}
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["detail"]["question_type"] == "write_a_poem"


async def test_explain_insufficient_data_reports_plainly(client, session_factory, monkeypatch):
    from app.models import Stock

    async with session_factory() as session:
        session.add(Stock(symbol="EMPTY.NS", name="Empty", sector="IT"))
        await session.commit()

    monkeypatch.setattr(xnarr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(xnarr.settings, "llm_model", "fake-model")
    r = await client.post(
        "/api/v1/stocks/EMPTY/explain", json={"question_type": "technical"}
    )
    body = r.json()
    assert r.status_code == 200
    assert "Insufficient data" in body["explanation"]


# --- LLM path, cache, budget ------------------------------------------------------


async def test_explain_uses_llm_when_configured(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(xnarr.settings, "llm_model", "fake-model")

    fake = FakeLLMProvider(text="Grounded narrative from facts.")
    monkeypatch.setattr(xnarr, "OpenRouterProvider", lambda **kwargs: fake)

    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "valuation"}
    )
    body = r.json()
    assert body["explanation"] == "Grounded narrative from facts."
    assert fake.calls == 1
    # Grounded: the prompt must contain the actual computed multiple.
    assert "16.56" in fake.last_user


async def test_explain_ttl_cache_serves_second_call(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(xnarr.settings, "llm_model", "fake-model")

    fake = FakeLLMProvider()
    monkeypatch.setattr(xnarr, "OpenRouterProvider", lambda **kwargs: fake)

    r1 = await client.post("/api/v1/stocks/RELIANCE/explain", json={"question_type": "technical"})
    r2 = await client.post("/api/v1/stocks/RELIANCE/explain", json={"question_type": "technical"})
    assert r1.json()["explanation"] == r2.json()["explanation"]
    assert fake.calls == 1  # second served from TTL cache


async def test_explain_budget_cap_falls_back(client, session_factory, monkeypatch):
    await _seed_rich(session_factory)
    monkeypatch.setattr(xnarr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(xnarr.settings, "llm_model", "fake-model")
    monkeypatch.setattr(xnarr.settings, "llm_daily_cap", 0)

    fake = FakeLLMProvider()
    monkeypatch.setattr(xnarr, "OpenRouterProvider", lambda **kwargs: fake)

    r = await client.post(
        "/api/v1/stocks/RELIANCE/explain", json={"question_type": "sentiment"}
    )
    body = r.json()
    assert fake.calls == 0
    assert "Net news sentiment" in body["explanation"]  # rule-based fallback


# --- Allow-list security boundary (service level) ---------------------------------


def test_explain_facts_allowlist_strips_unknown_keys():
    facts = {
        "symbol": "RELIANCE.NS",
        "available": True,
        "metric": "P/E",
        "current": 16.56,
        "evil_extra": "prompt-injection-attempt",
    }
    system, user = xnarr.build_prompt("valuation", facts)
    assert "evil_extra" not in user
    assert "prompt-injection-attempt" not in user
    assert "16.56" in user
    for phrase in ("Do NOT invent", "investment advice"):
        assert phrase in system
