# Alpha methodology v2.0: Strength replaces the technical score as the
# composite's price pillar. Covers the per-day Strength query used for the
# history (it must agree with the nightly ranking), the nightly re-blend of
# today's composite, and the live compute reading the stored rank.
# Zero network; runs against the test DB.

import random
from datetime import date, timedelta

import pytest
from sqlalchemy import select

import app.jobs as jobs_module
from app.jobs import record_strength_scores
from app.models import AlphaScore, DailyPrice, Stock, Universe, stock_universe
from app.repositories import strength as repo
from app.services import alpha as alpha_svc
from app.services import strength as svc

TODAY = date.today()
N_STOCKS = 24
N_BARS = svc.HISTORY_BARS + 30


def _walks() -> dict[str, list[float]]:
    """Deterministic random walks, one per share, with some exact ties."""
    rng = random.Random(7)
    out: dict[str, list[float]] = {}
    for i in range(N_STOCKS):
        price = 100.0
        closes = []
        for _ in range(N_BARS):
            price *= 1.0 + rng.uniform(-0.03, 0.032)
            closes.append(round(price, 2))
        out[f"W{i:02d}.NS"] = closes
    # Two shares with identical histories: their ranks must tie exactly.
    out["W01.NS"] = list(out["W00.NS"])
    return out


async def _seed(session_factory, walks, *, with_live_rows: bool = False):
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
            closes = walks[stock.symbol]
            for k, close in enumerate(closes):
                session.add(DailyPrice(
                    stock_id=stock.id, date=TODAY - timedelta(days=len(closes) - 1 - k),
                    open=close, high=close, low=close, close=close, volume=1000,
                ))
            if with_live_rows:
                session.add(AlphaScore(
                    symbol=stock.symbol, date=TODAY, composite=1, fundamental=70,
                    technical=40, sentiment=30, components_json={"trend": 40.0},
                ))
        await session.commit()


def _facts_at(closes: list[float], end: int) -> svc.PriceFacts:
    """The nightly facts for a share whose latest bar is closes[end]."""
    window = closes[max(0, end - svc.HISTORY_BARS + 1): end + 1][::-1]  # newest first
    moves = [
        abs(window[k] / window[k + 1] - 1.0)
        for k in range(min(len(window) - 1, svc.HISTORY_BARS - 1))
    ]
    return svc.PriceFacts(
        bars=len(window),
        last_date=TODAY,
        last_close=window[0],
        close_1m=window[svc.SKIP_BARS] if len(window) > svc.SKIP_BARS else None,
        close_12m=window[-1] if len(window) == svc.HISTORY_BARS else None,
        high_1y=max(window[: svc.HISTORY_BARS - 1]),
        max_move=max(moves) if moves else None,
        daily_sd=None,
    )


def _python_strength(walks, end: int) -> dict[str, float]:
    inputs = {}
    for symbol, closes in walks.items():
        ready, _ = svc.inputs_for(_facts_at(closes, end), None)
        if ready is not None:
            inputs[symbol] = ready
    return {s: r.strength for s, r in svc.rate_list(inputs).items()}


async def test_history_matches_the_nightly_ranking_on_every_day(session_factory):
    walks = _walks()
    await _seed(session_factory, walks)
    async with session_factory() as session:
        history = await repo.get_strength_history(
            session, jobs_module.UNIVERSE_NAME, since=TODAY - timedelta(days=1000)
        )
    first_rankable = svc.HISTORY_BARS - 1
    for end in (first_rankable, first_rankable + 9, N_BARS - 1):
        day = TODAY - timedelta(days=N_BARS - 1 - end)
        expected = _python_strength(walks, end)
        got = {s: by_day[day] for s, by_day in history.items() if day in by_day}
        assert got == pytest.approx(expected, abs=0.051)
    # No rank before a share has a full year of closes.
    too_early = TODAY - timedelta(days=N_BARS - first_rankable)
    assert all(too_early not in by_day for by_day in history.values())
    # Identical histories tie exactly.
    assert history["W00.NS"] == history["W01.NS"]


async def test_history_returns_only_the_requested_shares(session_factory):
    walks = _walks()
    await _seed(session_factory, walks)
    async with session_factory() as session:
        full = await repo.get_strength_history(
            session, jobs_module.UNIVERSE_NAME, since=TODAY - timedelta(days=1000)
        )
        some = await repo.get_strength_history(
            session, jobs_module.UNIVERSE_NAME, since=TODAY - timedelta(days=1000),
            symbols=["W05.NS"],
        )
        none = await repo.get_strength_history(
            session, jobs_module.UNIVERSE_NAME, since=TODAY, symbols=[],
        )
    # Ranked against the whole list, returned for one share only.
    assert some == {"W05.NS": full["W05.NS"]}
    assert none == {}


async def test_nightly_pass_reblends_todays_composite(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    walks = _walks()
    await _seed(session_factory, walks, with_live_rows=True)
    await record_strength_scores(today=TODAY)
    async with session_factory() as session:
        rows = {r.symbol: r for r in (await session.execute(select(AlphaScore))).scalars()}
    for symbol, row in rows.items():
        strength = row.components_json[repo.KEY_STRENGTH]
        expected, _ = alpha_svc._renormalized(70, round(strength), 30)
        assert float(row.composite) == expected, symbol
        assert float(row.technical) == 40  # kept, not blended


async def test_stored_strength_is_used_only_while_current(session_factory):
    async with session_factory() as session:
        session.add(AlphaScore(
            symbol="ONE.NS", date=TODAY - timedelta(days=3), composite=50,
            components_json={repo.KEY_STRENGTH: 81.6},
        ))
        await session.commit()
        assert await alpha_svc.stored_strength(session, "ONE.NS", TODAY) == 82
        stale = TODAY + timedelta(days=svc.STALE_DAYS)
        assert await alpha_svc.stored_strength(session, "ONE.NS", stale) is None
        assert await alpha_svc.stored_strength(session, "NONE.NS", TODAY) is None
