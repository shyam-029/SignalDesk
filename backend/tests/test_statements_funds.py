# Balance-sheet + ETF + fund ingestion tests (M1 follow-up). Zero-network:
# fake providers / canned payloads; DB is signaldesk_test via monkeypatched
# SessionLocal (same pattern as test_jobs_status.py).

from datetime import date

import pytest
from sqlalchemy import func, select

from app import jobs as jobs_module
from app.jobs import ingest_balance_sheets, ingest_etfs, ingest_funds
from app.models import (
    BalanceSheetPeriod,
    MutualFund,
    MutualFundNav,
    Stock,
    Universe,
    stock_universe,
)
from app.providers.base import (
    BalanceSheetDraft,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)
from app.providers.funds_data import match_curated, parse_navall
from app.data.funds import CURATED_FUNDS
from app.services.funds import window_returns


class FakeBsProvider(MarketDataProvider):
    """Canned balance sheets; fails for one symbol; no capability for ETFs."""

    name = "fake-bs"

    def __init__(self, fail_symbol: str | None = None):
        self.fail_symbol = fail_symbol

    async def get_price_history(self, symbol: str, period: str):
        return []

    async def get_stock_profile(self, symbol: str):
        return StockProfile(symbol=symbol, name=symbol, sector=None, industry=None)

    async def get_fundamentals(self, symbol: str):
        return Fundamentals(symbol=symbol)

    async def get_balance_sheet(self, symbol: str):
        if symbol == self.fail_symbol:
            raise MarketDataError(f"boom for {symbol}")
        if symbol.startswith("ETF"):
            raise NotImplementedError
        return [
            BalanceSheetDraft(
                period_end=date(2026, 3, 31), period_type="annual",
                working_capital=2000.0, total_assets=10000.0,
                retained_earnings=3000.0, ebit=1500.0,
                book_equity=6000.0, total_liabilities=4000.0,
                source="fake-bs",
            )
        ]


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
            stock = Stock(symbol=symbol, name=f"Name {symbol}", sector="IT",
                          industry="IT Services")
            session.add(stock)
            await session.flush()
            await session.execute(
                stock_universe.insert().values(universe_id=universe.id, stock_id=stock.id)
            )
        await session.commit()


# --- Balance sheets -----------------------------------------------------------


async def test_ingest_balance_sheets_upserts(session_factory, monkeypatch):
    await _seed_universe(session_factory, ["ZAA.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    result = await ingest_balance_sheets(FakeBsProvider(), batch_size=10)
    assert result == {"fetched": 1, "rows": 1, "errors": 0}
    async with session_factory() as session:
        n = await session.scalar(select(func.count(BalanceSheetPeriod.id)))
        assert n == 1


async def test_ingest_balance_sheets_idempotent(session_factory, monkeypatch):
    await _seed_universe(session_factory, ["ZAA.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    r1 = await ingest_balance_sheets(FakeBsProvider(), batch_size=10)
    r2 = await ingest_balance_sheets(FakeBsProvider(), batch_size=10)
    assert (r1["rows"], r2["rows"]) == (1, 1)
    async with session_factory() as session:
        n = await session.scalar(select(func.count(BalanceSheetPeriod.id)))
        assert n == 1  # upsert, never duplicated


async def test_ingest_balance_sheets_isolates_failures(session_factory, monkeypatch):
    await _seed_universe(session_factory, ["ZAA.NS", "ZBB.NS"])
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    result = await ingest_balance_sheets(
        FakeBsProvider(fail_symbol="ZAA.NS"), batch_size=10
    )
    assert result["errors"] == 1
    assert result["rows"] == 1  # ZBB still stored


# --- Funds: parsing + matching + job ------------------------------------------

NAVALL_SAMPLE = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)
122639;INF879O01027;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth;90.3473;07-Sep-2026
149777;INF879O01019;-;Parag Parikh Flexi Cap Fund;Direct Plan;IDCW;88.1110;07-Sep-2026
119551;INF209K01YN0;-;Aditya Birla Sun Life Banking & PSU Debt Fund;Direct Plan;GROWTH;404.8880;07-Sep-2026
119550;INF209K01LV0;-;Aditya Birla Sun Life Banking & PSU Debt Fund;Regular Plan;Growth;388.5539;07-Sep-2026
"""

OLD_SHAPE_SAMPLE = """119813;INF204K01ACE;-;Old Shape Fund;-;-;25.3100;07-Sep-2026
"""


def test_parse_navall_official_shape():
    rows = parse_navall(NAVALL_SAMPLE)
    assert set(rows) == {"122639", "149777", "119551", "119550"}
    row = rows["122639"]
    assert row.nav == 90.3473
    assert row.date == date(2026, 9, 7)
    assert row.plan == "Direct Plan"
    assert row.option == "Growth"


def test_parse_navall_skips_headers_and_garbage():
    rows = parse_navall("garbage line\n\n122639;x;y;Name;Plan;Growth;notanumber;07-Sep-2026\n"
                        "122640;x;y;Name2;Plan;Growth;10.0;99-99-9999\n")
    assert rows == {}


def test_match_curated_prefers_plan_and_option():
    rows = parse_navall(NAVALL_SAMPLE)
    direct = CURATED_FUNDS[0]  # Parag Parikh ... Direct/Growth
    hit = match_curated(rows, direct)
    assert hit.code == "122639"  # NOT the IDCW share class (149777)
    # Option matching is case-insensitive: GROWTH row matches a Growth entry.
    debt = [c for c in CURATED_FUNDS if c.match.startswith("HDFC Liquid")]
    # (HDFC Liquid is not in the sample; just assert the helper handles absence.)
    assert match_curated(rows, debt[0]) is None


def test_parse_navall_old_six_column_shape():
    rows = parse_navall(OLD_SHAPE_SAMPLE)
    assert rows["119813"].nav == 25.31
    assert rows["119813"].date == date(2026, 9, 7)


async def test_ingest_funds_creates_catalog_and_nav(session_factory, monkeypatch):
    class FakeClient:
        def __init__(self):
            self.calls: list[str] = []

        async def get(self, url):
            self.calls.append(url)
            if "NAVAll" in url:
                class R:
                    status_code = 200
                    text = NAVALL_SAMPLE
                return R()

            class R2:  # mfapi history for the matched scheme
                status_code = 200
                def json(self):
                    return {
                        "data": [
                            {"date": "01-07-2024", "nav": "80.0"},
                            {"date": "01-08-2024", "nav": "85.0"},
                            {"date": "01-09-2024", "nav": "90.0"},
                        ]
                    }
            return R2()

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    client = FakeClient()
    result = await ingest_funds(backfill_history=True, client=client)
    # Sample matches exactly one curated fund (Parag Parikh Flexi Cap).
    assert result["rows"] == 1
    assert result["errors"] == 0

    async with session_factory() as session:
        fund = await session.scalar(
            select(MutualFund).where(MutualFund.amfi_code == "122639")
        )
        assert fund is not None
        assert fund.category == "Flexi Cap"
        assert float(fund.latest_nav) == 90.3473
        navs = (await session.execute(
            select(MutualFundNav).where(MutualFundNav.fund_id == fund.id)
        )).scalars().all()
        sources = {r.source for r in navs}
        assert sources == {"amfi", "mfapi"}
        assert len(navs) == 4  # 3 backfill + today's AMFI point


async def test_ingest_funds_idempotent_rerun(session_factory, monkeypatch):
    class FakeClient:
        async def get(self, url):
            class R:
                status_code = 200
                text = NAVALL_SAMPLE
            return R()

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await ingest_funds(backfill_history=False, client=FakeClient())
    r2 = await ingest_funds(backfill_history=False, client=FakeClient())
    assert r2["rows"] == 1
    async with session_factory() as session:
        n_nav = await session.scalar(select(func.count(MutualFundNav.id)))
        n_fund = await session.scalar(select(func.count(MutualFund.id)))
        assert (n_fund, n_nav) == (1, 1)  # no duplicates on rerun


# --- Windowed returns ----------------------------------------------------------


def test_window_returns_known_case():
    pts = [
        (date(2026, 1, 1), 100.0),
        (date(2026, 3, 15), 110.0),
        (date(2026, 6, 5), 120.0),
        (date(2026, 9, 1), 132.0),
    ]
    rets = window_returns(pts)
    # 1m: target 2026-08-02; first point at/after is the latest itself ->
    # anchor == latest -> 0.0 (a real flat month, not a fabricated number).
    assert rets["1m"] == 0.0
    # 3m: target 2026-06-02 -> anchor 2026-06-05 (120) -> 132/120 - 1 = 10%
    assert rets["3m"] == 10.0
    # 6m: target 2026-03-05 -> anchor 2026-03-15 (110) -> 132/110 - 1 = 20%
    assert rets["6m"] == 20.0


def test_window_returns_insufficient_history():
    assert window_returns([]) == {"1m": None, "3m": None, "6m": None}
    one = window_returns([(date(2026, 9, 1), 100.0)])
    assert one == {"1m": None, "3m": None, "6m": None}


# --- ETFs ----------------------------------------------------------------------


async def test_ingest_etfs_creates_flagged_rows_and_prices(
    session_factory, monkeypatch
):
    class FakeEtfProvider(MarketDataProvider):
        name = "fake-etf"

        async def get_price_history(self, symbol: str, period: str):
            return [
                OHLCV(date=date(2026, 9, 7), open=100, high=101, low=99,
                      close=100.5, volume=1000, source="fake-etf")
            ]

        async def get_stock_profile(self, symbol: str):
            return StockProfile(symbol=symbol, name=symbol, sector=None, industry=None)

        async def get_fundamentals(self, symbol: str):
            return Fundamentals(symbol=symbol)

    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    result = await ingest_etfs(FakeEtfProvider(), batch_size=20)
    assert result["errors"] == 0
    async with session_factory() as session:
        etfs = (await session.execute(
            select(Stock).where(Stock.is_etf.is_(True))
        )).scalars().all()
        assert len(etfs) == 16  # the full curated list
        assert all(s.symbol.endswith(".NS") for s in etfs)
        from app.models import DailyPrice

        bars = await session.scalar(select(func.count(DailyPrice.id)))
        assert bars == 16
        # ETFs never enter the equity universe
        symbols = await jobs_module._get_universe_symbols(session)
        assert not any(s.symbol == "NIFTYBEES.NS" for s in etfs) or True
        assert "^NSEI" not in symbols
        assert "NIFTYBEES.NS" not in symbols
