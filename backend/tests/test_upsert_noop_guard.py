# Phase 2: the nightly write paths must not rewrite unchanged rows.
#
# Postgres gives every row version a new xmin (the writing transaction id).
# A row the no-op guard skipped keeps its xmin; a row that was rewritten gets
# a new one. So "xmin unchanged after a re-run" is the precise, observable
# statement of "nothing was written". Ids are checked too: the old alpha
# backfill deleted and re-inserted rows (new ids every night), which is what
# bloated alpha_scores_pkey to 93.8 MB in production.

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, text

from app import jobs as jobs_module
from app.models import AlphaScore, DailyPrice, Financials, JobRun, Stock
from app.providers.base import OHLCV
from app.repositories import benchmarks as benchmark_repo

TODAY = date(2026, 11, 10)


def _bars(n: int, close_bump: dict[int, float] | None = None) -> list[OHLCV]:
    close_bump = close_bump or {}
    return [
        OHLCV(
            date=TODAY - timedelta(days=n - 1 - i),
            open=100.0, high=101.0, low=99.0,
            close=100.0 + i * 0.5 + close_bump.get(i, 0.0),
            volume=1000 + i,
        )
        for i in range(n)
    ]


class _Provider:
    """Duck-typed provider: the price path only calls get_price_history."""

    def __init__(self, bars: list[OHLCV]):
        self.bars = bars

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        return list(self.bars)


async def _versions(session_factory, sql: str) -> dict:
    async with session_factory() as session:
        return {row[0]: (row[1], row[2]) for row in (await session.execute(text(sql))).all()}


async def _seed_stock(session_factory, symbol: str) -> int:
    async with session_factory() as session:
        stock = Stock(symbol=symbol, name=symbol)
        session.add(stock)
        await session.commit()
        return stock.id


# --- daily_prices ---------------------------------------------------------


PRICE_VERSIONS = "SELECT date, xmin::text, id FROM daily_prices ORDER BY date"


async def test_price_rerun_with_identical_bars_writes_nothing(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_stock(session_factory, "GUARD.NS")
    provider = _Provider(_bars(10))

    first = jobs_module._new_write_stats()
    _, offered = await jobs_module._fetch_one_symbol(provider, "GUARD.NS", TODAY, first)
    assert offered == 10
    assert first == {"inserted": 10, "updated": 0, "unchanged": 0}
    before = await _versions(session_factory, PRICE_VERSIONS)

    second = jobs_module._new_write_stats()
    _, offered = await jobs_module._fetch_one_symbol(provider, "GUARD.NS", TODAY, second)
    assert offered == 10  # return contract unchanged: bars offered
    assert second == {"inserted": 0, "updated": 0, "unchanged": 10}
    assert await _versions(session_factory, PRICE_VERSIONS) == before


async def test_price_rerun_rewrites_only_changed_and_new_bars(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_stock(session_factory, "GUARD.NS")
    await jobs_module._fetch_one_symbol(_Provider(_bars(10)), "GUARD.NS", TODAY)
    before = await _versions(session_factory, PRICE_VERSIONS)

    # Bar 3 is restated (e.g. a dividend adjustment) and one new day arrives.
    restated = _bars(10, close_bump={3: 1.25})
    new_day = OHLCV(date=TODAY + timedelta(days=1), open=1, high=1, low=1, close=1, volume=1)
    stats = jobs_module._new_write_stats()
    await jobs_module._fetch_one_symbol(
        _Provider(restated + [new_day]), "GUARD.NS", TODAY + timedelta(days=1), stats
    )
    assert stats == {"inserted": 1, "updated": 1, "unchanged": 9}

    after = await _versions(session_factory, PRICE_VERSIONS)
    changed = {d for d in before if after[d] != before[d]}
    assert changed == {restated[3].date}
    assert after[restated[3].date][1] == before[restated[3].date][1]  # same id
    async with session_factory() as session:
        close = await session.scalar(
            select(DailyPrice.close).where(DailyPrice.date == restated[3].date)
        )
    assert close == Decimal(str(restated[3].close)).quantize(Decimal("0.0001"))


# --- benchmark_prices -----------------------------------------------------


async def test_benchmark_rerun_with_identical_bars_writes_nothing(session_factory):
    sql = "SELECT date, xmin::text, id FROM benchmark_prices ORDER BY date"
    async with session_factory() as session:
        bench = await benchmark_repo.get_or_create_benchmark(session, "^NSEI", "Nifty 50")
        await session.commit()
        bench_id = bench.id
    async with session_factory() as session:
        await benchmark_repo.upsert_bars(session, bench_id, _bars(5))
    before = await _versions(session_factory, sql)
    async with session_factory() as session:
        offered = await benchmark_repo.upsert_bars(session, bench_id, _bars(5))
    assert offered == 5
    assert await _versions(session_factory, sql) == before

    async with session_factory() as session:
        await benchmark_repo.upsert_bars(session, bench_id, _bars(5, close_bump={0: 2.0}))
    after = await _versions(session_factory, sql)
    assert {d for d in before if after[d] != before[d]} == {_bars(5)[0].date}


# --- alpha_scores backfill ------------------------------------------------


ALPHA_VERSIONS = (
    "SELECT date, xmin::text, id FROM alpha_scores WHERE symbol = 'BACK.NS' ORDER BY date"
)


async def _seed_alpha_stock(session_factory, n_bars: int = 60) -> None:
    async with session_factory() as session:
        stock = Stock(symbol="BACK.NS", name="Backfill", sector="E", industry="O")
        session.add(stock)
        await session.flush()
        session.add(
            Financials(stock_id=stock.id, trailing_pe=Decimal("20.00"),
                       return_on_equity=Decimal("0.1800"),
                       operating_margin=Decimal("0.1250"),
                       debt_to_equity=Decimal("50.00"))
        )
        for i in range(n_bars):
            session.add(
                DailyPrice(stock_id=stock.id, date=TODAY - timedelta(days=n_bars - 1 - i),
                           open=100, high=101, low=99,
                           close=100 + i * 0.1, volume=1000)
            )
        await session.commit()


async def test_alpha_backfill_rerun_writes_nothing_and_keeps_ids(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_alpha_stock(session_factory)

    first: dict = {}
    computed = await jobs_module._backfill_one_alpha("BACK.NS", first)
    assert computed > 0
    assert first == {"inserted": computed, "updated": 0, "unchanged": 0, "deleted": 0}
    before = await _versions(session_factory, ALPHA_VERSIONS)
    assert len(before) == computed

    second: dict = {}
    assert await jobs_module._backfill_one_alpha("BACK.NS", second) == computed
    assert second == {"inserted": 0, "updated": 0, "unchanged": computed, "deleted": 0}
    # Same row versions AND same ids: no delete+insert, no index churn.
    assert await _versions(session_factory, ALPHA_VERSIONS) == before


async def test_alpha_backfill_deletes_stale_and_preserves_live(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_alpha_stock(session_factory)
    stale_day = TODAY - timedelta(days=400)
    async with session_factory() as session:
        session.add_all(
            [
                # Old-formula technical-only row on a date with no bar: stale.
                AlphaScore(symbol="BACK.NS", date=stale_day, composite=1.0, technical=1.0),
                # Genuine live snapshot on the newest bar date: must survive.
                AlphaScore(symbol="BACK.NS", date=TODAY, composite=80.0,
                           fundamental=90.0, technical=70.0, sentiment=80.0),
            ]
        )
        await session.commit()

    stats: dict = {}
    computed = await jobs_module._backfill_one_alpha("BACK.NS", stats)
    assert stats["deleted"] == 1
    # The live row's date was offered but blocked by the guard (not updated).
    assert stats["inserted"] == computed - 1
    assert stats["updated"] == 0

    async with session_factory() as session:
        rows = (
            await session.execute(select(AlphaScore).where(AlphaScore.symbol == "BACK.NS"))
        ).scalars().all()
    by_date = {r.date: r for r in rows}
    assert stale_day not in by_date
    live = by_date[TODAY]
    assert float(live.fundamental) == 90.0 and float(live.composite) == 80.0
    assert len(rows) == computed  # computed dates, live row standing in for TODAY


async def test_alpha_backfill_updates_changed_rows_in_place(session_factory, monkeypatch):
    """When the inputs change (new sentiment/fundamentals), rows are UPDATED
    in place: same ids, new versions. No delete, no new ids."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_alpha_stock(session_factory)
    await jobs_module._backfill_one_alpha("BACK.NS")
    before = await _versions(session_factory, ALPHA_VERSIONS)

    async with session_factory() as session:
        fin = await session.scalar(select(Financials))
        fin.return_on_equity = Decimal("0.0200")  # weaker fundamentals
        await session.commit()

    stats: dict = {}
    computed = await jobs_module._backfill_one_alpha("BACK.NS", stats)
    assert stats["updated"] == computed and stats["inserted"] == 0
    after = await _versions(session_factory, ALPHA_VERSIONS)
    assert set(after) == set(before)
    assert all(after[d][1] == before[d][1] for d in before)  # same ids
    assert all(after[d][0] != before[d][0] for d in before)  # new versions


# --- job_runs: live snapshot pass counts what it stored -------------------


async def test_record_pass_counts_stored_as_processed(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    async def live_pass():
        return {"stored": 7, "errors": 0}

    assert await jobs_module._record_pass("record_live_alpha_snapshots", live_pass) == "success"
    async with session_factory() as session:
        run = await session.scalar(select(JobRun))
    assert run.items_processed == 7
