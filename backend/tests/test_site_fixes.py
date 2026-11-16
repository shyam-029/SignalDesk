# Fixes from the owner's site review (2026-11-16): the P/E cliff from a one-off
# gain, the Alpha line mixing two methods, search order, the company-size
# filter and the separate mutual fund run. Zero network; signaldesk_test only.

from datetime import date

import pytest
from sqlalchemy import select

import app.jobs as jobs_module
from app.models import AlphaScore, Financials, Stock, Universe, stock_universe
from app.repositories import alpha as alpha_repo
from app.repositories import stocks as stocks_repo
from app.services import depth, screener_cache
from app.services.alpha import _renormalized


# --- P/E: a year lifted by a one-off gain -------------------------------------


def _year(y: int, revenue: float, net: float, op_margin: float | None) -> depth.AnnualFacts:
    return depth.AnnualFacts(
        period_end=date(y, 3, 31), net_income=net, revenue=revenue, operating_margin=op_margin
    )


def test_a_one_off_gain_year_is_replaced_by_an_underlying_estimate():
    # ITC's stored figures (Cr): the year to March 2025 carried a demerger gain.
    facts = [
        _year(2023, 70245, 19192, 0.340190),
        _year(2024, 67391, 20459, 0.351226),
        _year(2025, 74653, 34747, 0.324073),
        _year(2026, 78213, 20689, 0.327253),
    ]
    out, adjusted = depth.underlying_earnings(facts)
    assert adjusted == [date(2025, 3, 31)]
    fixed = {f.period_end.year: f.net_income for f in out}
    # In line with the years either side, not 34,747.
    assert 18_500 < fixed[2025] < 21_500
    assert fixed[2023] == 19192 and fixed[2024] == 20459 and fixed[2026] == 20689


def test_normal_years_and_holding_companies_are_left_alone():
    steady = [_year(y, 1000, 150, 0.20) for y in (2023, 2024, 2025, 2026)]
    assert depth.underlying_earnings(steady) == (steady, [])
    # Profit above operating profit EVERY year (investment income): its usual
    # ratio, so no year is singled out.
    holding = [_year(y, 1000, 400, 0.20) for y in (2023, 2024, 2025, 2026)]
    assert depth.underlying_earnings(holding)[1] == []
    # No operating margin stored (banks), or too few other years: untouched.
    bank = [_year(y, 1000, 900 if y == 2025 else 150, None) for y in (2023, 2024, 2025)]
    assert depth.underlying_earnings(bank)[1] == []
    short = [_year(2025, 1000, 900, 0.2), _year(2026, 1000, 150, 0.2)]
    assert depth.underlying_earnings(short)[1] == []


# --- Company size ---------------------------------------------------------------


def test_cap_sizes_follow_market_value_rank():
    caps = {f"S{i:04d}": float(10_000 - i) for i in range(400)}
    caps["NOCAP"] = None
    sizes = screener_cache.cap_sizes(caps)
    assert sizes["S0000"] == "large" and sizes["S0099"] == "large"
    assert sizes["S0100"] == "mid" and sizes["S0249"] == "mid"
    assert sizes["S0250"] == "small" and sizes["S0399"] == "small"
    assert "NOCAP" not in sizes


async def _universe(session, rows: list[tuple[str, str, float | None]]):
    uni = Universe(name="top1000")
    session.add(uni)
    await session.flush()
    for symbol, name, cap in rows:
        stock = Stock(symbol=symbol, name=name, sector="Industrials")
        session.add(stock)
        await session.flush()
        await session.execute(stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id))
        if cap is not None:
            session.add(Financials(stock_id=stock.id, market_cap=cap))
    await session.commit()


async def test_screener_filters_by_company_size(client, session_factory):
    screener_cache.reset_cache()
    async with session_factory() as session:
        await _universe(session, [(f"S{i:03d}.NS", f"Company {i}", float(1000 - i)) for i in range(260)])
    large = (await client.get("/api/v1/screener?cap=large&limit=250")).json()
    mid = (await client.get("/api/v1/screener?cap=mid&limit=250")).json()
    small = (await client.get("/api/v1/screener?cap=small&limit=250")).json()
    assert (large["total"], mid["total"], small["total"]) == (100, 150, 10)
    assert {i["cap_size"] for i in large["items"]} == {"large"}
    assert (await client.get("/api/v1/screener?cap=huge")).status_code in (400, 422)
    screener_cache.reset_cache()


# --- Search: biggest company first ---------------------------------------------


async def test_search_lists_the_biggest_company_first(session_factory):
    async with session_factory() as session:
        await _universe(
            session,
            [
                ("TATACHEM.NS", "Tata Chemicals", 25_000.0),
                ("TCS.NS", "Tata Consultancy Services", 1_200_000.0),
                ("TATAMOTORS.NS", "Tata Motors", 300_000.0),
                ("TATAELXSI.NS", "Tata Elxsi", None),
                ("TATA.NS", "Tata Tiny Exact Symbol", 10.0),
            ],
        )
        hits = [s.symbol for s in await stocks_repo.search_universe(session, "tata")]
    # The exact symbol first, then by market value, then the one with none.
    assert hits == ["TATA.NS", "TCS.NS", "TATAMOTORS.NS", "TATACHEM.NS", "TATAELXSI.NS"]


# --- Alpha history: one method for the whole line -------------------------------


async def test_live_snapshots_are_reblended_with_that_days_strength(session_factory):
    day_old, day_new, day_unranked = date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 10)
    async with session_factory() as session:
        for day in (day_old, day_new, day_unranked):
            # Old-method composite (technical pillar): far above the new one.
            session.add(AlphaScore(
                symbol="ITC.NS", date=day, composite=80, fundamental=100, technical=73,
                sentiment=50, components_json={"trend": 70.0},
            ))
        # A technical-only (backfilled) row is not this function's business.
        session.add(AlphaScore(symbol="ITC.NS", date=date(2026, 11, 11), composite=62, technical=73))
        await session.commit()

        strength = {day_old: 16.0, day_new: 15.3}
        changed = await alpha_repo.reblend_live_snapshots(session, "ITC.NS", strength, _renormalized)
        assert changed == 2
        rows = {
            r.date: r
            for r in (await session.execute(select(AlphaScore).where(AlphaScore.symbol == "ITC.NS"))).scalars()
        }
    expected, _ = _renormalized(100.0, 16, 50.0)
    assert float(rows[day_old].composite) == expected and expected < 80
    assert rows[day_old].components_json["strength"] == 16.0
    assert rows[day_old].components_json["trend"] == 70.0  # other components kept
    assert float(rows[day_old].fundamental) == 100  # that day's own scores kept
    assert float(rows[day_unranked].composite) == 80  # no Strength that day: untouched
    assert float(rows[date(2026, 11, 11)].composite) == 62
    async with session_factory() as session:
        # Idempotent: a second run changes nothing.
        assert await alpha_repo.reblend_live_snapshots(session, "ITC.NS", strength, _renormalized) == 0


# --- The mutual fund run is separate from the stock nightly ---------------------


async def test_fund_passes_run_on_their_own_and_not_in_the_stock_nightly(monkeypatch):
    ran: list[str] = []

    async def fake_record(name, run, *args, **kwargs):
        ran.append(name)
        return "success"

    monkeypatch.setattr(jobs_module, "_record_pass", fake_record)
    result = await jobs_module._funds_passes()
    assert ran == ["ingest_funds", jobs_module.FUNDS_DB_JOB]
    assert result["errors"] == 0

    ran.clear()

    async def always_due(*args, **kwargs):
        return False

    monkeypatch.setattr(jobs_module, "_pass_due", always_due)
    monkeypatch.setattr(jobs_module, "_alpha_full_backfill_due", always_due)
    await jobs_module._ingest_passes()
    assert "ingest_funds" not in ran and jobs_module.FUNDS_DB_JOB not in ran
    assert "ingest_prices" in ran and "ingest_etfs" in ran


def test_ownership_fill_covers_the_list_in_three_nights():
    assert jobs_module.SHAREHOLDING_NIGHTLY_CAP * 3 >= jobs_module.RANKED_SIZE
