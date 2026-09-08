# Endpoint + error-envelope tests for the stocks API.
#
# These hit the real app (via httpx ASGITransport) but with the DB dependency
# overridden to signaldesk_test (see conftest). No network calls are made.

from datetime import date, timedelta

from sqlalchemy import select

from app.models import Stock


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


# --- Server-side universe search (the ETERNAL/SWIGGY/IFCI fix) ----------------


async def _seed_search_data(session_factory):
    """ETERNAL/SWIGGY ranked-in; OUTSIDE.NS cataloged but outside the universe."""
    from app.models import Universe, stock_universe

    async with session_factory() as session:
        eternal = Stock(symbol="ETERNAL.NS", name="Eternal Ltd", sector="IT")
        swiggy = Stock(symbol="SWIGGY.NS", name="Swiggy Ltd", sector="IT")
        outside = Stock(symbol="ZZZOUT.NS", name="Outside Corp", sector="IT")
        session.add_all([eternal, swiggy, outside])
        await session.flush()
        uni = Universe(name="top1000")
        session.add(uni)
        await session.flush()
        await session.execute(
            stock_universe.insert().values(
                [
                    {"universe_id": uni.id, "stock_id": eternal.id},
                    {"universe_id": uni.id, "stock_id": swiggy.id},
                ]
            )
        )
        await session.commit()


async def test_search_finds_ranked_stock_by_prefix(client, session_factory):
    await _seed_search_data(session_factory)
    r = await client.get("/api/v1/stocks/search", params={"q": "eter"})
    assert r.status_code == 200
    body = r.json()
    symbols = [i["symbol"] for i in body["items"]]
    assert "ETERNAL.NS" in symbols


async def test_search_finds_by_company_name(client, session_factory):
    await _seed_search_data(session_factory)
    r = await client.get("/api/v1/stocks/search", params={"q": "swiggy"})
    assert r.status_code == 200
    assert [i["symbol"] for i in r.json()["items"]] == ["SWIGGY.NS"]


async def test_search_excludes_stocks_outside_universe(client, session_factory):
    await _seed_search_data(session_factory)
    r = await client.get("/api/v1/stocks/search", params={"q": "outside"})
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_stock_list_is_universe_scoped(client, session_factory):
    """The research list presents the ranked 1000, not the 2,900-row catalog."""
    await _seed_search_data(session_factory)
    r = await client.get("/api/v1/stocks")
    assert r.status_code == 200
    body = r.json()
    symbols = {i["symbol"] for i in body["items"]}
    assert symbols == {"ETERNAL.NS", "SWIGGY.NS"}
    assert body["total"] == 2


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

# --- Phase 7: honest nulls, staleness flags, explanation provenance ----------


async def test_list_stocks_no_prices_returns_nulls_not_zeros(client, session_factory, seeded):
    """A stock with no price bars gets last_price/change_pct null (was 0.0)."""
    from app.models import Stock, Universe, stock_universe

    async with session_factory() as session:
        stock = Stock(symbol="EMPTY.NS", name="Empty Co", sector="IT")
        session.add(stock)
        await session.flush()
        uni = await session.scalar(select(Universe).where(Universe.name == "top1000"))
        await session.execute(
            stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id)
        )
        await session.commit()

    r = await client.get("/api/v1/stocks")
    assert r.status_code == 200
    items = {i["symbol"]: i for i in r.json()["items"]}
    empty = items["EMPTY.NS"]
    assert empty["last_price"] is None
    assert empty["change_pct"] is None
    # Stocks WITH data are unaffected.
    assert items["RELIANCE.NS"]["last_price"] == 105.0


async def test_quote_stale_flag(client, session_factory):
    """quote.stale: fresh data -> False, old data -> True, no data -> None."""
    from sqlalchemy import select

    from app.models import DailyPrice, Stock

    old = date.today() - timedelta(days=9)  # older than the 3-day price TTL
    async with session_factory() as session:
        old_stock = Stock(symbol="OLD.NS", name="Old Co")
        bare = Stock(symbol="BARE.NS", name="Bare Co")
        session.add_all([old_stock, bare])
        await session.flush()
        session.add(
            DailyPrice(stock_id=old_stock.id, date=old,
                       open=10, high=11, low=9, close=10.5, volume=1)
        )
        await session.commit()

    r_old = await client.get("/api/v1/stocks/OLD")
    assert r_old.status_code == 200
    assert r_old.json()["quote"]["stale"] is True

    r_bare = await client.get("/api/v1/stocks/BARE")
    assert r_bare.status_code == 200
    assert r_bare.json()["quote"]["stale"] is None
    assert r_bare.json()["quote"]["last_price"] is None


async def test_quote_stale_flag_fresh(client, seeded):
    r = await client.get("/api/v1/stocks/RELIANCE")
    assert r.status_code == 200
    assert r.json()["quote"]["stale"] is False


async def test_alpha_explanation_exposes_source(client, seeded, monkeypatch):
    """Fallback provenance is observable on /alpha/explanation."""
    from app.services import llm_narrative as narr

    narr._cache.clear()
    monkeypatch.setattr(narr.settings, "llm_api_key", "")
    monkeypatch.setattr(narr.settings, "llm_model", "")

    r = await client.get("/api/v1/stocks/RELIANCE/alpha/explanation")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"symbol", "explanation", "source"}
    assert body["source"] == "rule_based"
