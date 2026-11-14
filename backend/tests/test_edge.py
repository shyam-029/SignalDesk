# Edge features (2026-11-14): what the price assumes, similar setups with
# the Strength back-test, and the frozen monthly lists of the track record.
# Zero network; the database tests run against signaldesk_test.

import random
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from sqlalchemy import select

import app.jobs as jobs_module
from app.models import AlphaScore, DailyPrice, PickList, Stock, Universe, stock_universe
from app.repositories import edge as edge_repo
from app.repositories import strength as strength_repo
from app.routers import edge as edge_router
from app.services import expectations as exp
from app.services import setups
from app.services import strength as strength_svc


@pytest.fixture(autouse=True)
def _reset_edge_caches():
    edge_repo.reset_cache()
    edge_router.reset_cache()
    yield
    edge_repo.reset_cache()
    edge_router.reset_cache()


# --- What the price assumes ----------------------------------------------------


def test_implied_growth_reproduces_the_market_value():
    for value in (5_000.0, 15_000.0, 40_000.0):
        got = exp.implied_growth(value, 1_000.0, 0.12)
        assert got.bound is None
        assert exp.present_value(1_000.0, got.growth, 0.12) == pytest.approx(value, rel=1e-4)


def test_more_expensive_means_more_growth_needed_and_a_higher_rate_too():
    cheap = exp.implied_growth(15_000.0, 1_000.0, 0.12).growth
    dear = exp.implied_growth(30_000.0, 1_000.0, 0.12).growth
    assert dear > cheap
    assert exp.implied_growth(30_000.0, 1_000.0, 0.13).growth > dear


def test_no_growth_price_is_about_eleven_times_earnings():
    # r 12%, 6% after ten years: zero growth is worth about 11.3 times earnings.
    assert exp.present_value(1.0, 0.0, 0.12) == pytest.approx(11.34, abs=0.05)
    assert abs(exp.implied_growth(11.34, 1.0, 0.12).growth) < 0.002


def test_out_of_range_prices_are_reported_as_bounds():
    assert exp.implied_growth(0.5, 1.0, 0.12).bound == "below"
    assert exp.implied_growth(1e12, 1.0, 0.12).bound == "above"


def test_trailing_earnings_prefers_four_consecutive_quarters():
    q = [
        exp.Quarter(date(2025, 12, 31), 10.0),
        exp.Quarter(date(2026, 3, 31), 20.0),
        exp.Quarter(date(2026, 6, 30), 30.0),
        exp.Quarter(date(2026, 9, 30), 40.0),
    ]
    a = [exp.Annual(date(2026, 3, 31), 70.0, 500.0)]
    assert exp.trailing_earnings(q, a) == (100.0, "last_4_quarters", date(2026, 9, 30))
    # A missing quarter breaks the run: fall back to the latest annual figure.
    gappy = [q[0], q[1], q[3], exp.Quarter(date(2026, 12, 31), 50.0)]
    assert exp.trailing_earnings(gappy, a) == (70.0, "latest_annual", date(2026, 3, 31))


def test_own_record_skips_empty_years():
    annuals = [
        exp.Annual(date(2022, 3, 31), None, None),
        exp.Annual(date(2023, 3, 31), 100.0, 1000.0),
        exp.Annual(date(2024, 3, 31), 110.0, 1100.0),
        exp.Annual(date(2026, 3, 31), 133.1, 1331.0),
    ]
    own = exp.own_record(annuals)
    assert own.years == 3
    assert own.from_year_end == date(2023, 3, 31)
    assert own.earnings_growth == pytest.approx(0.10, abs=1e-6)
    assert own.revenue_growth == pytest.approx(0.10, abs=1e-6)


def test_growth_windows_pair_reports_three_years_apart_and_skip_losses():
    rows = [
        (1, date(2023, 3, 31), 100.0, 1000.0),
        (1, date(2024, 3, 31), 120.0, 1100.0),
        (1, date(2026, 3, 31), 172.8, 1331.0),
        (2, date(2023, 3, 31), -5.0, 500.0),  # a loss start: no earnings rate
        (2, date(2026, 3, 31), 50.0, 500.0),
    ]
    earnings, revenue = exp.growth_windows(rows, years=3)
    assert earnings == [pytest.approx(0.2, abs=1e-6)]
    assert sorted(revenue) == [pytest.approx(0.0), pytest.approx(0.1, abs=1e-6)]


def test_assess_explains_instead_of_guessing():
    a = [exp.Annual(date(2026, 3, 31), -10.0, 100.0)]
    assert exp.assess(1_000.0, [], a, []).reason == exp.REASON_LOSS
    assert exp.assess(None, [], a, []).reason == exp.REASON_NO_MARKET_VALUE
    assert exp.assess(1_000.0, [], [], []).reason == exp.REASON_NO_EARNINGS
    ok = exp.assess(2_000.0, [], [exp.Annual(date(2026, 3, 31), 100.0, 900.0)], [0.5] * 300)
    assert ok.status == "ok" and ok.pe == 20.0
    assert [i.rate for i in ok.implied] == list(exp.DISCOUNT_RATES)
    assert ok.base_rate_share == 1.0  # every window grew 50%, more than needed


# --- Similar setups and the back-test -------------------------------------------

N_STOCKS = 30


def _trading_days(n: int, end: date) -> list[date]:
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def _walks(n_bars: int, seed: int = 3) -> dict[str, list[float]]:
    rng = random.Random(seed)
    out = {}
    for i in range(N_STOCKS):
        price, closes = 100.0, []
        drift = rng.uniform(-0.002, 0.003)
        for _ in range(n_bars):
            price *= 1.0 + drift + rng.uniform(-0.025, 0.025)
            closes.append(round(price, 2))
        out[f"S{i:02d}.NS"] = closes
    return out


def _series(walks, days):
    return {s: (days, np.array(c)) for s, c in walks.items()}


def test_forward_returns_count_from_the_next_day_and_skip_bad_data():
    days = _trading_days(400, date(2026, 11, 13))
    closes = np.linspace(100.0, 200.0, 400)
    p = setups._Prepared(days, closes)
    assert p.ret(10, 20) == pytest.approx(closes[20] / closes[10] - 1.0)
    assert p.ret(390, 450) is None  # past the data
    jumpy = closes.copy()
    jumpy[15:] *= 2.0  # an unadjusted 1:2 split inside the window
    assert setups._Prepared(days, jumpy).ret(10, 20) is None


async def test_setups_rank_today_exactly_as_the_nightly_pass(session_factory):
    """The weekly pass's Strength for the newest day must equal the nightly
    rating computed in SQL from the same closes."""
    n_bars = strength_svc.HISTORY_BARS + 60
    today = date.today()
    days = _trading_days(n_bars, today)
    walks = _walks(n_bars)
    async with session_factory() as session:
        uni = Universe(name=jobs_module.UNIVERSE_NAME)
        session.add(uni)
        stocks = [Stock(symbol=s, name=s) for s in walks]
        session.add_all(stocks)
        await session.flush()
        for stock in stocks:
            await session.execute(
                stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id)
            )
            for d, c in zip(days, walks[stock.symbol]):
                session.add(DailyPrice(
                    stock_id=stock.id, date=d, open=c, high=c, low=c, close=c, volume=1,
                ))
        await session.commit()
        facts = await strength_repo.get_price_facts(session, days[-1], jobs_module.UNIVERSE_NAME)
    inputs = {}
    for s, f in facts.items():
        got, _ = strength_svc.inputs_for(f, days[-1])
        if got is not None:
            inputs[s] = got
    nightly = strength_svc.rate_list(inputs)

    _, by_day = setups.build_samples(_series(walks, days))
    weekly = {s.symbol: s for s in by_day[days[-1]]}
    assert set(weekly) == set(nightly)
    for symbol, rating in nightly.items():
        assert weekly[symbol].strength == rating.strength
        assert weekly[symbol].steadiness == pytest.approx(rating.steadiness)


def test_similar_leaves_out_the_share_own_recent_past_and_takes_k():
    n_bars = strength_svc.HISTORY_BARS + 420
    days = _trading_days(n_bars, date(2026, 11, 13))
    _, by_day = setups.build_samples(_series(_walks(n_bars), days))
    table = setups.sample_table(by_day)
    today = days[-1]
    got = setups.similar(table, "S00.NS", today, (50.0, 50.0, 50.0), k=25)
    for h in ("3m", "12m"):
        assert got[h]["n"] <= 25
    # With k larger than every completed case, the only ones left out are
    # S00's own month-ends from the past year.
    every = setups.similar(table, "S00.NS", today, (50.0, 50.0, 50.0), k=10_000)
    done = ~np.isnan(table.forward["3m"])
    cutoff = np.datetime64(today) - np.timedelta64(setups.OWN_EXCLUSION_DAYS, "D")
    own = (table.symbols == "S00.NS") & (table.days >= cutoff)
    assert every["3m"]["n"] == int((done & ~own).sum())
    assert (done & own).sum() > 0


def test_backtest_picks_the_strongest_and_compares_with_the_list():
    def sample(sym, strength, nxt):
        return setups.Sample(sym, date(2026, 1, 30), strength, 50.0, 50.0, 0.0, 0.0, {}, nxt)

    day = date(2026, 1, 30)
    group = [sample(f"X{i:03d}.NS", float(i), 0.10 if i >= 180 else 0.0) for i in range(200)]
    bt = setups.strength_backtest([day], {day: group}, top_n=20)
    assert bt["months_count"] == 1 and bt["months_beat"] == 1
    assert bt["latest_picks"][0] == "X199.NS"
    m = bt["curve"][0]
    assert m["top"] == pytest.approx(1.10)
    assert m["list"] == pytest.approx(1.01)
    assert bt["quintiles"][-1] > bt["quintiles"][0]


def test_setups_rows_shape_and_stale_guard():
    n_bars = strength_svc.HISTORY_BARS + 300
    end = date(2026, 11, 13)
    days = _trading_days(n_bars, end)
    rows, facts = jobs_module.setups_rows(_series(_walks(n_bars), days), end)
    keys = {k for k, _, _ in rows}
    assert edge_repo.SETUPS_BASELINE_KEY in keys
    assert edge_repo.STRENGTH_BACKTEST_KEY in keys
    assert sum(k.startswith("setups:") for k in keys) > 20
    stale, _ = jobs_module.setups_rows(_series(_walks(n_bars), days), end + timedelta(days=30))
    assert stale == []


# --- Storage, frozen lists and the endpoints ------------------------------------


async def test_snapshots_are_not_rewritten_when_unchanged(session_factory):
    rows = [("setups:A.NS", date(2026, 11, 13), {"x": 1}), ("k2", date(2026, 11, 13), {"y": 2})]
    async with session_factory() as session:
        assert await edge_repo.upsert_snapshots(session, rows) == 2
        assert await edge_repo.upsert_snapshots(session, rows) == 0
        changed = [("k2", date(2026, 11, 14), {"y": 3})]
        assert await edge_repo.upsert_snapshots(session, changed) == 1
        snap = await edge_repo.get_snapshot(session, "k2")
        assert snap.payload == {"y": 3} and snap.asof == date(2026, 11, 14)


async def _seed_scores(session_factory, day: date, n: int = 25):
    async with session_factory() as session:
        uni = Universe(name=edge_repo.UNIVERSE_NAME)
        session.add(uni)
        for i in range(n):
            stock = Stock(symbol=f"P{i:02d}.NS", name=f"P{i:02d}")
            session.add(stock)
            await session.flush()
            await session.execute(
                stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id)
            )
            for k, d in enumerate((day, day + timedelta(days=3), day + timedelta(days=10))):
                close = 100.0 * (1 + 0.01 * i) ** k
                session.add(DailyPrice(
                    stock_id=stock.id, date=d, open=close, high=close, low=close,
                    close=close, volume=1,
                ))
            session.add(AlphaScore(
                symbol=stock.symbol, date=day, composite=float(i), fundamental=50,
                sentiment=50, components_json={"strength": float(n - i)},
            ))
        await session.commit()


async def test_lists_are_frozen_once_a_month(session_factory, monkeypatch):
    day = date(2026, 11, 2)
    await _seed_scores(session_factory, day)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    first = await jobs_module.freeze_pick_lists()
    assert first == {"fetched": 40, "errors": 0}
    again = await jobs_module.freeze_pick_lists()
    assert again == {"fetched": 0, "errors": 0}
    async with session_factory() as session:
        rows = (await session.execute(
            select(PickList).order_by(PickList.rating, PickList.rank)
        )).scalars().all()
    alpha = [r.symbol for r in rows if r.rating == "alpha"]
    strength = [r.symbol for r in rows if r.rating == "strength"]
    assert alpha[0] == "P24.NS" and len(alpha) == 20  # highest composite first
    assert strength[0] == "P00.NS"  # highest Strength first
    assert float(rows[0].entry_close) == pytest.approx(100.0)


async def test_track_record_counts_from_the_next_close(client, session_factory, monkeypatch):
    day = date(2026, 11, 2)
    await _seed_scores(session_factory, day)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await jobs_module.freeze_pick_lists()
    body = (await client.get("/api/v1/track-record")).json()
    assert body["backtest"] is None
    assert len(body["lists"]) == 2 and body["lists"][0]["rating"] == "alpha"
    top = body["lists"][0]["holdings"][0]
    assert top["symbol"] == "P24.NS"
    assert top["entry_date"] == str(day + timedelta(days=3))
    # Entry is the day-3 close (1.24x), latest the day-10 close (1.24^2 x).
    assert top["return_pct"] == pytest.approx(24.0, abs=0.01)
    assert body["lists"][0]["list_average_pct"] is not None


def test_shape_lists_marks_unstarted_lists():
    row = SimpleNamespace(
        list_date=date(2026, 12, 1), rating="strength", rank=1, symbol="A.NS", score=99,
        name="A", entry_date=None, entry_close=None, last_date=date(2026, 12, 1),
        last_close=10.0,
    )
    lists, latest = edge_router.shape_lists({"picks": [row], "averages": {}, "index": {}})
    assert lists[0].started is False and lists[0].return_pct is None
    assert latest == date(2026, 12, 1)


async def test_expectations_and_setups_endpoints(client, seeded, session_factory):
    from app.models import Financials, FinancialPeriod

    async with session_factory() as session:
        rel = await session.scalar(select(Stock).where(Stock.symbol == "RELIANCE.NS"))
        session.add(Financials(stock_id=rel.id, market_cap=2_000_000))
        session.add(FinancialPeriod(
            stock_id=rel.id, period_end=date(2026, 3, 31), period_type="annual",
            net_income=100_000, revenue=900_000, source="test",
        ))
        await session.commit()
    body = (await client.get("/api/v1/stocks/RELIANCE/expectations")).json()
    assert body["status"] == "ok" and body["pe"] == 20.0
    assert [i["discount_rate_pct"] for i in body["implied"]] == [11.0, 12.0, 13.0]
    assert body["base_rate_pct"] is None  # too few company records

    none = (await client.get("/api/v1/stocks/RELIANCE/setups")).json()
    assert none["status"] == "none"
    async with session_factory() as session:
        await edge_repo.upsert_snapshots(session, [
            ("setups:RELIANCE.NS", date(2026, 11, 13), {
                "asof": "2026-11-13",
                "today": {"strength": 60.0, "steadiness": 70.0, "high_rank": 55.0,
                          "year_return_pct": 12.0, "from_high_pct": -5.0},
                "horizons": {"3m": {"n": 200, "median": 2.0, "from": "2018-01-31"},
                             "12m": {"n": 0}},
            }),
            ("setups_baseline", date(2026, 11, 13), {
                "samples": 1000, "shares": 900, "from": "2017-11-30", "to": "2026-11-13",
                "neighbours": 200, "horizons": {"3m": {"n": 1000}, "12m": {"n": 900}},
            }),
        ])
    body = (await client.get("/api/v1/stocks/RELIANCE/setups")).json()
    assert body["status"] == "ok"
    three = body["horizons"][0]
    assert three["horizon"] == "3m" and three["similar"]["from_"] == "2018-01-31"
    assert body["horizons"][1]["similar"]["n"] == 0
