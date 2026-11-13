# Per-stock page snapshots: every entry equals what its real endpoint
# returns, failed routes are left out, and build_all writes one file per
# listed stock under the frontend's canonical symbol.

import json

from app.services import stock_snapshot


def _by_key(body):
    return {tuple(q["key"]): q["data"] for q in body["queries"]}


async def test_entries_equal_the_real_endpoints(client, seeded):
    body = await stock_snapshot.build_one(client, "RELIANCE")
    assert body["version"] == stock_snapshot.SNAPSHOT_VERSION
    assert body["symbol"] == "RELIANCE"
    got = _by_key(body)
    assert ("stock-detail", "RELIANCE") in got
    assert ("prices", "RELIANCE", "6mo") in got
    paths = {tuple(k): p for k, p in stock_snapshot.stock_queries("RELIANCE")}
    for key, data in got.items():
        direct = await client.get(f"/api/v1{paths[key]}")
        assert direct.status_code == 200
        assert direct.json() == data, key


async def test_unknown_stock_has_no_entries(client, seeded):
    body = await stock_snapshot.build_one(client, "NOPE")
    assert body["queries"] == []


def test_no_llm_or_heavy_routes():
    paths = [p for _, p in stock_snapshot.stock_queries("X")]
    assert not any("/alpha/explanation" in p for p in paths)
    assert not any("/alpha/history" in p for p in paths)
    assert not any("/technicals/series" in p for p in paths)


def test_canonical_matches_the_frontend():
    assert stock_snapshot.canonical(" reliance.ns ") == "RELIANCE"
    assert stock_snapshot.canonical("M&M") == "M&M"


async def test_build_all_writes_one_file_per_listed_stock(client, seeded, tmp_path, monkeypatch):
    # `client` installs the test-database override on the app.
    from app.main import app

    async def fake_symbols(_client):
        return ["RELIANCE", "TCS", "NOPE"]

    monkeypatch.setattr(stock_snapshot, "list_symbols", fake_symbols)
    written, failed = await stock_snapshot.build_all(app, tmp_path)
    assert (written, failed) == (2, 1)
    files = sorted(p.name for p in (tmp_path / "stock").iterdir())
    assert files == ["RELIANCE.json", "TCS.json"]
    body = json.loads((tmp_path / "stock" / "TCS.json").read_text(encoding="utf-8"))
    assert body["symbol"] == "TCS"


async def test_shared_session_mode_returns_the_same_data(client, seeded, session_factory):
    # The batch's fast path (one session per stock) must produce exactly what
    # the normal per-request sessions produce.
    from app.main import app

    normal = await stock_snapshot.build_one(client, "RELIANCE")
    # The `client` fixture clears all overrides on teardown.
    stock_snapshot.install_shared_sessions(app, session_factory)
    shared = await stock_snapshot.build_one(client, "RELIANCE", session_factory)
    assert _by_key(shared) == _by_key(normal)
    assert len(shared["queries"]) >= 2


async def test_batch_mode_end_to_end(client, seeded, session_factory, tmp_path):
    # Exactly what main() runs: shared sessions installed, the real
    # list_symbols (which runs outside any stock's session), then one file
    # per listed stock. The 2026-11-12 run failed here before this was fixed.
    from app.main import app

    listed = await stock_snapshot.list_symbols(client)  # normal sessions
    stock_snapshot.install_shared_sessions(app, session_factory)
    written, failed = await stock_snapshot.build_all(app, tmp_path, session_factory)
    assert (written, failed) == (len(listed), 0)
    for sym in listed:
        assert (tmp_path / "stock" / f"{sym}.json").exists()


async def test_memo_mode_returns_the_same_snapshot(client, seeded, session_factory):
    # With the per-stock read memo on (as main() runs it), every entry must
    # equal the build without it.
    from app.main import app

    stock_snapshot.install_shared_sessions(app, session_factory)
    plain = await stock_snapshot.build_one(client, "RELIANCE")

    async def with_memo():
        async with session_factory() as session:
            from app.repositories.batch_memo import MEMO_KEY

            session.info[MEMO_KEY] = {}
            token = stock_snapshot._stock_session.set(session)
            try:
                return await stock_snapshot.build_one(client, "RELIANCE")
            finally:
                stock_snapshot._stock_session.reset(token)

    memo = await with_memo()

    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("computed_at", "generated_at")}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o

    assert strip(memo) == strip(plain)
