# Phase 6.5 Part E tests â€” historical endpoints + ingestion job (zero network).

from datetime import date, timedelta

import pytest
from sqlalchemy import select

import app.jobs as jobs_module
from app.jobs import ingest_financial_periods
from app.models import (
    AlphaScore,
    DailyPrice,
    FinancialPeriod,
    Financials,
    Stock,
    Universe,
    stock_universe,
)
from app.providers.base import (
    FinancialPeriodDraft,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)


# --- Fakes ---------------------------------------------------------------------


class FakeHistoryProvider(MarketDataProvider):
    """Deterministic provider exposing canned financial history."""

    name = "fake"

    def __init__(self, periods: dict[str, list[FinancialPeriodDraft]] | None = None,
                 fail_symbol: str | None = None,
                 quarterly_periods: dict[str, list[FinancialPeriodDraft]] | None = None):
        self.periods = periods or {}
        self.quarterly_periods = quarterly_periods or {}
        self.fail_symbol = fail_symbol

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        return []

    async def get_stock_profile(self, symbol: str) -> StockProfile:
        return StockProfile(symbol=symbol, name=symbol, sector=None, industry=None)

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        return Fundamentals(symbol=symbol)

    async def get_financial_history(
        self, symbol: str, period_type: str = "annual"
    ) -> list[FinancialPeriodDraft]:
        if symbol == self.fail_symbol:
            raise MarketDataError(f"boom for {symbol}")
        if period_type == "quarterly":
            return self.quarterly_periods.get(symbol, [])
        return self.periods.get(symbol, [])


def _draft(day: str, **fields) -> FinancialPeriodDraft:
    return FinancialPeriodDraft(
        period_end=date.fromisoformat(day), period_type="annual", source="fake", **fields
    )


async def _seed_universe(session_factory, symbols: list[str]) -> None:
    async with session_factory() as session:
        universe = await session.scalar(select(Universe).where(Universe.name == "nifty250"))
        if universe is None:
            universe = Universe(name="nifty250")
            session.add(universe)
            await session.flush()
        for symbol in symbols:
            stock = Stock(symbol=symbol, name=f"Name of {symbol}", sector="Energy",
                          industry="Refineries")
            session.add(stock)
            await session.flush()
            await session.execute(
                stock_universe.insert().values(universe_id=universe.id, stock_id=stock.id)
            )
        await session.commit()


# --- Ingestion job -------------------------------------------------------------


async def test_ingest_financial_periods_upserts(session_factory, monkeypatch):
    await _seed_universe(session_factory, ["RELIANCE.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    provider = FakeHistoryProvider({
        "RELIANCE.NS": [
            _draft("2026-03-31", revenue=100.0, net_income=10.0, eps=5.0,
                   operating_margin=0.2, net_margin=0.1),
            _draft("2025-03-31", revenue=90.0, net_income=None),
        ]
    })
    result = await ingest_financial_periods(provider, batch_size=10)
    assert result == {"fetched": 1, "rows": 2, "errors": 0}

    async with session_factory() as session:
        rows = (await session.execute(select(FinancialPeriod))).scalars().all()
        assert len(rows) == 2
        row = next(r for r in rows if r.period_end == date(2026, 3, 31))
        assert float(row.revenue) == 100.0
        assert float(row.eps) == 5.0
        assert row.source == "fake"


async def test_ingest_financial_periods_idempotent(session_factory, monkeypatch):
    await _seed_universe(session_factory, ["RELIANCE.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    provider = FakeHistoryProvider({
        "RELIANCE.NS": [_draft("2026-03-31", revenue=100.0)]
    })
    r1 = await ingest_financial_periods(provider, batch_size=10)
    r2 = await ingest_financial_periods(provider, batch_size=10)
    assert r1["rows"] == 1
    assert r2["rows"] == 1  # upserted, not duplicated

    async with session_factory() as session:
        rows = (await session.execute(select(FinancialPeriod))).scalars().all()
        assert len(rows) == 1


async def test_ingest_financial_periods_isolates_failures(session_factory, monkeypatch):
    await _seed_universe(session_factory, ["RELIANCE.NS", "TCS.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    provider = FakeHistoryProvider(
        periods={"TCS.NS": [_draft("2026-03-31", revenue=50.0)]},
        fail_symbol="RELIANCE.NS",
    )
    result = await ingest_financial_periods(provider, batch_size=10)
    assert result["errors"] == 1
    assert result["rows"] == 1  # TCS still stored


async def test_ingest_financial_periods_provider_without_capability(
    session_factory, monkeypatch
):
    """A provider without the capability (ABC default NotImplementedError)
    stores nothing and is not an error: capability missing, not a failure."""
    await _seed_universe(session_factory, ["RELIANCE.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    class NoHistoryProvider(FakeHistoryProvider):
        async def get_financial_history(
            self, symbol: str, period_type: str = "annual"
        ):
            # Delegate to the ABC default, which raises NotImplementedError.
            return await MarketDataProvider.get_financial_history(self, symbol)

    result = await ingest_financial_periods(NoHistoryProvider(), batch_size=10)
    assert result["rows"] == 0
    assert result["errors"] == 0


# --- /financials/history ---------------------------------------------------------


async def test_financials_history_endpoint(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == "RELIANCE.NS"))
        session.add_all([
            FinancialPeriod(
                stock_id=stock.id, period_end=date(2026, 3, 31), period_type="annual",
                revenue=100.0, net_income=10.0, operating_margin=0.2, net_margin=0.1,
                eps=5.0, source="yfinance",
            ),
            FinancialPeriod(
                stock_id=stock.id, period_end=date(2025, 3, 31), period_type="annual",
                revenue=90.0, net_income=None, operating_margin=None, net_margin=None,
                eps=None, source="merged",
            ),
        ])
        await session.commit()

    r = await client.get("/api/v1/stocks/RELIANCE/financials/history")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] is False
    assert len(body["items"]) == 2
    assert body["items"][0]["period_end"] == "2026-03-31"  # newest first
    assert body["items"][0]["revenue"] == 100.0
    assert body["items"][0]["source"] == "yfinance"
    assert body["items"][1]["net_income"] is None  # missing stays missing


async def test_financials_history_period_type_filter(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == "RELIANCE.NS"))
        session.add_all([
            FinancialPeriod(
                stock_id=stock.id, period_end=date(2026, 3, 31), period_type="annual",
                revenue=100.0, source="yfinance",
            ),
            FinancialPeriod(
                stock_id=stock.id, period_end=date(2026, 6, 30), period_type="quarterly",
                revenue=25.0, source="yfinance",
            ),
        ])
        await session.commit()

    r = await client.get("/api/v1/stocks/RELIANCE/financials/history?period_type=quarterly")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["period_type"] == "quarterly"

    r = await client.get("/api/v1/stocks/RELIANCE/financials/history?period_type=decade")
    assert r.status_code == 422


async def test_financials_history_unknown_symbol_404(client, session_factory):
    r = await client.get("/api/v1/stocks/ZZZ/financials/history")
    assert r.status_code == 404


# --- /financials/history grouped views (Session 20 follow-up) ---------------------


async def _seed_quarters_and_years(session_factory) -> None:
    """Four fiscal quarters (FY2026) + two annual rows for grouping tests."""
    async with session_factory() as session:
        session.add(Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == "RELIANCE.NS"))
        session.add_all([
            # FY2026 quarters: H1 = Jun+Sep 2025, H2 = Dec 2025 + Mar 2026.
            FinancialPeriod(stock_id=stock.id, period_end=date(2025, 6, 30), period_type="quarterly",
                            revenue=10.0, net_income=1.0, operating_margin=0.20, source="t"),
            FinancialPeriod(stock_id=stock.id, period_end=date(2025, 9, 30), period_type="quarterly",
                            revenue=30.0, net_income=3.0, operating_margin=0.10, source="t"),
            FinancialPeriod(stock_id=stock.id, period_end=date(2025, 12, 31), period_type="quarterly",
                            revenue=20.0, net_income=None, operating_margin=None, source="t"),
            FinancialPeriod(stock_id=stock.id, period_end=date(2026, 3, 31), period_type="quarterly",
                            revenue=40.0, net_income=8.0, operating_margin=0.25, source="t"),
            # Annual rows: FY2025 + FY2026 (three_yearly groups them in threes).
            FinancialPeriod(stock_id=stock.id, period_end=date(2025, 3, 31), period_type="annual",
                            revenue=80.0, net_income=6.0, source="t"),
            FinancialPeriod(stock_id=stock.id, period_end=date(2026, 3, 31), period_type="annual",
                            revenue=100.0, net_income=14.0, source="t"),
        ])
        await session.commit()


async def test_financials_history_half_yearly_sums_quarters(client, session_factory):
    await _seed_quarters_and_years(session_factory)
    r = await client.get(
        "/api/v1/stocks/RELIANCE/financials/history?period_type=quarterly&group=half_yearly"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] is False
    assert len(body["items"]) == 2
    first, second = body["items"]  # ascending period_end within the response
    assert first["period_end"] == "2025-09-30"  # end of the H1 bucket
    assert first["revenue"] == 40.0             # 10 + 30
    assert first["net_income"] == 4.0           # 1 + 3
    assert first["net_margin"] == pytest.approx(0.1)  # 4/40, recomputed from sums
    # Revenue-weighted operating margin: (0.20*10 + 0.10*30) / 40 = 0.125
    assert first["operating_margin"] == pytest.approx(0.125)
    assert first["eps"] is None                 # per-share metric is never summed
    assert first["aggregated_from"] == 2
    assert second["period_end"] == "2026-03-31"
    assert second["revenue"] == 60.0            # 20 + 40
    assert second["net_income"] == 8.0          # None quarter contributes nothing
    assert second["operating_margin"] == pytest.approx(0.25)  # only one input


async def test_financials_history_three_yearly_sums_annual(client, session_factory):
    await _seed_quarters_and_years(session_factory)
    r = await client.get(
        "/api/v1/stocks/RELIANCE/financials/history?period_type=annual&group=three_yearly"
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1  # two annual rows -> one 3-year bucket
    row = body["items"][0]
    assert row["revenue"] == 180.0
    assert row["net_income"] == 20.0
    assert row["net_margin"] == pytest.approx(20.0 / 180.0)
    assert row["aggregated_from"] == 2


async def test_financials_history_group_validation(client, session_factory):
    await _seed_quarters_and_years(session_factory)
    # half_yearly requires quarterly periods; three_yearly requires annual.
    r = await client.get("/api/v1/stocks/RELIANCE/financials/history?period_type=annual&group=half_yearly")
    assert r.status_code == 422
    r = await client.get("/api/v1/stocks/RELIANCE/financials/history?period_type=quarterly&group=three_yearly")
    assert r.status_code == 422
    r = await client.get("/api/v1/stocks/RELIANCE/financials/history?group=decade")
    assert r.status_code == 422


async def test_financials_history_empty_is_insufficient(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="NEW.NS", name="New", sector="X", industry="Y"))
        await session.commit()
    r = await client.get("/api/v1/stocks/NEW/financials/history")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["insufficient_data"] is True


# --- /performance -----------------------------------------------------------------


async def _seed_price_bars(session_factory, symbol: str, days: int) -> None:
    """Seed `days` consecutive daily bars ending today, closing 100, 101, ..."""
    async with session_factory() as session:
        session.add(Stock(symbol=symbol, name="Reliance", sector="E", industry="O"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == symbol))
        end = date.today()
        for i in range(days):
            d = end - timedelta(days=days - 1 - i)
            close = 100 + i
            session.add(
                DailyPrice(
                    stock_id=stock.id, date=d, open=close, high=close + 1,
                    low=close - 1, close=close, volume=1000,
                )
            )
        await session.commit()


async def test_performance_endpoint_windows(client, session_factory):
    await _seed_price_bars(session_factory, "RELIANCE.NS", 40)
    r = await client.get("/api/v1/stocks/RELIANCE/performance")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] is False
    assert body["bars_used"] == 40
    assert body["as_of"] == date.today().isoformat()

    # 1m (31 days) anchors on the last bar dated on/before as_of - 31 days:
    # bar i has date as_of-(39-i), so the anchor is bar 8 (close 108.0).
    win = body["windows"]["1m"]
    assert win["end_close"] == 139.0
    assert win["start_close"] == 108.0
    assert win["change_pct"] == round((139.0 - 108.0) / 108.0 * 100, 2)

    # 52-week range from the high/low columns of the stored window.
    assert body["high_52w"] == 140.0
    assert body["low_52w"] == 99.0
    # Volatility over the 1y window: returns are uniformly +1/100 per day,
    # so the sample variance is a known small value; just check plausibility
    # and the exact value for a tiny deterministic series below.
    assert body["volatility_1y_pct"] is not None
    assert body["volatility_1y_pct"] > 0


async def test_performance_volatility_exact_small_series(client, session_factory):
    """Three closes 100 -> 90 -> 110: two returns, one variance degree of
    freedom. Expected = stdev([-0.10, +0.10]) * sqrt(252) * 100."""
    async with session_factory() as session:
        session.add(Stock(symbol="VOL.NS", name="Vol", sector="X", industry="Y"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == "VOL.NS"))
        end = date.today()
        for i, close in enumerate([100.0, 90.0, 110.0]):
            session.add(
                DailyPrice(
                    stock_id=stock.id, date=end - timedelta(days=2 - i),
                    open=close, high=close, low=close, close=close, volume=10,
                )
            )
        await session.commit()

    r = await client.get("/api/v1/stocks/VOL/performance")
    assert r.status_code == 200
    import math

    r1, r2 = -0.10, (110.0 - 90.0) / 90.0
    mean_r = (r1 + r2) / 2
    var = ((r1 - mean_r) ** 2 + (r2 - mean_r) ** 2) / 1
    expected = round(math.sqrt(var) * math.sqrt(252.0) * 100, 2)
    assert r.json()["volatility_1y_pct"] == expected


async def test_performance_volatility_needs_three_closes(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="VOL2.NS", name="Vol2", sector="X", industry="Y"))
        await session.flush()
        stock = await session.scalar(select(Stock).where(Stock.symbol == "VOL2.NS"))
        end = date.today()
        for i, close in enumerate([100.0, 101.0]):
            session.add(
                DailyPrice(
                    stock_id=stock.id, date=end - timedelta(days=1 - i),
                    open=close, high=close, low=close, close=close, volume=10,
                )
            )
        await session.commit()

    r = await client.get("/api/v1/stocks/VOL2/performance")
    assert r.status_code == 200
    assert r.json()["volatility_1y_pct"] is None


async def test_performance_short_history_flags_missing_windows(client, session_factory):
    await _seed_price_bars(session_factory, "RELIANCE.NS", 5)
    r = await client.get("/api/v1/stocks/RELIANCE/performance")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] is False  # enough bars for "today"
    # Five calendar days cannot reach any window anchor: missing, not zero.
    for label in ("1w", "1m", "3m", "6mo", "1y", "2y"):
        assert body["windows"][label]["start_close"] is None
        assert body["windows"][label]["change_pct"] is None


async def test_performance_unknown_symbol_404(client, session_factory):
    r = await client.get("/api/v1/stocks/ZZZ/performance")
    assert r.status_code == 404


# --- /alpha/history -----------------------------------------------------------------


async def test_alpha_history_endpoint(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="RELIANCE.NS", name="Reliance", sector="E", industry="O"))
        session.add_all([
            AlphaScore(
                symbol="RELIANCE.NS", date=date.today() - timedelta(days=2),
                composite=55, fundamental=60, technical=50, sentiment=55,
                components_json={"trend": 50.0},
            ),
            AlphaScore(
                symbol="RELIANCE.NS", date=date.today() - timedelta(days=1),
                composite=59, fundamental=62, technical=51, sentiment=60,
                components_json={"trend": 51.0},
            ),
        ])
        await session.commit()

    r = await client.get("/api/v1/stocks/RELIANCE/alpha/history")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] is False
    assert [i["composite"] for i in body["items"]] == [55.0, 59.0]  # oldest first
    assert body["items"][1]["components"] == {"trend": 51.0}


async def test_alpha_history_empty_is_insufficient(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="NEW.NS", name="New", sector="X", industry="Y"))
        await session.commit()
    r = await client.get("/api/v1/stocks/NEW/alpha/history")
    assert r.status_code == 200
    assert r.json()["insufficient_data"] is True


# --- /technicals/series ---------------------------------------------------------------


async def test_technicals_series_endpoint(client, session_factory):
    await _seed_price_bars(session_factory, "RELIANCE.NS", 40)
    r = await client.get("/api/v1/stocks/RELIANCE/technicals/series")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_data"] is False
    assert len(body["items"]) == 40
    # Warm-up nulls before SMA20/RSI14/MACD windows complete.
    first = body["items"][0]
    assert first["sma20"] is None
    assert first["rsi14"] is None
    assert first["macd"] is None
    last = body["items"][-1]
    assert last["sma20"] is not None
    assert last["rsi14"] is not None
    assert last["macd_histogram"] is not None
    # Values must match the scalar indicators (no duplicated math).
    from app.services import indicators

    closes = [i["close"] for i in body["items"]]
    assert last["sma20"] == indicators.sma(closes, 20)
    assert last["rsi14"] == indicators.rsi(closes, 14)


async def test_technicals_series_unknown_symbol_404(client, session_factory):
    r = await client.get("/api/v1/stocks/ZZZ/technicals/series")
    assert r.status_code == 404


# --- /peers -----------------------------------------------------------------------------


async def test_peers_endpoint(client, session_factory):
    async with session_factory() as session:
        session.add_all([
            Stock(symbol="RELIANCE.NS", name="Reliance", sector="Energy", industry="Refineries"),
            Stock(symbol="IOC.NS", name="Indian Oil", sector="Energy", industry="Refineries"),
            Stock(symbol="TCS.NS", name="TCS", sector="IT", industry="Services"),
        ])
        await session.flush()
        ioc = await session.scalar(select(Stock).where(Stock.symbol == "IOC.NS"))
        rel = await session.scalar(select(Stock).where(Stock.symbol == "RELIANCE.NS"))
        today = date.today()
        session.add_all([
            DailyPrice(stock_id=ioc.id, date=today - timedelta(days=1),
                       open=100, high=105, low=99, close=104, volume=100),
            DailyPrice(stock_id=ioc.id, date=today, open=104, high=106, low=103,
                       close=105, volume=200),
        ])
        session.add(Financials(stock_id=ioc.id, trailing_pe=12.5, return_on_equity=0.15,
                               profit_margin=0.08, debt_to_equity=40.0))
        session.add(Financials(stock_id=rel.id, trailing_pe=24.0))
        await session.commit()

    r = await client.get("/api/v1/stocks/RELIANCE/peers")
    assert r.status_code == 200
    body = r.json()
    assert body["classifier"] == "Refineries"
    assert body["count"] == 1
    peer = body["items"][0]
    assert peer["symbol"] == "IOC.NS"
    assert peer["last_price"] == 105.0
    assert peer["change_pct"] == pytest.approx(0.96, abs=0.01)
    assert peer["trailing_pe"] == 12.5
    assert peer["return_on_equity"] == 0.15
    assert peer["profit_margin"] == 0.08
    assert peer["debt_to_equity"] == 40.0


async def test_peers_no_peers_returns_empty(client, session_factory):
    async with session_factory() as session:
        session.add(Stock(symbol="LONELY.NS", name="Lonely", sector="X", industry="OnlyOne"))
        await session.commit()
    r = await client.get("/api/v1/stocks/LONELY/peers")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["items"] == []

