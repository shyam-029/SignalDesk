# Work list item 17: live alpha snapshots are dated by the latest stored bar
# (a trading day), never by the runner's calendar date.

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app import jobs as jobs_module
from app.models import AlphaScore, DailyPrice, Financials, Stock

# A Friday: the run below happens "on the weekend" as far as bars go.
LAST_TRADING_DAY = date(2026, 11, 6)


async def _seed(session_factory, symbol: str = "LIVE.NS", with_bars: bool = True) -> None:
    async with session_factory() as session:
        stock = Stock(symbol=symbol, name="Live Co", sector="E", industry="O")
        session.add(stock)
        await session.flush()
        session.add(
            Financials(stock_id=stock.id, trailing_pe=Decimal("20.00"),
                       return_on_equity=Decimal("0.1800"),
                       operating_margin=Decimal("0.1250"),
                       debt_to_equity=Decimal("50.00"))
        )
        if with_bars:
            for i in range(60):
                session.add(
                    DailyPrice(stock_id=stock.id,
                               date=LAST_TRADING_DAY - timedelta(days=59 - i),
                               open=100, high=101, low=99,
                               close=100 + i * 0.1, volume=1000)
                )
        await session.commit()


async def _live_rows(session_factory, symbol: str = "LIVE.NS") -> list[AlphaScore]:
    async with session_factory() as session:
        return list(
            (await session.execute(
                select(AlphaScore).where(
                    AlphaScore.symbol == symbol, AlphaScore.fundamental.is_not(None)
                )
            )).scalars()
        )


async def test_live_snapshot_is_dated_by_the_latest_bar(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed(session_factory)

    assert await jobs_module.record_live_alpha_snapshot("LIVE.NS") is True
    rows = await _live_rows(session_factory)
    assert [r.date for r in rows] == [LAST_TRADING_DAY]


async def test_rerun_on_a_non_trading_day_refreshes_the_same_row(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed(session_factory)

    await jobs_module.record_live_alpha_snapshot("LIVE.NS")
    await jobs_module.record_live_alpha_snapshot("LIVE.NS")
    rows = await _live_rows(session_factory)
    assert len(rows) == 1 and rows[0].date == LAST_TRADING_DAY
