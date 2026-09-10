# Incident 2026-09-09 regression tests — null/NaN overwrite bug.
#
# Failure modes proven closed (see SEMESTER2_PROGRESS.md work log):
#   1. yfinance ex-dividend rows returned NaN OHLC with real volume; the
#      unconditional price upsert stored them and destroyed previously-good
#      bars (2,257 symbols incl. every curated ETF). Guard: provider drops
#      NaN-OHLC rows; upserts COALESCE field-by-field.
#   2. Sparse provider responses (throttled info dicts, empty statement
#      fields) overwrote good stored values in financial_periods,
#      balance_sheet_periods and company_profiles.
#   3. An empty RSS article list rendered INSERT ... DEFAULT VALUES and
#      tripped news_articles.symbol NOT NULL.
#   5. Any non-finite float reaching a dict-returning route serialized as an
#      invalid JSON literal browsers cannot parse.
#
# Zero-network: fake providers / canned DataFrames; DB is signaldesk_test via
# monkeypatched SessionLocal (same pattern as test_jobs_status.py).

import json
import math
from datetime import date

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.jobs as jobs_module
from app.jobs import ingest_balance_sheets, ingest_financial_periods
from app.models import (
    BalanceSheetPeriod,
    CompanyProfile,
    DailyPrice,
    FinancialPeriod,
    NewsArticle,
    Stock,
    Universe,
    stock_universe,
)
from app.nan_guard import nan_guard_middleware, scrub_non_finite
from app.providers.base import (
    BalanceSheetDraft,
    FinancialPeriodDraft,
    Fundamentals,
    MarketDataProvider,
    StockProfile,
)
from app.providers.yfinance_provider import YFinanceProvider
from app.repositories import company_profiles as profile_repo


# --- Fakes ---------------------------------------------------------------------


class FakeStatementProvider(MarketDataProvider):
    """Canned statements; supports staging successive responses per symbol."""

    name = "fake-stmt"

    def __init__(self):
        self.periods: dict[str, list[FinancialPeriodDraft]] = {}
        self.balance_sheets: dict[str, list[BalanceSheetDraft]] = {}

    async def get_price_history(self, symbol: str, period: str):
        return []

    async def get_stock_profile(self, symbol: str):
        return StockProfile(symbol=symbol, name=symbol, sector=None, industry=None)

    async def get_fundamentals(self, symbol: str):
        return Fundamentals(symbol=symbol)

    async def get_financial_history(self, symbol: str, period_type="annual"):
        if period_type == "quarterly":
            return []
        return self.periods.get(symbol, [])

    async def get_balance_sheet(self, symbol: str):
        return self.balance_sheets.get(symbol, [])


async def _seed_universe(session_factory, symbols: list[str]) -> None:
    async with session_factory() as session:
        universe = await session.scalar(
            select(Universe).where(Universe.name == jobs_module.UNIVERSE_NAME)
        )
        if universe is None:
            universe = Universe(name=jobs_module.UNIVERSE_NAME)
            session.add(universe)
            await session.flush()
        for symbol in symbols:
            stock = Stock(symbol=symbol, name=f"Name {symbol}")
            session.add(stock)
            await session.flush()
            await session.execute(
                stock_universe.insert().values(universe_id=universe.id, stock_id=stock.id)
            )
        await session.commit()


# --- Fix 1a: provider drops NaN-OHLC rows --------------------------------------


async def test_yfinance_drops_nan_ohlc_rows(monkeypatch):
    """Ex-div all-NaN rows are dropped, good rows kept, NaN volume survives."""
    import app.providers.yfinance_provider as yf_mod

    idx = pd.to_datetime(
        ["2026-09-05", "2026-09-07", "2026-09-08"]
    ).tz_localize("Asia/Kolkata")
    frame = pd.DataFrame(
        {
            # 09-07 mirrors the live GEECEE.NS ex-div row: all-NaN prices,
            # zero volume, a real dividend.
            "Open": [100.0, float("nan"), 102.0],
            "High": [101.0, float("nan"), 103.0],
            "Low": [99.0, float("nan"), 101.5],
            "Close": [100.5, float("nan"), 102.5],
            "Volume": [1000, 0, 1200],
            "Dividends": [0.0, 2.0, 0.0],
            "Stock Splits": [0.0, 0.0, 0.0],
        },
        index=idx,
    )

    class FakeTicker:
        def history(self, period: str):
            return frame

    monkeypatch.setattr(yf_mod.yf, "Ticker", lambda symbol: FakeTicker())

    bars = await YFinanceProvider().get_price_history("GEECEE.NS", "5d")

    assert [b.date for b in bars] == [date(2026, 9, 5), date(2026, 9, 8)]
    for b in bars:
        assert None not in (b.open, b.high, b.low, b.close)
        assert all(math.isfinite(v) for v in (b.open, b.high, b.low, b.close))


# --- Fix 1b: NaN rows never reach the daily_prices upsert (end-to-end) ----------


async def test_nan_price_row_rejected_not_stored(session_factory, monkeypatch):
    """The full ingestion path: an ex-div all-NaN row is dropped, so the
    previously-good stored bar for that date SURVIVES the nightly refetch —
    the exact production failure (2,257 NaN closes overwriting good bars).
    """
    import app.providers.yfinance_provider as yf_mod

    idx = pd.to_datetime(
        ["2026-09-05", "2026-09-07", "2026-09-08"]
    ).tz_localize("Asia/Kolkata")
    frame = pd.DataFrame(
        {
            # 09-07 is the ex-dividend row Yahoo served all-NaN (GEECEE.NS).
            "Open": [100.0, float("nan"), 102.0],
            "High": [101.0, float("nan"), 103.0],
            "Low": [99.0, float("nan"), 101.5],
            "Close": [100.5, float("nan"), 102.5],
            "Volume": [1000, 0, 1200],
            "Dividends": [0.0, 2.0, 0.0],
            "Stock Splits": [0.0, 0.0, 0.0],
        },
        index=idx,
    )

    class FakeTicker:
        def history(self, period: str):
            return frame

    monkeypatch.setattr(yf_mod.yf, "Ticker", lambda symbol: FakeTicker())

    async with session_factory() as session:
        stock = Stock(symbol="GEECEE.NS", name="Co")
        session.add(stock)
        await session.flush()
        stock_id = stock.id
        # The bar the provider used to destroy: a good close for the same
        # ex-div date, stored by an earlier (pre-glitch) ingestion.
        session.add(
            DailyPrice(
                stock_id=stock_id, date=date(2026, 9, 7),
                open=103.0, high=104.0, low=102.0, close=103.5, volume=900,
            )
        )
        await session.commit()

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    symbol, bars = await jobs_module._fetch_one_symbol(
        YFinanceProvider(), "GEECEE.NS"
    )
    assert bars == 2  # the NaN row was rejected at the provider

    async with session_factory() as session:
        rows = (await session.execute(select(DailyPrice))).scalars().all()
        by_date = {r.date: r for r in rows}
        assert set(by_date) == {
            date(2026, 9, 5), date(2026, 9, 7), date(2026, 9, 8),
        }
        # The ex-div row must NOT have overwritten the previously-good bar.
        exdiv = by_date[date(2026, 9, 7)]
        assert float(exdiv.close) == 103.5
        assert exdiv.volume == 900
        # The good rows landed normally.
        assert float(by_date[date(2026, 9, 8)].close) == 102.5


# --- Fix 2: financial_periods COALESCE ------------------------------------------


async def test_financial_periods_coalesce_keeps_stored_values(
    session_factory, monkeypatch
):
    await _seed_universe(session_factory, ["AAACO.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    provider = FakeStatementProvider()
    provider.periods["AAACO.NS"] = [
        FinancialPeriodDraft(
            period_end=date(2026, 3, 31), period_type="annual",
            revenue=100.0, net_income=10.0, operating_margin=0.2,
            net_margin=0.1, eps=5.0, source="fake",
        )
    ]
    await ingest_financial_periods(provider, batch_size=10)

    # Tonight's throttled response omits revenue/net_income entirely.
    provider.periods["AAACO.NS"] = [
        FinancialPeriodDraft(
            period_end=date(2026, 3, 31), period_type="annual",
            revenue=None, net_income=None, operating_margin=0.25,
            net_margin=0.12, eps=6.0, source="fake-sparse",
        )
    ]
    await ingest_financial_periods(provider, batch_size=10)

    async with session_factory() as session:
        row = await session.scalar(select(FinancialPeriod))
        assert float(row.revenue) == 100.0  # kept
        assert float(row.net_income) == 10.0  # kept
        assert float(row.operating_margin) == 0.25  # updated
        assert float(row.eps) == 6.0  # updated
        assert row.source == "fake-sparse"


# --- Fix 2: balance_sheet_periods COALESCE --------------------------------------


async def test_balance_sheet_coalesce_keeps_stored_values(
    session_factory, monkeypatch
):
    await _seed_universe(session_factory, ["AAACO.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    provider = FakeStatementProvider()
    provider.balance_sheets["AAACO.NS"] = [
        BalanceSheetDraft(
            period_end=date(2026, 3, 31), period_type="annual",
            working_capital=2000.0, total_assets=10000.0,
            retained_earnings=3000.0, ebit=1500.0,
            book_equity=6000.0, total_liabilities=4000.0, source="fake",
        )
    ]
    await ingest_balance_sheets(provider, batch_size=10)

    # Sparse re-fetch: only total_assets supplied tonight (a throttled or
    # partially-parsed response). Every omitted field must keep its value.
    provider.balance_sheets["AAACO.NS"] = [
        BalanceSheetDraft(
            period_end=date(2026, 3, 31), period_type="annual",
            working_capital=None, total_assets=11000.0,
            retained_earnings=None, ebit=None,
            book_equity=None, total_liabilities=None, source="fake-sparse",
        )
    ]
    await ingest_balance_sheets(provider, batch_size=10)

    async with session_factory() as session:
        row = await session.scalar(select(BalanceSheetPeriod))
        assert float(row.working_capital) == 2000.0  # kept
        assert float(row.total_assets) == 11000.0  # updated
        assert float(row.retained_earnings) == 3000.0  # kept
        assert float(row.ebit) == 1500.0  # kept
        assert float(row.book_equity) == 6000.0  # kept
        assert float(row.total_liabilities) == 4000.0  # kept


# --- Fix 2: company_profiles COALESCE -------------------------------------------


async def _upsert_profile(session_factory, stock_id, *, summary, ceo, employees, website):
    async with session_factory() as session:
        await profile_repo.upsert_profile(
            session, stock_id=stock_id, business_summary=summary, ceo=ceo,
            employees=employees, website=website, source="yfinance",
        )


async def test_company_profile_coalesce_keeps_stored_values(session_factory):
    async with session_factory() as session:
        stock = Stock(symbol="AAACO.NS", name="Co")
        session.add(stock)
        await session.flush()
        stock_id = stock.id
        await session.commit()

    await _upsert_profile(
        session_factory, stock_id,
        summary="Does things", ceo="Founder", employees=10, website="https://x",
    )
    # Throttled night: provider supplied nothing.
    await _upsert_profile(
        session_factory, stock_id, summary=None, ceo=None,
        employees=None, website=None,
    )
    async with session_factory() as session:
        row = await session.scalar(select(CompanyProfile))
        assert row.business_summary == "Does things"
        assert row.ceo == "Founder"
        assert row.employees == 10
        assert row.website == "https://x"
        assert row.source == "yfinance"  # nothing supplied -> source unchanged

    # Partial night: one field supplied -> it updates, others survive, and
    # source moves because something was supplied.
    await _upsert_profile(
        session_factory, stock_id, summary="Better summary", ceo=None,
        employees=None, website=None,
    )
    async with session_factory() as session:
        row = await session.scalar(select(CompanyProfile))
        assert row.business_summary == "Better summary"
        assert row.ceo == "Founder"  # kept
        assert row.employees == 10  # kept
        assert row.source == "yfinance"  # something was supplied


# --- Fix 3: empty article list is a no-op ----------------------------------------


async def test_upsert_articles_empty_list_is_noop(session_factory):
    """No articles must not render INSERT ... DEFAULT VALUES (NotNullViolation)."""
    async with session_factory() as session:
        result = await jobs_module._upsert_articles(session, [])
        assert result == {"inserted": 0, "existing": 0}
        n = await session.scalar(select(func.count(NewsArticle.id)))
        assert n == 0


# --- Fix 5: API-boundary NaN scrub ----------------------------------------------


def test_scrub_non_finite_replaces_nan_and_inf_with_none():
    data = {
        "a": float("nan"),
        "b": float("inf"),
        "c": float("-inf"),
        "d": 1.5,
        "e": [float("nan"), "x", {"f": float("inf")}],
        "g": "NaN literal string stays",
        "h": None,
    }
    out = scrub_non_finite(data)
    assert out["a"] is None and out["b"] is None and out["c"] is None
    assert out["e"] == [None, "x", {"f": None}]
    assert out["g"] == "NaN literal string stays"  # strings untouched
    assert out["h"] is None


def test_nan_guard_middleware_scrubs_invalid_json_literals():
    """JSON bytes carrying NaN/Infinity literals are rewritten to null.

    On this Starlette the default JSONResponse already refuses NaN
    (allow_nan=False -> 500), so the guard is the layer for renderers that
    do emit the literals (orjson-style encoders, custom Response classes).
    The canned body below simulates such a renderer.
    """
    from starlette.responses import Response as RawResponse

    app = FastAPI()
    app.middleware("http")(nan_guard_middleware)

    @app.get("/bad")
    async def bad():
        # A renderer that (unlike JSONResponse) passes the invalid literal
        # through — exactly what the guard must catch.
        return RawResponse(
            content=b'{"last_price": NaN, "ok": 1}',
            media_type="application/json",
        )

    @app.get("/good")
    async def good():
        return {"last_price": 1.5}

    client = TestClient(app)
    r_bad = client.get("/bad")
    assert r_bad.status_code == 200
    assert "NaN" not in r_bad.text
    body = json.loads(r_bad.text)
    assert body["last_price"] is None
    assert body["ok"] == 1

    r_good = client.get("/good")
    assert r_good.status_code == 200
    assert r_good.json() == {"last_price": 1.5}
