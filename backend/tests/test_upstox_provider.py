# Phase 6.5 Part F tests — Upstox adapter over mocked HTTP (httpx.MockTransport).
# Zero real network. Also covers credential hygiene: the token must never
# appear in error messages or logs.

import gzip
import json

import httpx
import pytest

from app.providers.base import MarketDataError
from app.providers.upstox_provider import (
    UpstoxProvider,
    parse_instruments,
    parse_period_label,
    parse_ratio_value,
)

TOKEN = "test-token-abc123"


def _candle(day: str, o: float, h: float, low: float, c: float, v: int) -> list:
    return [f"{day}T00:00:00+05:30", o, h, low, c, v, 0]


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.upstox.com/v2",
        transport=httpx.MockTransport(handler),
        headers={"Accept": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )


INSTRUMENT_MAP = {"RELIANCE": ("NSE_EQ|INE002A01018", "INE002A01018")}


# --- Pure parsers ---------------------------------------------------------------


def test_parse_period_label_indian_fiscal_year_end():
    assert parse_period_label("Mar 2026") is not None
    assert parse_period_label("Mar 2026").isoformat() == "2026-03-31"
    assert parse_period_label("Jun 2025").isoformat() == "2025-06-30"
    assert parse_period_label("Dec 2024").isoformat() == "2024-12-31"


def test_parse_period_label_rejects_garbage():
    assert parse_period_label("") is None
    assert parse_period_label("Foo 2026") is None
    assert parse_period_label("2026") is None
    assert parse_period_label(None) is None


def test_parse_ratio_values():
    assert parse_ratio_value("20.15") == 20.15
    assert parse_ratio_value("8.94%") == pytest.approx(0.0894)
    assert parse_ratio_value("-") is None
    assert parse_ratio_value("") is None
    assert parse_ratio_value(None) is None
    assert parse_ratio_value("n/a") is None


def test_parse_instruments_keeps_cash_equities():
    payload = json.dumps([
        {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "RELIANCE",
         "isin": "INE002A01018", "instrument_key": "NSE_EQ|INE002A01018"},
        {"segment": "NSE_FO", "instrument_type": "FUT", "trading_symbol": "RELIANCE",
         "isin": "INE002A01018", "instrument_key": "NSE_FO|123"},
        {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "BAD",
         "isin": None, "instrument_key": "NSE_EQ|x"},
    ]).encode()
    parsed = parse_instruments(gzip.compress(payload))
    assert parsed == {"RELIANCE": ("NSE_EQ|INE002A01018", "INE002A01018")}


def test_parse_instruments_invalid_payload_raises_market_data_error():
    with pytest.raises(MarketDataError):
        parse_instruments(b"not gzip")


# --- Token hygiene ---------------------------------------------------------------


def test_missing_token_rejected():
    with pytest.raises(MarketDataError):
        UpstoxProvider("")
    with pytest.raises(MarketDataError):
        UpstoxProvider("   ")


async def test_token_never_appears_in_errors():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    provider = UpstoxProvider(
        TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP
    )
    try:
        await provider.get_price_history("RELIANCE.NS", "1y")
        raised = False
    except MarketDataError as exc:
        raised = True
        assert TOKEN not in str(exc)
    assert raised


async def test_authorization_header_uses_bearer_token():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"status": "success", "data": {"candles": []}})

    provider = UpstoxProvider(
        TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP
    )
    await provider.get_price_history("RELIANCE.NS", "1y")
    assert seen["auth"] == f"Bearer {TOKEN}"


# --- Price history ----------------------------------------------------------------


def _candle_handler(calls: list[str]):
    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "candles": [
                        _candle("2026-01-02", 101.0, 103.0, 100.0, 102.5, 1500),
                        _candle("2026-01-01", 100.0, 101.0, 99.0, 100.5, 1200),
                    ]
                },
            },
        )

    return handler


async def test_price_history_parses_candles_chronological():
    calls: list[str] = []
    provider = UpstoxProvider(
        TOKEN, client=_client(_candle_handler(calls)), instrument_map=INSTRUMENT_MAP
    )
    bars = await provider.get_price_history("RELIANCE.NS", "1y")
    assert len(bars) == 2
    assert bars[0].date.isoformat() == "2026-01-01"
    assert bars[1].date.isoformat() == "2026-01-02"
    assert bars[0].close == 100.5
    assert bars[0].volume == 1200
    assert bars[0].source == "upstox"
    # The instrument key must be URL-encoded in the path.
    assert any("NSE_EQ%7CINE002A01018" in url for url in calls)


async def test_price_history_unsupported_period_raises():
    provider = UpstoxProvider(
        TOKEN, client=_client(_candle_handler([])), instrument_map=INSTRUMENT_MAP
    )
    with pytest.raises(MarketDataError):
        await provider.get_price_history("RELIANCE.NS", "7d")


async def test_price_history_unknown_symbol_raises():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be called without an instrument")

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map={"TCS": ("K", "I")})
    with pytest.raises(MarketDataError):
        await provider.get_price_history("RELIANCE.NS", "1y")


# --- Fundamentals / profile -------------------------------------------------------


async def test_fundamentals_maps_key_ratios():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/fundamentals/INE002A01018/key-ratios"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    {"name": "P/E", "company_value": "20.15", "sector_value": "12.46"},
                    {"name": "P/B", "company_value": "2.13", "sector_value": "1.53"},
                    {"name": "ROA", "company_value": "4.39%", "sector_value": "7.54%"},
                    {"name": "ROE", "company_value": "8.94%", "sector_value": "16.46%"},
                    {"name": "EV/EBITDA", "company_value": "10.25", "sector_value": "6.94"},
                ],
            },
        )

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP)
    f = await provider.get_fundamentals("RELIANCE.NS")
    assert f.trailing_pe == 20.15
    assert f.price_to_book == 2.13
    assert f.return_on_assets == pytest.approx(0.0439)
    assert f.return_on_equity == pytest.approx(0.0894)
    # Fields Upstox does not supply stay None (never fabricated).
    assert f.market_cap is None
    assert f.price_to_sales is None
    assert f.ebitda is None


async def test_profile_maps_sector_without_name():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {"sector": "Refineries", "company_profile": "desc"},
            },
        )

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP)
    profile = await provider.get_stock_profile("RELIANCE.NS")
    assert profile.sector == "Refineries"
    assert profile.name is None  # Upstox has no display name; merge fills it


# --- Financial history --------------------------------------------------------------


def _income_statement_payload() -> dict:
    return {
        "status": "success",
        "data": {
            "type": "consolidated",
            "time_period": "yearly",
            "units_in": "crore",
            "income_statement": [
                {
                    "category": "revenue",
                    "history": [
                        {"value": 982671, "period": "Mar 2025"},
                        {"value": 917121, "period": "Mar 2024"},
                    ],
                },
                {
                    "category": "operating_profit",
                    "history": [
                        {"value": 106017, "period": "Mar 2025"},
                        {"value": 104340, "period": "Mar 2024"},
                    ],
                },
                {
                    "category": "net_profit",
                    "history": [
                        {"value": 80787, "period": "Mar 2025"},
                        {"value": 78633, "period": "Mar 2024"},
                    ],
                },
            ],
            "full_statement": [
                {
                    "particular": "EPS - Basic",
                    "history": [
                        {"period": "Mar 2025", "value": 51.0},
                        {"period": "Mar 2024", "value": 51.2},
                    ],
                },
                {
                    "particular": "EPS - Diluted",
                    "history": [
                        {"period": "Mar 2025", "value": 51.47},
                        {"period": "Mar 2024", "value": 51.45},
                    ],
                },
            ],
        },
    }


async def test_financial_history_converts_crore_to_rupees():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert "type=consolidated" in str(request.url)
        assert "time_period=yearly" in str(request.url)
        return httpx.Response(200, json=_income_statement_payload())

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP)
    periods = await provider.get_financial_history("RELIANCE.NS")

    by_end = {p.period_end: p for p in periods}
    assert len(by_end) == 2

    fy25 = by_end[parse_period_label("Mar 2025")]
    assert fy25.revenue == pytest.approx(982671 * 1e7)   # crore -> rupees
    assert fy25.net_income == pytest.approx(80787 * 1e7)
    assert fy25.operating_margin == pytest.approx(106017 / 982671)
    assert fy25.net_margin == pytest.approx(80787 / 982671)
    assert fy25.eps == 51.47  # diluted preferred over basic
    assert fy25.period_type == "annual"
    assert fy25.source == "upstox"


async def test_financial_history_unsupported_units_raises():
    payload = _income_statement_payload()
    payload["data"]["units_in"] = "million"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP)
    with pytest.raises(MarketDataError):
        await provider.get_financial_history("RELIANCE.NS")


async def test_financial_history_skips_unparseable_periods():
    payload = _income_statement_payload()
    payload["data"]["income_statement"][0]["history"].append(
        {"value": 100.0, "period": "Q??"}
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP)
    periods = await provider.get_financial_history("RELIANCE.NS")
    assert len(periods) == 2  # the bad label is skipped, not guessed


# --- Failure modes --------------------------------------------------------------------


async def test_non_200_raises_market_data_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP)
    with pytest.raises(MarketDataError):
        await provider.get_fundamentals("RELIANCE.NS")


async def test_error_envelope_raises_market_data_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "errors": {}})

    provider = UpstoxProvider(TOKEN, client=_client(handler), instrument_map=INSTRUMENT_MAP)
    with pytest.raises(MarketDataError):
        await provider.get_fundamentals("RELIANCE.NS")


async def test_instrument_resolution_from_master_file():
    master = gzip.compress(
        json.dumps([
            {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "RELIANCE",
             "isin": "INE002A01018", "instrument_key": "NSE_EQ|INE002A01018"},
        ]).encode()
    )
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "assets.upstox.com" in str(request.url):
            return httpx.Response(200, content=master)
        return httpx.Response(
            200, json={"status": "success", "data": {"candles": []}}
        )

    # No instrument_map: the adapter must load the official instruments file.
    client = httpx.AsyncClient(
        base_url="https://api.upstox.com/v2", transport=httpx.MockTransport(handler)
    )
    provider = UpstoxProvider(TOKEN, client=client)
    bars = await provider.get_price_history("RELIANCE.NS", "1y")
    assert bars == []
    assert any("NSE.json.gz" in url for url in calls)
    assert any("historical-candle" in url for url in calls)
