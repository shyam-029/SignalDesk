# Repository tests — peer selection + financials retrieval against signaldesk_test.

from decimal import Decimal

from sqlalchemy import select

import app.repositories.financials as fin_repo
import app.repositories.stocks as stock_repo
from app.models import Financials, Stock


async def _seed_stock(session_factory, symbol, name, sector, industry):
    async with session_factory() as session:
        stock = Stock(symbol=symbol, name=name, sector=sector, industry=industry)
        session.add(stock)
        await session.flush()
        await session.commit()
        return stock.id


async def test_get_stock_returns_match(session_factory):
    await _seed_stock(session_factory, "RELIANCE.NS", "Reliance", "Energy", "Oil & Gas")
    async with session_factory() as session:
        s = await stock_repo.get_stock(session, "RELIANCE.NS")
        assert s is not None
        assert s.symbol == "RELIANCE.NS"
        assert (await stock_repo.get_stock(session, "NOPE.NS")) is None


async def test_get_peers_by_industry_excludes_self(session_factory):
    await _seed_stock(session_factory, "TCS.NS", "TCS", "IT", "IT Services")
    await _seed_stock(session_factory, "INFY.NS", "Infy", "IT", "IT Services")
    await _seed_stock(session_factory, "RELIANCE.NS", "Reliance", "Energy", "Oil & Gas")

    async with session_factory() as session:
        tcs = await stock_repo.get_stock(session, "TCS.NS")
        peers = await stock_repo.get_peers(session, tcs)
        syms = [p.symbol for p in peers]
        assert "INFY.NS" in syms
        assert "TCS.NS" not in syms  # self excluded
        assert "RELIANCE.NS" not in syms  # different industry excluded


async def test_get_peers_sector_fallback_when_industry_null(session_factory):
    await _seed_stock(session_factory, "A.NS", "A", "Auto", None)
    await _seed_stock(session_factory, "B.NS", "B", "Auto", None)
    await _seed_stock(session_factory, "C.NS", "C", "Bank", None)

    async with session_factory() as session:
        a = await stock_repo.get_stock(session, "A.NS")
        peers = await stock_repo.get_peers(session, a)
        assert [p.symbol for p in peers] == ["B.NS"]


async def test_get_financials_returns_fundamentals(session_factory):
    sid = await _seed_stock(session_factory, "RELIANCE.NS", "Reliance", "Energy", "Oil & Gas")
    async with session_factory() as session:
        session.add(
            Financials(
                stock_id=sid, trailing_pe=Decimal("23.90"),
                return_on_equity=Decimal("0.1500"), debt_to_equity=Decimal("50.00"),
            )
        )
        await session.commit()

    async with session_factory() as session:
        s = await stock_repo.get_stock(session, "RELIANCE.NS")
        f = await fin_repo.get_financials(session, s)
        assert f is not None
        assert f.trailing_pe == 23.9
        assert f.return_on_equity == 0.15
        assert f.debt_to_equity == 50.0


async def test_get_financials_none_when_missing(session_factory):
    await _seed_stock(session_factory, "RELIANCE.NS", "Reliance", "Energy", "Oil & Gas")
    async with session_factory() as session:
        s = await stock_repo.get_stock(session, "RELIANCE.NS")
        assert await fin_repo.get_financials(session, s) is None


async def test_to_key_ratios(session_factory):
    sid = await _seed_stock(session_factory, "RELIANCE.NS", "Reliance", "Energy", "Oil & Gas")
    async with session_factory() as session:
        session.add(Financials(stock_id=sid, trailing_pe=Decimal("23.90")))
        await session.commit()
    async with session_factory() as session:
        s = await stock_repo.get_stock(session, "RELIANCE.NS")
        row = await fin_repo.get_financials_row(session, s)
        ratios = fin_repo.to_key_ratios(row)
        assert ratios["trailing_pe"] == 23.9
        assert ratios["return_on_equity"] is None  # never set