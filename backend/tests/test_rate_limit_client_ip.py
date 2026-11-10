# Item 15: the rate limiter keys on CF-Connecting-IP (set by Cloudflare,
# which refuses client-supplied values), never on X-Forwarded-For.

from app.config import settings


async def test_forged_x_forwarded_for_cannot_dodge_the_limit(client, monkeypatch, seeded):
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 2)
    statuses = []
    for i in range(3):
        r = await client.get(
            "/api/v1/stocks",
            headers={"CF-Connecting-IP": "198.51.100.7", "X-Forwarded-For": f"203.0.113.{i}"},
        )
        statuses.append(r.status_code)
    # Rotating fake X-Forwarded-For values no longer buys fresh buckets.
    assert statuses == [200, 200, 429]


async def test_distinct_real_clients_get_separate_buckets(client, monkeypatch, seeded):
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 1)
    a = await client.get("/api/v1/stocks", headers={"CF-Connecting-IP": "198.51.100.7"})
    b = await client.get("/api/v1/stocks", headers={"CF-Connecting-IP": "198.51.100.8"})
    assert a.status_code == 200 and b.status_code == 200


async def test_without_cloudflare_the_transport_peer_is_used(client, monkeypatch, seeded):
    """Local runs/tests have no Cloudflare: X-Forwarded-For is still ignored."""
    monkeypatch.setattr(settings, "rate_limit_default_per_min", 1)
    first = await client.get("/api/v1/stocks", headers={"X-Forwarded-For": "203.0.113.1"})
    second = await client.get("/api/v1/stocks", headers={"X-Forwarded-For": "203.0.113.2"})
    assert first.status_code == 200
    assert second.status_code == 429
