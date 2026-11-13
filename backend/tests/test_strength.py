# Strength rating tests. The math is pure; the facts query, the nightly pass
# and the endpoint run against the test DB. Zero network.

from datetime import date, timedelta

import pytest
from sqlalchemy import select

import app.jobs as jobs_module
from app.jobs import record_strength_scores
from app.models import AlphaScore, DailyPrice, Stock, Universe, stock_universe
from app.repositories import strength as repo
from app.services import strength as svc

TODAY = date.today()


def _facts(**over) -> svc.PriceFacts:
    base = dict(
        bars=svc.HISTORY_BARS, last_date=TODAY, last_close=120.0, close_1m=110.0,
        close_12m=100.0, high_1y=125.0, max_move=0.05, daily_sd=0.02,
    )
    base.update(over)
    return svc.PriceFacts(**base)


# --- Pure math -----------------------------------------------------------------


def test_inputs_use_the_year_skipping_the_latest_month():
    ready, reason = svc.inputs_for(_facts(), TODAY)
    assert reason is None
    assert ready.year_return_pct == pytest.approx(10.0)  # 110 against 100, not 120
    assert ready.from_high_pct == pytest.approx(-4.0)    # 120 against 125
    assert ready.volatility_pct == pytest.approx(0.02 * 252 ** 0.5 * 100)


def test_short_history_gets_no_inputs():
    assert svc.inputs_for(_facts(bars=svc.HISTORY_BARS - 1), TODAY) == (
        None, svc.REASON_SHORT_HISTORY,
    )
    assert svc.inputs_for(_facts(close_12m=None), TODAY)[1] == svc.REASON_SHORT_HISTORY


def test_suspect_move_gets_no_inputs():
    assert svc.inputs_for(_facts(max_move=0.40), TODAY) == (None, svc.REASON_SUSPECT_MOVE)
    assert svc.inputs_for(_facts(max_move=0.399), TODAY)[1] is None


def test_stale_last_bar_gets_no_inputs():
    old = TODAY - timedelta(days=svc.STALE_DAYS + 1)
    assert svc.inputs_for(_facts(last_date=old), TODAY) == (None, svc.REASON_STALE)
    edge = TODAY - timedelta(days=svc.STALE_DAYS)
    assert svc.inputs_for(_facts(last_date=edge), TODAY)[1] is None
    # Without a reference the share's own history is all that is checked.
    assert svc.inputs_for(_facts(last_date=old), None)[1] is None


def test_percentile_ranks_average_ties_and_ignore_order():
    ranks = svc.percentile_ranks({"a": 1.0, "b": 5.0, "c": 5.0, "d": 9.0})
    assert ranks == {"a": 25.0, "b": 62.5, "c": 62.5, "d": 100.0}
    assert svc.percentile_ranks({"d": 9.0, "c": 5.0, "b": 5.0, "a": 1.0}) == ranks
    assert svc.percentile_ranks({}) == {}


def test_rate_list_orders_by_both_ingredients():
    inputs = {
        f"S{i:02d}": svc.Inputs(
            year_return_pct=float(i), from_high_pct=float(i - 30), volatility_pct=float(i + 10)
        )
        for i in range(25)
    }
    ratings = svc.rate_list(inputs)
    assert len(ratings) == 25
    assert ratings["S24"].strength == 100.0
    assert ratings["S00"].strength == 4.0
    # The jumpiest share is the least steady.
    assert ratings["S24"].steadiness == 4.0
    assert ratings["S00"].steadiness == 100.0
    assert ratings["S10"].ranked == 25


def test_rate_list_needs_enough_shares_and_keeps_missing_steadiness_missing():
    few = {f"S{i}": svc.Inputs(1.0 * i, -1.0, 20.0) for i in range(svc.MIN_RANKED - 1)}
    assert svc.rate_list(few) == {}
    many = {f"S{i}": svc.Inputs(1.0 * i, -1.0, 20.0) for i in range(svc.MIN_RANKED)}
    many["S0"] = svc.Inputs(0.0, -1.0, None)
    assert svc.rate_list(many)["S0"].steadiness is None


# --- Facts query, nightly pass, endpoint ----------------------------------------

N_STOCKS = 22
N_BARS = svc.HISTORY_BARS + 5


async def _seed(session_factory, *, short: str | None = None, jump: str | None = None):
    """N_STOCKS shares; share i rises i/10 percent of its start a day."""
    async with session_factory() as session:
        uni = Universe(name=jobs_module.UNIVERSE_NAME)
        session.add(uni)
        stocks = [Stock(symbol=f"S{i:02d}.NS", name=f"Share {i}") for i in range(N_STOCKS)]
        session.add_all(stocks)
        await session.flush()
        for i, stock in enumerate(stocks):
            await session.execute(
                stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id)
            )
            n = 100 if stock.symbol == short else N_BARS
            for k in range(n):
                day = TODAY - timedelta(days=n - 1 - k)
                close = 100.0 + k * i / 10.0
                if stock.symbol == jump and k >= n - 50:
                    close *= 2.0  # an unadjusted bonus, 50 bars ago
                session.add(DailyPrice(
                    stock_id=stock.id, date=day, open=close, high=close, low=close,
                    close=close, volume=1000,
                ))
            session.add(AlphaScore(
                symbol=stock.symbol, date=TODAY, composite=50, fundamental=50,
                technical=50, sentiment=None, components_json={"trend": 55.0},
            ))
        await session.commit()


@pytest.fixture()
def job_db(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    return session_factory


async def test_price_facts_match_the_stored_closes(session_factory):
    await _seed(session_factory)
    async with session_factory() as session:
        facts = await repo.get_price_facts(
            session, TODAY, universe_name=jobs_module.UNIVERSE_NAME
        )
    assert len(facts) == N_STOCKS
    f = facts["S10.NS"]  # rises 1.0 a day from 100; the window is the last 253 bars
    last = 100.0 + (N_BARS - 1)
    assert f.bars == svc.HISTORY_BARS
    assert f.last_date == TODAY
    assert f.last_close == pytest.approx(last)
    assert f.close_1m == pytest.approx(last - svc.SKIP_BARS)
    assert f.close_12m == pytest.approx(last - (svc.HISTORY_BARS - 1))
    assert f.high_1y == pytest.approx(last)
    # The oldest step in the window is the largest: one rupee on the oldest close.
    assert f.max_move == pytest.approx(1.0 / (last - (svc.HISTORY_BARS - 1)))
    assert facts["S00.NS"].daily_sd == pytest.approx(0.0)


async def test_nightly_pass_stores_ranks_and_is_idempotent(job_db):
    await _seed(job_db, short="S03.NS", jump="S07.NS")
    result = await record_strength_scores(today=TODAY)
    assert result == {"stored": N_STOCKS - 2, "skipped": 2, "errors": 0}

    async with job_db() as session:
        rows = {
            r.symbol: r for r in (await session.execute(select(AlphaScore))).scalars()
        }
    top = rows[f"S{N_STOCKS - 1:02d}.NS"].components_json
    assert top[repo.KEY_STRENGTH] == 100.0
    assert top["trend"] == 55.0  # the technical components are kept
    assert set(top) == {"trend", repo.KEY_STRENGTH, repo.KEY_STEADINESS}
    assert all(isinstance(v, (int, float)) for v in top.values())
    assert repo.KEY_STRENGTH not in rows["S03.NS"].components_json
    assert repo.KEY_STRENGTH not in rows["S07.NS"].components_json
    stamps = {s: r.updated_at for s, r in rows.items()}

    # A second run changes nothing and rewrites no row.
    assert await record_strength_scores(today=TODAY) == result
    async with job_db() as session:
        again = {
            r.symbol: r.updated_at
            for r in (await session.execute(select(AlphaScore))).scalars()
        }
    assert again == stamps


async def test_nightly_pass_clears_a_score_that_no_longer_qualifies(job_db):
    await _seed(job_db, jump="S07.NS")
    async with job_db() as session:
        row = await session.scalar(select(AlphaScore).where(AlphaScore.symbol == "S07.NS"))
        row.components_json = {"trend": 55.0, repo.KEY_STRENGTH: 88.0, repo.KEY_STEADINESS: 22.0}
        await session.commit()
    await record_strength_scores(today=TODAY)
    async with job_db() as session:
        row = await session.scalar(select(AlphaScore).where(AlphaScore.symbol == "S07.NS"))
    assert row.components_json == {"trend": 55.0}


async def test_nightly_pass_with_no_prices_is_a_quiet_no_op(job_db):
    assert await record_strength_scores(today=TODAY) == {
        "stored": 0, "skipped": 0, "errors": 0,
    }


async def test_strength_endpoint(client, job_db):
    await _seed(job_db, short="S03.NS", jump="S07.NS")

    before = (await client.get("/api/v1/stocks/S10/strength")).json()
    assert before["status"] == "not_computed"
    assert before["strength"] is None

    await record_strength_scores(today=TODAY)

    body = (await client.get("/api/v1/stocks/S21/strength")).json()
    assert body["status"] == "available"
    assert body["strength"] == 100.0
    assert body["as_of"] == TODAY.isoformat()
    assert body["year_return_pct"] > 0
    assert body["from_high_pct"] == 0.0
    assert body["bars"] == svc.HISTORY_BARS

    short = (await client.get("/api/v1/stocks/S03/strength")).json()
    assert short["status"] == "short_history"
    assert short["strength"] is None
    assert short["bars"] == 100
    assert short["bars_needed"] == svc.HISTORY_BARS

    jump = (await client.get("/api/v1/stocks/S07/strength")).json()
    assert jump["status"] == "suspect_move"
    assert jump["strength"] is None


async def test_strength_endpoint_never_serves_an_old_score_for_a_disqualified_share(
    client, job_db
):
    await _seed(job_db, jump="S07.NS")
    async with job_db() as session:
        session.add(AlphaScore(
            symbol="S07.NS", date=TODAY - timedelta(days=30), composite=50,
            fundamental=50, technical=50, sentiment=None,
            components_json={repo.KEY_STRENGTH: 91.0},
        ))
        await session.commit()
    body = (await client.get("/api/v1/stocks/S07/strength")).json()
    assert body["status"] == "suspect_move"
    assert body["strength"] is None


async def test_rerunning_the_live_snapshot_keeps_the_ratings(job_db):
    from app.repositories import alpha as alpha_repo

    assert set(alpha_repo.PRESERVED_KEYS) == set(repo.RATING_KEYS)
    await _seed(job_db)
    await record_strength_scores(today=TODAY)
    async with job_db() as session:
        await alpha_repo.upsert_snapshot(
            session, symbol="S10.NS", snapshot_date=TODAY, composite=61, fundamental=60,
            technical=62, sentiment=None, components_json={"trend": 70.0},
        )
    async with job_db() as session:
        row = await session.scalar(select(AlphaScore).where(AlphaScore.symbol == "S10.NS"))
    assert row.components_json["trend"] == 70.0  # the live pass's own key is replaced
    assert float(row.composite) == 61.0
    assert set(repo.RATING_KEYS) <= set(row.components_json)

    # A first insert, and a row with nothing to keep, store just what was given.
    async with job_db() as session:
        await alpha_repo.upsert_snapshot(
            session, symbol="NEW.NS", snapshot_date=TODAY, composite=50, fundamental=50,
            technical=50, sentiment=None, components_json=None,
        )
        await alpha_repo.upsert_snapshot(
            session, symbol="NEW.NS", snapshot_date=TODAY, composite=51, fundamental=50,
            technical=50, sentiment=None, components_json={"trend": 1.0},
        )
    async with job_db() as session:
        row = await session.scalar(select(AlphaScore).where(AlphaScore.symbol == "NEW.NS"))
    assert row.components_json == {"trend": 1.0}
