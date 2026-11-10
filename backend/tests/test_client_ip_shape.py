# Item 15: the client-IP shape probe reports structure and yes/no answers,
# never an address.

SPOOF = "203.0.113.9"
CALLER = "198.51.100.7"


async def test_reports_shape_without_any_address(client):
    r = await client.get(
        "/debug/client-ip-shape",
        headers={
            "X-Forwarded-For": f"{SPOOF}, {CALLER}",
            "X-Real-IP": CALLER,
            "X-Probe-Spoof": SPOOF,
            "X-Probe-Caller": CALLER,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["x_forwarded_for_entries"] == 2
    assert body["xff_first_is_spoof"] is True
    assert body["xff_last_is_caller"] is True
    assert body["xff_first_is_caller"] is False
    assert body["header_is_caller"] == {"x-real-ip": True}
    assert body["header_is_spoof"] == {"x-real-ip": False}
    assert "x-forwarded-for" in body["headers_present"]
    # No address appears anywhere in the response.
    assert SPOOF not in r.text and CALLER not in r.text


async def test_empty_probe_values_never_match(client):
    r = await client.get("/debug/client-ip-shape", headers={"X-Forwarded-For": "1.2.3.4"})
    body = r.json()
    assert body["xff_first_is_spoof"] is False and body["xff_first_is_caller"] is False


async def test_requires_the_ops_key_in_production(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "ops_api_key", "k" * 40)
    r = await client.get("/debug/client-ip-shape")
    assert r.status_code in (401, 403, 404)
