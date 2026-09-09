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


async def test_get_peers_unclassified_stock_has_no_peers(session_factory):
    """M1-T3 500: industry AND sector both NULL means no peer set.

    Ranking-created catalog rows carry no classification; an IS NULL cohort
    match would group thousands of unrelated companies and fan one request
    into thousands of provider calls. Empty list, never the NULL cohort.
    """
    await _seed_stock(session_factory, "U1.NS", "U1", None, None)
    await _seed_stock(session_factory, "U2.NS", "U2", None, None)
    await _seed_stock(session_factory, "C.NS", "C", "Bank", "Banks")

    async with session_factory() as session:
        u1 = await stock_repo.get_stock(session, "U1.NS")
        assert await stock_repo.get_peers(session, u1) == []


async def test_get_peers_caps_at_15_and_orders_by_rank(session_factory):
    """M2-T8 (owner decision): cohort capped at 15, ordered mcap_rank ASC
    NULLS LAST then symbol ASC — deterministic on every call, largest names
    first, and the NULL-rank row loses the tie for the last slot."""
    async with session_factory() as session:
        session.add(Stock(symbol="TGT.NS", name="T", sector="IT", industry="IT Services"))
        for i in range(1, 21):  # 20 ranked peers: ranks 1..20
            session.add(
                Stock(symbol=f"P{i:02d}.NS", name=f"P{i}", sector="IT",
                      industry="IT Services", mcap_rank=i)
            )
        # A NULL-rank stock whose symbol sorts first alphabetically.
        session.add(
            Stock(symbol="AAA.NS", name="AAA", sector="IT",
                  industry="IT Services", mcap_rank=None)
        )
        await session.commit()

    async with session_factory() as session:
        tgt = await stock_repo.get_stock(session, "TGT.NS")
        peers = await stock_repo.get_peers(session, tgt)

    assert len(peers) == stock_repo.PEER_CAP == 15
    # The 15 smallest ranks win; P16..P20 and the NULL-rank AAA are cut.
    assert [p.symbol for p in peers] == [f"P{i:02d}.NS" for i in range(1, 16)]


async def test_get_peers_rank_tiebreak_symbol_asc(session_factory):
    """Equal ranks resolve by symbol ASC — a deterministic total order."""
    async with session_factory() as session:
        session.add(Stock(symbol="TGT.NS", name="T", sector="Auto", industry="Cars"))
        for symbol in ("ZED.NS", "ABLE.NS", "MIKE.NS"):
            session.add(
                Stock(symbol=symbol, name=symbol, sector="Auto", industry="Cars",
                      mcap_rank=7)
            )
        await session.commit()

    async with session_factory() as session:
        tgt = await stock_repo.get_stock(session, "TGT.NS")
        peers = await stock_repo.get_peers(session, tgt)

    assert [p.symbol for p in peers] == ["ABLE.NS", "MIKE.NS", "ZED.NS"]


async def test_get_peers_excludes_etf_and_inactive(session_factory):
    """M2-T8: ETF rows (separate domain, Plan 9) and inactive rows (ranking
    E9/E10 delist/suspend) are never peers; active ranked-out rows remain."""
    async with session_factory() as session:
        session.add(Stock(symbol="TGT.NS", name="T", sector="Energy", industry="Refineries"))
        session.add(
            Stock(symbol="OK.NS", name="Ok", sector="Energy", industry="Refineries",
                  mcap_rank=500, active=True)
        )
        session.add(
            Stock(symbol="ETF.NS", name="An ETF", sector="Energy", industry="Refineries",
                  is_etf=True)
        )
        session.add(
            Stock(symbol="DEAD.NS", name="Dead", sector="Energy", industry="Refineries",
                  active=False, delisted_reason="inactive_proxy")
        )
        await session.commit()

    async with session_factory() as session:
        tgt = await stock_repo.get_stock(session, "TGT.NS")
        peers = await stock_repo.get_peers(session, tgt)

    assert [p.symbol for p in peers] == ["OK.NS"]


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