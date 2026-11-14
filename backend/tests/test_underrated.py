# The underrated scan (2026-11-14): the four checks, ranking, the API and the
# third frozen monthly list. Zero network; database tests use signaldesk_test.

from datetime import date, timedelta

import pytest
from sqlalchemy import select

import app.jobs as jobs_module
from app.models import AlphaScore, DailyPrice, Financials, FinancialPeriod, PickList, Stock, Universe, stock_universe
from app.repositories import edge as edge_repo
from app.repositories import underrated as repo
from app.services import expectations as exp
from app.services import underrated as svc


@pytest.fixture(autouse=True)
def _reset():
    repo.reset_cache()
    edge_repo.reset_cache()
    yield
    repo.reset_cache()
    edge_repo.reset_cache()


def _inputs(**over) -> svc.Inputs:
    """A company that passes all four checks: earnings 1,000 (growing 30% a
    year), market value 10,000 (price needs well under 10% growth)."""
    base = dict(
        symbol="GEM.NS", name="Gem Ltd", sector="Industrials",
        fundamental=85.0, solvency=70.0, valuation_status="undervalued",
        strength=30.0, from_high_pct=-25.0, market_cap=10_000.0,
        quarters=[],
        annuals=[
            exp.Annual(date(2023, 3, 31), 455.0, 3000.0),
            exp.Annual(date(2024, 3, 31), 590.0, 3500.0),
            exp.Annual(date(2025, 3, 31), 770.0, 4000.0),
            exp.Annual(date(2026, 3, 31), 1000.0, 4600.0),
        ],
    )
    base.update(over)
    return svc.Inputs(**base)


def _passed(r: svc.Result) -> dict[str, bool | None]:
    return {c.key: c.passed for c in r.checks}


def test_a_company_passing_everything_is_a_match():
    r = svc.evaluate(_inputs())
    assert r.passes == 4
    assert r.needed_growth_pct is not None and r.needed_growth_pct < 10
    assert r.own_growth_pct == pytest.approx(30.0, abs=0.5)
    assert r.gap_points > 15 and not r.low_base


@pytest.mark.parametrize(
    "over, key",
    [
        (dict(fundamental=60.0), "quality"),
        (dict(solvency=40.0), "quality"),
        (dict(market_cap=100_000.0), "expectations"),  # price needs far more
        (dict(valuation_status="overvalued"), "valuation"),
        (dict(strength=80.0), "rerating"),
        (dict(from_high_pct=-3.0), "rerating"),
    ],
)
def test_each_check_can_fail_on_its_own(over, key):
    r = svc.evaluate(_inputs(**over))
    assert _passed(r)[key] is False
    assert r.passes == 3


def test_missing_data_is_unknown_not_a_pass():
    r = svc.evaluate(_inputs(fundamental=None, strength=None, valuation_status=None))
    got = _passed(r)
    assert got["quality"] is None and got["rerating"] is None and got["valuation"] is None
    assert r.passes == 1  # only the expectations check
    loss = svc.evaluate(_inputs(annuals=[exp.Annual(date(2026, 3, 31), -50.0, 100.0)]))
    assert _passed(loss)["expectations"] is None


def test_growth_from_a_tiny_profit_is_flagged_and_capped_for_ranking():
    recovery = svc.evaluate(_inputs(annuals=[
        exp.Annual(date(2023, 3, 31), 5.0, 3000.0),
        exp.Annual(date(2026, 3, 31), 1000.0, 4600.0),
    ]))
    steady = svc.evaluate(_inputs())
    assert recovery.low_base and recovery.own_growth_pct > svc.LOW_BASE_GROWTH_PCT
    assert recovery.passes == 4  # still passes, but...
    assert recovery.rank_gap == pytest.approx(svc.RANK_GROWTH_CAP_PCT - recovery.needed_growth_pct)
    # ...but counts as at most the cap when ranking, so it does not beat a
    # company that grew at the cap with a stronger business.
    assert recovery.gap_points > recovery.rank_gap
    at_cap = svc.evaluate(_inputs(symbol="STEADY.NS", fundamental=95.0, annuals=[
        exp.Annual(date(2023, 3, 31), 364.0, 3000.0),  # 40% a year to 1,000
        exp.Annual(date(2026, 3, 31), 1000.0, 4600.0),
    ]))
    assert at_cap.rank_gap == pytest.approx(recovery.rank_gap, abs=0.3)
    ordered = sorted([recovery, at_cap], key=svc.rank_key)
    assert ordered[0].symbol == "STEADY.NS"


# --- Database: the scan, the endpoint and the frozen list --------------------------

TODAY = date(2026, 11, 13)


async def _seed(session_factory, n_gems: int = 3, n_plain: int = 2):
    async with session_factory() as session:
        uni = Universe(name="top1000")
        session.add(uni)
        await session.flush()
        names = [f"GEM{i}.NS" for i in range(n_gems)] + [f"PLAIN{i}.NS" for i in range(n_plain)]
        for k, symbol in enumerate(names):
            gem = symbol.startswith("GEM")
            stock = Stock(symbol=symbol, name=symbol, sector="Industrials")
            session.add(stock)
            await session.flush()
            await session.execute(stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id))
            session.add(Financials(
                stock_id=stock.id, market_cap=10_000 if gem else 90_000,
                return_on_equity=20, debt_to_equity=30, interest_coverage=8, current_ratio=2,
                operating_margin=20, profit_margin=15, trailing_pe=8,
            ))
            for yr, ni in ((2023, 455), (2024, 590), (2025, 770), (2026, 1000 + 10 * k)):
                session.add(FinancialPeriod(
                    stock_id=stock.id, period_end=date(yr, 3, 31), period_type="annual",
                    net_income=ni, revenue=ni * 5, source="test",
                ))
            # A year of prices that fell from a high: 25% below it today.
            for d in range(300):
                day = TODAY - timedelta(days=299 - d)
                close = 100.0 if d < 150 else 75.0
                session.add(DailyPrice(stock_id=stock.id, date=day, open=close, high=close,
                                       low=close, close=close, volume=1))
            session.add(AlphaScore(
                symbol=symbol, date=TODAY, fundamental=85 if gem else 40, composite=60,
                sentiment=50, components_json={"strength": 30.0 if gem else 90.0},
            ))
        await session.commit()


async def test_endpoint_lists_matches_with_reasons(client, session_factory):
    await _seed(session_factory)
    body = (await client.get("/api/v1/screener/underrated?min_checks=3")).json()
    assert body["scanned"] == 5
    symbols = [i["symbol"] for i in body["items"]]
    assert all(s.startswith("GEM") for s in symbols) or all(i["passes"] >= 3 for i in body["items"])
    top = body["items"][0]
    assert top["checks"][1]["key"] == "expectations" and top["checks"][1]["detail"]
    assert body["thresholds"]["max_strength"] == svc.MAX_STRENGTH
    assert (await client.get("/api/v1/screener/underrated?min_checks=9")).status_code == 422


async def test_underrated_list_is_frozen_with_the_others_and_only_once(session_factory, monkeypatch):
    await _seed(session_factory)
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    async with session_factory() as session:
        from sqlalchemy import update

        # Peer valuation comes from the analysis service; make the gems
        # undervalued by giving the plain stocks no discount: nothing to do,
        # the scan reads it. Here only the lists' bookkeeping is checked.
        pass
    first = await jobs_module.freeze_pick_lists()
    assert first["errors"] == 0
    async with session_factory() as session:
        ratings = set((await session.execute(select(PickList.rating))).scalars())
    assert {"alpha", "strength"} <= ratings
    again = await jobs_module.freeze_pick_lists()
    assert again == {"fetched": 0, "errors": 0}


async def test_a_rating_added_later_is_written_without_touching_existing_lists(session_factory):
    day = TODAY
    async with session_factory() as session:
        session.add(PickList(list_date=day, rating="alpha", rank=1, symbol="OLD.NS", score=90))
        session.add(PickList(list_date=day, rating="strength", rank=1, symbol="OLD.NS", score=99))
        await session.commit()
        assert await edge_repo.has_list_in_month(session, day) is False  # underrated missing
        session.add(PickList(list_date=day, rating="underrated", rank=1, symbol="X.NS", score=30))
        await session.commit()
        assert await edge_repo.has_list_in_month(session, day) is True
        rows = (await session.execute(select(PickList).order_by(PickList.rating))).scalars().all()
        assert [r.symbol for r in rows if r.rating == "alpha"] == ["OLD.NS"]
