# Phase 5 tests — grounded LLM explanation. All network-free:
#  - FakeLLMProvider replaces the real OpenRouter httpx call everywhere.
#  - Settings are monkeypatched to simulate no-key / model-available / budget cap.
#  - OpenRouterProvider itself is tested against a monkeypatched httpx client.

import asyncio
from datetime import date

import httpx

import pytest

from app.providers.llm_base import LLMError, LLMProvider, LLMResult
from app.providers.openrouter_provider import OpenRouterProvider
from app.services.alpha import AlphaResult, ValueSignal
from app.services import llm_narrative as narr


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level cache + daily counter between tests (they persist)."""
    narr._cache.clear()
    narr._calls_today = 0
    narr._calls_day = date.today()
    yield


class FakeLLMProvider(LLMProvider):
    """Deterministic provider; can be told to fail."""

    def __init__(self, text="Narrated from facts.", tokens=42, model="fake-model",
                 error: Exception | None = None):
        self.text = text
        self.tokens = tokens
        self.model = model
        self.error = error
        self.calls = 0
        self.last_system = None
        self.last_user = None

    async def generate(self, system: str, user: str) -> LLMResult:
        self.calls += 1
        self.last_system = system
        self.last_user = user
        if self.error is not None:
            raise self.error
        return LLMResult(text=self.text, tokens_used=self.tokens, model=self.model)


def _result(**overrides) -> AlphaResult:
    base = dict(
        symbol="RELIANCE.NS",
        composite=59,
        fundamental=98,
        technical=27,
        sentiment=39,
        components={"trend": 31.4, "momentum": 3.8, "reversion": 50.0},
        weights={"fundamental": 0.4, "technical": 0.3, "sentiment": 0.3},
        value_signal=ValueSignal(metric="P/E", status="fairly_valued",
                                 margin_pct=-2.3, explanation="Trades at PE 16.56."),
        insufficient_data=False,
    )
    base.update(overrides)
    return AlphaResult(**base)


# --- Allow-list security boundary ---------------------------------------------


def test_alpha_facts_is_explicit_allowlist():
    facts = narr._alpha_facts(_result())
    allowed = {
        "symbol", "composite", "fundamental", "technical", "sentiment",
        "components", "weights", "value_signal", "insufficient_data",
    }
    assert set(facts) == allowed  # nothing extra sneaks in
    # value_signal is structurally limited (never free-text explanation).
    assert set(facts["value_signal"]) == {"metric", "status", "margin_pct"}
    # The free-text explanation on ValueSignal must never reach the prompt.
    assert "Trades at PE" not in str(facts)


# --- Prompt grounding + output contract ---------------------------------------

def test_prompt_contains_actual_scores():
    system, user = narr.build_alpha_prompt(_result())
    assert "59" in user          # composite
    assert "98" in user          # fundamental
    assert "31.4" in user        # technical sub-component
    assert "RELIANCE.NS" in user


def test_prompt_enforces_output_contract():
    system, _ = narr.build_alpha_prompt(_result())
    for phrase in ("short explanation", "Do NOT invent", "investment advice",
                   "guaranteed"):
        assert phrase.lower() in system.lower()


# --- generate_alpha_explanation: disabled / provider / fallback paths ---------

async def test_no_key_skips_provider(monkeypatch):
    monkeypatch.setattr(narr.settings, "llm_api_key", "")
    monkeypatch.setattr(narr.settings, "llm_model", "fake-model")
    provider = FakeLLMProvider()
    out = await narr.generate_alpha_explanation(FakeStock("RELIANCE.NS"), _result(), provider)
    assert provider.calls == 0
    assert "Alpha composite" in out  # rule-based fallback


async def test_no_model_skips_provider(monkeypatch):
    monkeypatch.setattr(narr.settings, "llm_api_key", "sk-fake")
    monkeypatch.setattr(narr.settings, "llm_model", "")
    provider = FakeLLMProvider()
    out = await narr.generate_alpha_explanation(FakeStock("RELIANCE.NS"), _result(), provider)
    assert provider.calls == 0
    assert "Alpha composite" in out


async def test_provider_error_falls_back(monkeypatch):
    monkeypatch.setattr(narr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(narr.settings, "llm_model", "fake-model")
    provider = FakeLLMProvider(error=LLMError("boom"))
    out = await narr.generate_alpha_explanation(FakeStock("RELIANCE.NS"), _result(), provider)
    assert provider.calls == 1
    assert "Alpha composite" in out


async def test_provider_success_uses_llm_text(monkeypatch):
    monkeypatch.setattr(narr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(narr.settings, "llm_model", "fake-model")
    provider = FakeLLMProvider(text="This is a grounded narrative.")
    out = await narr.generate_alpha_explanation(FakeStock("RELIANCE.NS"), _result(), provider)
    assert out == "This is a grounded narrative."
    assert provider.calls == 1


async def test_budget_cap_skips_provider(monkeypatch):
    monkeypatch.setattr(narr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(narr.settings, "llm_model", "fake-model")
    monkeypatch.setattr(narr.settings, "llm_daily_cap", 0)  # cap already hit
    provider = FakeLLMProvider()
    out = await narr.generate_alpha_explanation(FakeStock("RELIANCE.NS"), _result(), provider)
    assert provider.calls == 0
    assert "Alpha composite" in out


# --- TTL cache ----------------------------------------------------------------

async def test_ttl_cache_reuses_narrative(monkeypatch):
    monkeypatch.setattr(narr.settings, "llm_api_key", "fake")
    monkeypatch.setattr(narr.settings, "llm_model", "fake-model")
    provider = FakeLLMProvider()
    r = _result()
    stock = FakeStock("RELIANCE.NS")

    first = await narr.generate_alpha_explanation(stock, r, provider)
    second = await narr.generate_alpha_explanation(stock, r, provider)
    assert first == second == "Narrated from facts."
    assert provider.calls == 1  # second call served from cache


# --- Cost logging -------------------------------------------------------------

def test_log_usage_records_tokens_and_model(caplog):
    with caplog.at_level("INFO", logger="app.services.llm_narrative"):
        narr._log_usage(LLMResult(text="hi", tokens_used=123, model="m"))
    assert "tokens=123" in caplog.text
    assert "model=m" in caplog.text


def test_log_usage_handles_none_tokens(caplog):
    with caplog.at_level("INFO", logger="app.services.llm_narrative"):
        narr._log_usage(LLMResult(text="hi", tokens_used=None, model="m"))
    assert "tokens=n/a" in caplog.text


# --- OpenRouterProvider: success / non-2xx / malformed (mocked httpx) ---------

class FakeStock:
    def __init__(self, symbol):
        self.symbol = symbol
        self.id = 1


class _FakeResp:
    """Minimal stand-in for an httpx.Response used by OpenRouterProvider."""

    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture()
def fake_post(monkeypatch):
    """Monkeypatch httpx.AsyncClient.post; returns a queue of (status,payload)."""
    queue = []

    async def _post(self, url, json=None, headers=None):
        status, payload = queue.pop(0)
        return _FakeResp(status, payload)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)
    return queue


def test_openrouter_success(fake_post):
    fake_post.append(
        (200, {
            "model": "echoed-model",
            "choices": [{"message": {"content": "  Grounded text.  "}}],
            "usage": {"total_tokens": 88},
        })
    )
    provider = OpenRouterProvider(api_key="k", model="m")
    res = asyncio.run(provider.generate("sys", "user"))
    assert res.text == "Grounded text."
    assert res.tokens_used == 88
    assert res.model == "echoed-model"


def test_openrouter_non2xx_raises(fake_post):
    fake_post.append((500, {}))
    provider = OpenRouterProvider(api_key="k", model="m")
    with pytest.raises(LLMError):
        asyncio.run(provider.generate("sys", "user"))


def test_openrouter_malformed_raises(fake_post):
    fake_post.append((200, {"no_choices": True}))
    provider = OpenRouterProvider(api_key="k", model="m")
    with pytest.raises(LLMError):
        asyncio.run(provider.generate("sys", "user"))


def test_openrouter_invalid_json_raises(monkeypatch):
    class _BadJson(_FakeResp):
        def json(self):
            raise ValueError("not json")

    async def _post_bad(self, url, json=None, headers=None):
        return _BadJson(200, None)

    monkeypatch.setattr(httpx.AsyncClient, "post", _post_bad)
    provider = OpenRouterProvider(api_key="k", model="m")
    with pytest.raises(LLMError):
        asyncio.run(provider.generate("sys", "user"))