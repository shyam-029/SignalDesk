# API/integration tests for the Phase 2 routes (fundamentals/valuation/scores/
# screener). Uses the httpx ASGI client with the DB dependency overridden to
# signaldesk_test (see conftest). No network.

from decimal import Decimal

from sqlalchemy import select

from app.models import Financials, Stock


async def _seed_analysis_data(session_factory) -> None:
    """Seed stocks (with industry) + financials for meaningful analysis tests."""
    async with session_factory() as session:
        tcs = Stock(symbol="TCS.NS", name="TCS", sector="IT", industry="IT Services")
        infy = Stock(symbol="INFY.NS", name="Infy", sector="IT", industry="IT Services")
        rel = Stock(symbol="RELIANCE.NS", name="Reliance", sector="Energy", industry="Oil & Gas")
        session.add_all([tcs, infy, rel])
        await session.flush()

        # TCS: P/E 28.4, ROE 18%, D/E 50, op margin 12.5%
        session.add(
            Financials(
                stock_id=tcs.id, trailing_pe=Decimal("28.40"),
                return_on_equity=Decimal("0.1800"),
                operating_margin=Decimal("0.1250"),
                debt_to_equity=Decimal("50.00"),
            )
        )
        # INFY: P/E 24.1 (cheaper peer)
        session.add(
            Financials(
                stock_id=infy.id, trailing_pe=Decimal("24.10"),
                return_on_equity=Decimal("0.2000"),
                operating_margin=Decimal("0.2000"),
                debt_to_equity=Decimal("30.00"),
            )
        )
        # RELIANCE: P/E 23.9, but no IT peers (different industry)
        session.add(
            Financials(
                stock_id=rel.id, trailing_pe=Decimal("23.90"),
                debt_to_equity=Decimal("50.00"),
            )
        )
        await session.commit()


async def test_fundamentals_endpoint(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/stocks/TCS/fundamentals")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TCS.NS"
    assert body["key_ratios"]["trailing_pe"] == 28.4
    assert body["key_ratios"]["return_on_equity"] == 0.18


async def test_fundamentals_missing_stock_404(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/stocks/ZZZ/fundamentals")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_scores_endpoint(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/stocks/TCS/scores")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TCS.NS"
    # ROE 18% -> 90, op 12.5 -> 50; weights 40/20 -> renorm 2/3,1/3 -> 76.67 -> 77
    # D/E 50 -> 100 (only solvency component present -> 100)
    assert body["profitability"] == 77
    assert body["solvency"] == 100
    assert "Profitability" in body["explanation"]


async def test_valuation_endpoint(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/stocks/TCS/valuation", params={"metric": "PE"})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TCS.NS"
    assert body["metric"] == "P/E"
    assert body["current"] == 28.4
    assert body["peer_median"] == 24.1   # INFY only peer
    assert body["status"] == "overvalued"  # 28.4 vs 24.1 -> +17.8%
    assert "INFY.NS" in body["peers"]


async def test_valuation_no_peers_409(client, session_factory):
    await _seed_analysis_data(session_factory)
    # RELIANCE has no same-industry peers -> NoPeersError -> 409
    r = await client.get("/api/v1/stocks/RELIANCE/valuation", params={"metric": "PE"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NO_PEERS"


async def test_valuation_bad_metric_422(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/stocks/TCS/valuation", params={"metric": "ROE"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_valuation_explanation_endpoint(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/stocks/TCS/valuation/explanation", params={"metric": "PE"})
    assert r.status_code == 200
    body = r.json()
    assert "overvalued" in body["explanation"]
    assert body["symbol"] == "TCS.NS"


async def test_screener_status_filter(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/screener", params={"status": "overvalued"})
    assert r.status_code == 200
    body = r.json()
    # TCS should be overvalued (P/E 28.4 vs peer 24.1)
    syms = [i["symbol"] for i in body["items"]]
    assert "TCS.NS" in syms
    assert all(i["valuation_status"] == "overvalued" for i in body["items"])


async def test_screener_min_profitability(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/screener", params={"min_profitability": 80})
    assert r.status_code == 200
    body = r.json()
    syms = [i["symbol"] for i in body["items"]]
    # INFY profitability (ROE 20->100, op 20->100) = 100 >= 80; TCS = 77 < 80
    assert "INFY.NS" in syms
    assert "TCS.NS" not in syms


async def test_screener_bad_status_422(client, session_factory):
    await _seed_analysis_data(session_factory)
    r = await client.get("/api/v1/screener", params={"status": "bogus"})
    assert r.status_code == 422