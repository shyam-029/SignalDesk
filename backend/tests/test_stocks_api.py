# Endpoint + error-envelope tests for the stocks API.
#
# These hit the real app (via httpx ASGITransport) but with the DB dependency
# overridden to signaldesk_test (see conftest). No network calls are made.

from datetime import date, timedelta


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_list_stocks_default(client, seeded):
    r = await client.get("/api/v1/stocks")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    symbols = {item["symbol"] for item in body["items"]}
    assert symbols == {"RELIANCE.NS", "TCS.NS"}


async def test_list_stocks_last_price_and_change(client, seeded):
    r = await client.get("/api/v1/stocks")
    items = r.json()["items"]
    rel = next(i for i in items if i["symbol"] == "RELIANCE.NS")
    # Latest close 105, prior close 104 -> ~0.96% change.
    assert rel["last_price"] == 105.0
    assert abs(rel["change_pct"] - 0.96) < 0.05


async def test_list_stocks_sector_filter(client, seeded):
    r = await client.get("/api/v1/stocks", params={"sector": "Energy"})
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "RELIANCE.NS"


async def test_list_stocks_pagination(client, seeded):
    r = await client.get("/api/v1/stocks", params={"limit": 1, "page": 1})
    body = r.json()
    assert len(body["items"]) == 1
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["limit"] == 1


async def test_price_history_bare_symbol(client, seeded):
    r = await client.get("/api/v1/stocks/RELIANCE/prices", params={"range": "1y"})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert len(body["items"]) == 2
    assert body["items"][0]["close"] == 104.0
    assert body["items"][-1]["close"] == 105.0


async def test_price_history_with_suffix(client, seeded):
    r = await client.get("/api/v1/stocks/TCS.NS/prices", params={"range": "1y"})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TCS.NS"
    assert len(body["items"]) == 2


async def test_price_history_range_filter(client, seeded):
    # Only the most recent row (today) falls within the last 5 days.
    r = await client.get("/api/v1/stocks/RELIANCE/prices", params={"range": "5d"})
    body = r.json()
    assert len(body["items"]) == 2  # both seeded rows are within a week


async def test_unknown_symbol_404_envelope(client):
    r = await client.get("/api/v1/stocks/ZZZNOTREAL/prices")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "RESOURCE_NOT_FOUND"
    assert err["detail"]["symbol"] == "ZZZNOTREAL.NS"


async def test_bad_range_422_envelope(client, seeded):
    r = await client.get("/api/v1/stocks/RELIANCE/prices", params={"range": "99y"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "99y" in err["detail"]["range"]


async def test_bad_resample_422_envelope(client, seeded):
    r = await client.get("/api/v1/stocks/RELIANCE/prices", params={"resample": "1w"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["detail"]["resample"] == "1w"

# --- /stocks/{symbol}/profile (provider-sourced company background) ----------


async def test_company_profile_endpoint(client, session_factory, seeded):
    from sqlalchemy import select

    from app.models import Stock
    from app.repositories import company_profiles as profile_repo

    async with session_factory() as session:
        stock = await session.scalar(select(Stock).where(Stock.symbol == "RELIANCE.NS"))
        await profile_repo.upsert_profile(
            session,
            stock_id=stock.id,
            business_summary="Reliance engages in energy, telecom and retail.",
            ceo="Mukesh Ambani",
            employees=389000,
            website="www.ril.com",
            source="yfinance",
        )

    r = await client.get("/api/v1/stocks/RELIANCE/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert body["business_summary"].startswith("Reliance engages")
    assert body["ceo"] == "Mukesh Ambani"
    assert body["employees"] == 389000
    assert body["website"] == "www.ril.com"
    assert body["source"] == "yfinance"


async def test_company_profile_missing_is_null_not_empty_error(client, seeded):
    r = await client.get("/api/v1/stocks/RELIANCE/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["business_summary"] is None
    assert body["ceo"] is None
