# Funds database ingestion and API (2026-11-14): the AMFI catalog parser,
# packed NAV history, returns worked out inside the database, the nightly
# pass end to end against fake AMFI/mfapi responses, and /funds served from
# the funds database. Database tests use the local signaldesk_funds_test
# copy and are skipped when it does not exist.

from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.jobs as jobs_module
from app.config import settings
from app.funds_db import session as funds_session
from app.funds_db.models import Fund, FundReturns, FundsBase, NavHistory
from app.repositories import funds_db as fdb
from app.routers import funds as funds_router
from app.services import fund_catalog as cat
from app.services.fund_nav import pack, unpack
from app.services.funds import window_returns

FUNDS_TEST_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/signaldesk_funds_test"
TODAY = date(2026, 11, 13)


def _amfi(today: date = TODAY) -> str:
    d = today.strftime("%d-%b-%Y")
    old = (today - timedelta(days=90)).strftime("%d-%b-%Y")
    return "\n".join([
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date",
        "",
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)",
        "",
        "Axis Mutual Fund",
        "",
        f"100001;INF846K01AA1;-;Axis Bluechip Fund;Direct Plan;Growth Option;61.25;{d}",
        f"100002;INF846K01AA2;-;Axis Bluechip Fund;Regular Plan;Growth Option;55.10;{d}",
        f"100003;INF846K01AA3;-;Axis Bluechip Fund;Direct Plan;IDCW Option;20.00;{d}",
        "Open Ended Schemes(Equity Schemes - Large Cap Fund)",
        "HDFC Mutual Fund",
        f"100004;INF179K01AA4;-;HDFC Large Cap Fund - Direct Plan - Growth;-;-;1100.5;{d}",
        f"100005;INF179K01AA5;-;HDFC Large Cap Fund - Regular Plan - Growth;-;-;1000.5;{d}",
        f"100006;INF179K01AA6;-;HDFC Old Fund - Direct Plan - Growth;-;-;10.0;{old}",
        "Open Ended Schemes(Other Scheme - Index Funds)",
        "HDFC Mutual Fund",
        f"100007;INF179K01AA7;-;HDFC Nifty 50 Index Fund;Direct Plan;Growth;200.0;{d}",
        f"100008;INF179K01AA8;-;HDFC CRISIL IBX Gilt June 2027 Index Fund;Direct Plan;Growth;11.0;{d}",
        "Open Ended Schemes(Exchange Traded Funds (ETFs) - Gold ETF)",
        "Nippon India Mutual Fund",
        f"100009;INF204KB17I5;-;Nippon India ETF Gold BeES;-;-;80.5;{d}",
    ])


def test_catalog_keeps_direct_growth_plans_and_etfs_only():
    rows, counts = cat.parse_catalog(_amfi())
    codes = {r.amfi_code: r for r in rows}
    assert set(codes) == {"100001", "100004", "100007", "100008", "100009"}
    assert counts["stale"] == 1  # 100006: last NAV 90 days old
    # Both spellings of the heading land in one category.
    assert codes["100001"].heading.category == codes["100004"].heading.category == "Large Cap Fund"
    assert codes["100001"].fund_house == "Axis Mutual Fund"
    assert codes["100007"].heading.category == "Index Funds"
    assert codes["100007"].heading.asset_group == "equity"
    assert codes["100008"].heading.category == "Debt Index Funds"
    assert codes["100008"].heading.asset_group == "debt"
    assert codes["100009"].heading.fund_kind == "etf"
    assert codes["100009"].heading.category == "Gold ETF"


def test_share_class_from_columns_or_name():
    assert cat.is_direct_growth("X Fund", "Direct Plan", "Growth Option")
    assert not cat.is_direct_growth("X Fund", "Regular Plan", "Growth")
    assert not cat.is_direct_growth("X Fund", "Direct Plan", "IDCW")
    assert cat.is_direct_growth("X Fund - Direct Plan - Growth", None, None)
    assert not cat.is_direct_growth("X Fund - Direct Plan - IDCW Payout", None, None)
    assert not cat.is_direct_growth("X Fund - Growth", None, None)  # no "direct"
    assert cat.fund_house_name("Axis Mutual Fund") == "Axis"


def test_pack_round_trip_by_year():
    pts = [(date(2025, 12, 31), 10.0), (date(2026, 1, 1), 10.5), (date(2026, 1, 2), 0.0),
           (date(2026, 1, 1), 10.6)]
    packed = pack(pts)
    assert packed == {2025: ([365], [10.0]), 2026: ([1], [10.6])}
    assert unpack([(y, d, n) for y, (d, n) in packed.items()]) == [
        (date(2025, 12, 31), 10.0), (date(2026, 1, 1), 10.6)]


@pytest.fixture()
async def funds_factory(monkeypatch):
    monkeypatch.setattr(settings, "funds_database_url", "")
    engine = create_async_engine(FUNDS_TEST_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(FundsBase.metadata.drop_all)
            await conn.run_sync(FundsBase.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"local funds test database unavailable: {type(exc).__name__}")
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    funds_session.set_sessionmaker(factory)
    funds_router.reset_cache()
    yield factory
    funds_session.set_sessionmaker(None)
    funds_router.reset_cache()
    await engine.dispose()


def _history(days_back: int, end_nav: float, step: float = 0.0004):
    """A weekday NAV series ending today at `end_nav` (the AMFI file's NAV)."""
    pts, nav, d = [], 10.0, TODAY - timedelta(days=days_back)
    while d <= TODAY:
        if d.weekday() < 5:
            pts.append((d, nav))
            nav *= 1 + step * (1 if d.day % 3 else -1.5)
        d += timedelta(days=1)
    scale = end_nav / pts[-1][1]
    return [(d, round(n * scale, 4)) for d, n in pts[:-1]] + [(pts[-1][0], end_nav)]


def _mock_client(histories: dict[str, list], refuse: set[str] = frozenset()):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "NAVAll" in url:
            return httpx.Response(200, text=_amfi())
        code = url.rstrip("/").split("/")[-1]
        if code in refuse:
            return httpx.Response(429)
        pts = histories.get(code, [])
        return httpx.Response(200, json={"data": [
            {"date": d.strftime("%d-%m-%Y"), "nav": str(n)} for d, n in reversed(pts)]})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_nightly_pass_end_to_end(funds_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "FUNDS_HISTORY_PAUSE_S", 0)
    long = _history(4000, 61.25)
    histories = {"100001": long, "100004": _history(400, 1100.5), "100007": _history(40, 200.0)}
    monkeypatch.setattr(jobs_module, "FUNDS_MIN_LIVE", 1)
    client = _mock_client(histories, refuse={"100008"})
    result = await jobs_module.sync_funds_db(client=client)
    assert result["fetched"] == 5

    async with funds_factory() as s:
        funds = {f.amfi_code: f for f in (await s.execute(select(Fund))).scalars()}
        assert funds["100001"].launch_date == long[0][0]
        assert funds["100008"].launch_date is None  # refused: loads another night
        hist = unpack(await fdb.get_history(s, funds["100001"].id))
        assert hist[-1] == long[-1] and len(hist) == len(long)
        rets = {r.fund_id: r for r in (await s.execute(select(FundReturns))).scalars()}

    expected = window_returns(long, {"1m": 30, "1y": 365, "3y": 1095, "5y": 1826, "10y": 3652})
    got = rets[funds["100001"].id]
    assert float(got.ret_1m) == pytest.approx(expected["1m"], abs=0.01)
    assert float(got.ret_1y) == pytest.approx(expected["1y"], abs=0.01)
    assert float(got.ret_3y) == pytest.approx(expected["3y"], abs=0.01)
    # window_returns annualises only 1y and 3y; 5y and 10y are yearly rates here.
    def yearly(total_pct, days):
        return ((1 + total_pct / 100) ** (365 / days) - 1) * 100
    assert float(got.ret_5y) == pytest.approx(yearly(expected["5y"], 1826), abs=0.01)
    assert float(got.ret_10y) == pytest.approx(yearly(expected["10y"], 3652), abs=0.01)
    assert got.volatility_pct is not None and float(got.max_drawdown_pct) <= 0
    # A 40-day history has a 1-month return but no 1-year one.
    short = rets[funds["100007"].id]
    assert short.ret_1m is not None and short.ret_1y is None
    # Rank inside "Large Cap Fund": both large-cap funds have a 1y return.
    assert {got.category_rank, rets[funds["100004"].id].category_rank} == {1, 2}
    assert got.category_size == 2

    # A second night appends nothing new and keeps the history intact.
    again = await jobs_module.sync_funds_db(client=_mock_client(histories, refuse={"100008"}))
    assert again["fetched"] == 5
    async with funds_factory() as s:
        rows = (await s.execute(select(NavHistory).where(NavHistory.fund_id == funds["100001"].id))).scalars().all()
        assert sum(len(r.days) for r in rows) == len(long)


async def test_append_is_inside_the_database_and_never_duplicates(funds_factory):
    async with funds_factory() as s:
        s.add(Fund(amfi_code="1", name="A"))
        await s.commit()
        fid = (await s.execute(select(Fund.id))).scalar()
        assert await fdb.append_navs(s, [(fid, TODAY, 10.0)]) == 1
        assert await fdb.append_navs(s, [(fid, TODAY, 10.0)]) == 0
        assert await fdb.append_navs(s, [(fid, TODAY + timedelta(days=1), 10.1)]) == 1
        await s.commit()
        assert unpack(await fdb.get_history(s, fid)) == [(TODAY, 10.0), (TODAY + timedelta(days=1), 10.1)]


async def test_funds_api_from_the_funds_database(client, funds_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "FUNDS_HISTORY_PAUSE_S", 0)
    monkeypatch.setattr(jobs_module, "FUNDS_MIN_LIVE", 1)
    await jobs_module.sync_funds_db(
        client=_mock_client({"100001": _history(800, 61.25), "100004": _history(800, 1100.5)})
    )
    body = (await client.get("/api/v1/funds?asset_group=equity&sort=return_1y&direction=desc")).json()
    assert body["source"] == "funds_db"
    names = [i["name"] for i in body["items"]]
    assert "Axis Bluechip Fund" in names and "Nippon India ETF Gold BeES" not in names
    top = body["items"][0]
    assert top["fund_house"] in ("Axis", "HDFC") and top["category_rank"] == 1

    page = (await client.get("/api/v1/funds?limit=2&offset=2&sort=name")).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    found = (await client.get("/api/v1/funds?q=gold%20bees")).json()
    assert [i["amfi_code"] for i in found["items"]] == ["100009"]

    cats = (await client.get("/api/v1/funds/categories")).json()
    assert {"asset_group": "equity", "category": "Large Cap Fund", "count": 2} in cats["items"]

    fid = next(i["id"] for i in body["items"] if i["amfi_code"] == "100001")
    detail = (await client.get(f"/api/v1/funds/{fid}?window=1y")).json()
    assert detail["fund_house"] == "Axis" and detail["launch_date"] is not None
    assert detail["nav_points"] > 500 and 0 < len(detail["items"]) <= 120
    assert (await client.get("/api/v1/funds/999999")).status_code == 404
    bad = await client.get("/api/v1/funds?asset_group=crypto")
    assert bad.status_code == 422


async def test_an_empty_funds_database_keeps_the_curated_list(client, funds_factory):
    """Before the first nightly fills the funds database, /funds keeps
    serving the old curated list instead of showing no funds."""
    body = (await client.get("/api/v1/funds")).json()
    assert body["source"] == "curated"
    cats = (await client.get("/api/v1/funds/categories")).json()
    assert cats["source"] == "curated"
