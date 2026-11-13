# Nightly pass order (work list item 31): market data and news run side by
# side, and the score passes run only after both have finished.

import asyncio

import pytest

from app import jobs


async def test_market_and_news_overlap_and_scores_come_last(session_factory, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setenv("INGEST_ALL_PASSES", "1")
    news_started = asyncio.Event()
    finished: list[str] = []

    async def fake_record(name, run, *a, **k):
        if name == "ingest_prices":
            # Only finishes if news has started meanwhile, i.e. they overlap.
            await asyncio.wait_for(news_started.wait(), timeout=5)
        if name == "ingest_news":
            news_started.set()
        finished.append(name)
        return "success"

    monkeypatch.setattr(jobs, "_record_pass", fake_record)
    await jobs._ingest_passes()

    scores = ["record_live_alpha_snapshots", "record_strength_scores"]
    first_score = min(finished.index(s) for s in scores)
    for name in ("ingest_prices", "ingest_financials", "repair_catalog_gaps",
                 "ingest_news", "prune_news"):
        assert finished.index(name) < first_score, name
    assert finished.index("record_live_alpha_snapshots") < finished.index("record_strength_scores")
    assert finished.index("ingest_news") < finished.index("prune_news")


async def test_a_failed_news_pass_does_not_stop_the_scores(session_factory, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    monkeypatch.setenv("INGEST_ALL_PASSES", "1")
    ran: list[str] = []

    async def fake_record(name, run, *a, **k):
        ran.append(name)
        return "failed" if name == "ingest_news" else "success"

    monkeypatch.setattr(jobs, "_record_pass", fake_record)
    out = await jobs._ingest_passes()
    assert "record_strength_scores" in ran
    assert out["errors"] == 1


@pytest.mark.parametrize("keep", [3])
async def test_prune_reads_once(session_factory, monkeypatch, keep):
    """The prune issues one read for all stocks, not one per stock."""
    monkeypatch.setattr(jobs, "SessionLocal", session_factory)
    opened = 0
    real = session_factory

    def counting_factory():
        nonlocal opened
        opened += 1
        return real()

    monkeypatch.setattr(jobs, "SessionLocal", counting_factory)
    out = await jobs.prune_news(keep=keep)
    assert out == {"fetched": 0, "deleted": 0, "errors": 0}
    assert opened == 1
