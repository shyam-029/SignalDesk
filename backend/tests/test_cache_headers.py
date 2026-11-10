# Item 12: successful research GETs are browser-cacheable; nothing else is.

from app.main import API_CACHE_CONTROL


async def test_successful_api_get_is_cacheable(client, seeded):
    r = await client.get("/api/v1/stocks")
    assert r.status_code == 200
    assert r.headers["cache-control"] == API_CACHE_CONTROL


async def test_errors_are_not_cacheable(client, seeded):
    r = await client.get("/api/v1/stocks/NOPE")
    assert r.status_code == 404
    assert "cache-control" not in r.headers
    r = await client.get("/api/v1/screener", params={"status": "bogus"})
    assert r.status_code == 422
    assert "cache-control" not in r.headers


async def test_operational_routes_are_not_cacheable(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert "cache-control" not in r.headers


async def test_posts_are_not_cacheable(client, seeded):
    r = await client.post("/api/v1/stocks/RELIANCE/ask", json={"question": "What does it do?"})
    assert "cache-control" not in r.headers
