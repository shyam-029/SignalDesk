# Incremental price fetch (work list item 27): the last month when it agrees
# with the stored bars, the full history when it does not or when little is
# stored. Zero network; a scripted provider stands in for Yahoo.

from datetime import date, timedelta

from sqlalchemy import select

import app.jobs as jobs_module
from app.models import DailyPrice, Stock, Universe, stock_universe
from app.providers.base import OHLCV

TODAY = date.today()


def _series(n: int, scale: float = 1.0, end: date = TODAY) -> list[OHLCV]:
    """n daily bars ending at `end`, close rising 1 a day from 100."""
    out = []
    for k in range(n):
        day = end - timedelta(days=n - 1 - k)
        close = (100.0 + k) * scale
        out.append(OHLCV(date=day, open=close, high=close, low=close, close=close,
                         volume=1000, source="test"))
    return out


class _Provider:
    """Answers "1mo" with the last 31 bars of `series`, "2y" with all of it."""

    def __init__(self, series: dict[str, list[OHLCV]]):
        self.series = series
        self.calls: list[tuple[str, str]] = []

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        self.calls.append((symbol, period))
        bars = self.series.get(symbol, [])
        return bars[-31:] if period == "1mo" else list(bars)


async def _seed(session_factory, stored: dict[str, list[OHLCV]]):
    async with session_factory() as session:
        uni = Universe(name=jobs_module.UNIVERSE_NAME)
        session.add(uni)
        await session.flush()
        for symbol, bars in stored.items():
            stock = Stock(symbol=symbol, name=symbol)
            session.add(stock)
            await session.flush()
            await session.execute(
                stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id)
            )
            for b in bars:
                session.add(DailyPrice(stock_id=stock.id, date=b.date, open=b.open,
                                       high=b.high, low=b.low, close=b.close, volume=b.volume))
        await session.commit()


async def _closes(session_factory, symbol: str) -> dict[date, float]:
    async with session_factory() as session:
        rows = await session.execute(
            select(DailyPrice.date, DailyPrice.close)
            .join(Stock, Stock.id == DailyPrice.stock_id)
            .where(Stock.symbol == symbol)
        )
        return {d: float(c) for d, c in rows.all()}


async def test_stored_tails_reads_count_and_newest_closes(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed(session_factory, {"A.NS": _series(450, end=TODAY - timedelta(days=1))})
    tails = await jobs_module._stored_tails(["A.NS", "NONE.NS"])
    assert set(tails) == {"A.NS"}
    t = tails["A.NS"]
    assert t.bars == 450 and t.last_date == TODAY - timedelta(days=1)
    assert len(t.closes) == jobs_module.OVERLAP_BARS
    assert t.closes[t.last_date] == 100.0 + 449


async def test_normal_night_fetches_one_month_only(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    full = _series(500)
    await _seed(session_factory, {"A.NS": full[:-1]})  # stored up to yesterday
    provider = _Provider({"A.NS": full})
    out = await jobs_module.ingest_universe(provider=provider, batch_size=5, today=TODAY)
    assert provider.calls == [("A.NS", "1mo")]
    assert (out["incremental"], out["full"], out["refetch"]) == (1, 0, 0)
    assert out["inserted"] == 1  # today's new bar
    closes = await _closes(session_factory, "A.NS")
    assert len(closes) == 500 and closes[TODAY] == 100.0 + 499


async def test_adjusted_history_is_refetched_in_full(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    stored = _series(500)[:-1]
    await _seed(session_factory, {"A.NS": stored})
    # A 1:2 split: the provider now reports every past close halved.
    provider = _Provider({"A.NS": _series(500, scale=0.5)})
    out = await jobs_module.ingest_universe(provider=provider, batch_size=5, today=TODAY)
    assert provider.calls == [("A.NS", "1mo"), ("A.NS", "2y")]
    assert (out["incremental"], out["full"], out["refetch"]) == (0, 0, 1)
    closes = await _closes(session_factory, "A.NS")
    oldest = min(closes)
    assert closes[oldest] == 50.0  # the old part of the series was rescaled too


async def test_small_moves_inside_tolerance_stay_incremental(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed(session_factory, {"A.NS": _series(500)[:-1]})
    provider = _Provider({"A.NS": _series(500, scale=1.0005)})  # 0.05%
    out = await jobs_module.ingest_universe(provider=provider, batch_size=5, today=TODAY)
    assert out["incremental"] == 1 and out["refetch"] == 0


async def test_short_or_stale_history_gets_the_full_fetch(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    stale_end = TODAY - timedelta(days=jobs_module.INCREMENTAL_MAX_GAP_DAYS + 1)
    await _seed(session_factory, {
        "SHORT.NS": _series(100)[:-1],
        "STALE.NS": _series(500, end=stale_end),
        "NEW.NS": [],
    })
    provider = _Provider({s: _series(500) for s in ("SHORT.NS", "STALE.NS", "NEW.NS")})
    out = await jobs_module.ingest_universe(provider=provider, batch_size=5, today=TODAY)
    assert sorted(provider.calls) == [
        ("NEW.NS", "2y"), ("SHORT.NS", "2y"), ("STALE.NS", "2y"),
    ]
    assert (out["incremental"], out["full"], out["refetch"]) == (0, 3, 0)
    for symbol in ("SHORT.NS", "STALE.NS", "NEW.NS"):
        closes = await _closes(session_factory, symbol)
        assert TODAY in closes and len(closes) >= 500


def test_overlap_needs_enough_shared_days():
    tail = jobs_module.StoredTail(
        bars=500, last_date=TODAY - timedelta(days=40),
        closes={TODAY - timedelta(days=40): 100.0},
    )
    assert jobs_module._overlap_matches(tail, _series(31)) is False
