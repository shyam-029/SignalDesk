# Shareholding pattern tests (checklist section 6, step 3). Parser, due-slice
# policy and trend math are pure; the job and endpoint run against the test
# DB with a fake provider. Zero network.

from datetime import date

import pytest
from sqlalchemy import func, select

import app.jobs as jobs_module
from app.jobs import (
    expected_shareholding_quarter,
    ingest_shareholding,
    shareholding_due_slice,
)
from app.models import ShareholdingPeriod, Stock, Universe, stock_universe
from app.providers.base import MarketDataError, ShareholdingDraft
from app.providers.upstox_provider import parse_shareholding
from app.services import depth as svc


# The documented example payload (Upstox share-holdings, Reliance).
PAYLOAD = [
    {"category": "promoters", "history": [
        {"period": "Mar 2026", "value": 50.0}, {"period": "Dec 2025", "value": 50.01},
        {"period": "Sep 2025", "value": 50.01}, {"period": "Jun 2025", "value": 50.07}]},
    {"category": "fii", "history": [
        {"period": "Mar 2026", "value": 18.67}, {"period": "Dec 2025", "value": 19.09},
        {"period": "Sep 2025", "value": 18.65}, {"period": "Jun 2025", "value": 19.21}]},
    {"category": "other_dii", "history": [
        {"period": "Mar 2026", "value": 10.77}, {"period": "Dec 2025", "value": 10.66},
        {"period": "Sep 2025", "value": 10.67}, {"period": "Jun 2025", "value": 10.48}]},
    {"category": "mutual_funds", "history": [
        {"period": "Mar 2026", "value": 9.78}, {"period": "Dec 2025", "value": 9.52},
        {"period": "Sep 2025", "value": 9.66}, {"period": "Jun 2025", "value": 9.32}]},
    {"category": "retail_and_other", "history": [
        {"period": "Mar 2026", "value": 10.79}, {"period": "Dec 2025", "value": 10.73},
        {"period": "Sep 2025", "value": 11.01}, {"period": "Jun 2025", "value": 10.92}]},
]


# --- Parser ------------------------------------------------------------------


def test_parse_documented_payload():
    drafts = parse_shareholding(PAYLOAD)
    assert [d.period_end for d in drafts] == [
        date(2026, 3, 31), date(2025, 12, 31), date(2025, 9, 30), date(2025, 6, 30),
    ]
    latest = drafts[0]
    assert latest.promoters == 50.0
    assert latest.fii == 18.67
    assert latest.other_dii == 10.77
    assert latest.mutual_funds == 9.78
    assert latest.retail_and_other == 10.79
    assert latest.source == "upstox"


def test_parse_skips_bad_values_and_unknown_categories():
    drafts = parse_shareholding([
        {"category": "promoters", "history": [
            {"period": "Mar 2026", "value": 140.0},     # out of range
            {"period": "not a date", "value": 40.0},    # bad label
            {"period": "Dec 2025", "value": "40"},      # not a number
            {"period": "Sep 2025", "value": True},      # bool is not a number
            {"period": "Jun 2025", "value": 41.5},
        ]},
        {"category": "aliens", "history": [{"period": "Jun 2025", "value": 3.0}]},
        "garbage",
    ])
    assert len(drafts) == 1
    assert drafts[0].period_end == date(2025, 6, 30)
    assert drafts[0].promoters == 41.5
    # A category the payload did not carry stays missing, never derived.
    assert drafts[0].fii is None and drafts[0].retail_and_other is None


def test_parse_non_list_payload_is_empty():
    assert parse_shareholding({}) == []
    assert parse_shareholding(None) == []


# --- Due-slice policy --------------------------------------------------------


def test_expected_quarter_waits_for_the_filing_deadline():
    # 30 Sep + 21 days = 21 Oct.
    assert expected_shareholding_quarter(date(2026, 10, 20)) == date(2026, 6, 30)
    assert expected_shareholding_quarter(date(2026, 10, 21)) == date(2026, 9, 30)
    # Across the year boundary: 31 Dec + 21 days = 21 Jan.
    assert expected_shareholding_quarter(date(2026, 1, 10)) == date(2025, 9, 30)
    assert expected_shareholding_quarter(date(2026, 1, 21)) == date(2025, 12, 31)


def test_due_slice_only_takes_stocks_missing_the_expected_quarter():
    today = date(2026, 11, 13)  # expected quarter: 30 Sep 2026
    coverage = [
        ("AAA.NS", date(2026, 9, 30)),   # current
        ("BBB.NS", date(2026, 6, 30)),   # one quarter behind
        ("CCC.NS", None),                # never fetched
    ]
    assert shareholding_due_slice(coverage, today, cap=10) == ["BBB.NS", "CCC.NS"]


def test_due_slice_rotates_so_nothing_starves():
    coverage = [(f"S{i:02d}.NS", None) for i in range(10)]
    seen: set[str] = set()
    for offset in range(5):
        picked = shareholding_due_slice(coverage, date(2026, 11, 13 + offset), cap=3)
        assert len(picked) == 3
        seen.update(picked)
    # 10 due, 3 a night: every stock is reached within a handful of nights.
    assert len(seen) == 10


# --- Trend -------------------------------------------------------------------


def _own(day: str, **kw) -> svc.OwnershipQuarter:
    return svc.OwnershipQuarter(period_end=date.fromisoformat(day), **kw)


def test_ownership_trend_changes_and_directions():
    rows = [
        _own("2025-06-30", promoters=50.07, fii=19.21, other_dii=10.48,
             mutual_funds=9.32, retail_and_other=10.92),
        _own("2026-03-31", promoters=50.0, fii=18.67, other_dii=10.77,
             mutual_funds=9.78, retail_and_other=10.79),
    ]
    trend = svc.ownership_trend(rows)
    assert trend.insufficient_data is False
    assert trend.change_pts["promoters"] == -0.07
    assert trend.change_pts["fii"] == -0.54
    # Institutions: 39.01 -> 39.22.
    assert trend.change_pts["institutions"] == pytest.approx(0.21, abs=0.001)
    assert trend.promoter_direction == "steady"
    assert trend.institution_direction == "steady"
    assert trend.from_period == date(2025, 6, 30)


def test_ownership_trend_rising_and_falling():
    rows = [
        _own("2025-06-30", promoters=60.0, fii=10.0, other_dii=5.0, mutual_funds=5.0),
        _own("2026-03-31", promoters=55.0, fii=13.0, other_dii=5.0, mutual_funds=6.0),
    ]
    trend = svc.ownership_trend(rows)
    assert trend.promoter_direction == "falling"
    assert trend.institution_direction == "rising"


def test_ownership_trend_missing_category_is_not_compared():
    rows = [
        _own("2025-06-30", promoters=60.0, fii=10.0),
        _own("2026-03-31", promoters=61.0, fii=None, other_dii=5.0, mutual_funds=6.0),
    ]
    trend = svc.ownership_trend(rows)
    assert trend.change_pts["fii"] is None
    assert trend.change_pts["institutions"] is None
    assert trend.institution_direction is None
    assert rows[0].institutions is None
    assert trend.promoter_direction == "rising"


def test_ownership_trend_single_quarter_and_empty():
    assert svc.ownership_trend([]).insufficient_data is True
    one = svc.ownership_trend([_own("2026-03-31", promoters=50.0)])
    assert one.insufficient_data is False
    assert one.change_pts == {}
    assert one.promoter_direction is None


# --- Job + endpoint ----------------------------------------------------------


class FakeShareholdingProvider:
    def __init__(self, fail: str | None = None):
        self.calls: list[str] = []
        self.fail = fail

    async def get_shareholding(self, symbol: str) -> list[ShareholdingDraft]:
        self.calls.append(symbol)
        if symbol == self.fail:
            raise MarketDataError(f"boom for {symbol}")
        return parse_shareholding(PAYLOAD)


async def _link_universe(session_factory) -> None:
    """Put the two seeded stocks into the universe the nightly reads."""
    async with session_factory() as session:
        uni = await session.scalar(
            select(Universe).where(Universe.name == jobs_module.UNIVERSE_NAME)
        )
        if uni is None:
            uni = Universe(name=jobs_module.UNIVERSE_NAME)
            session.add(uni)
            await session.flush()
            for stock in (await session.execute(select(Stock))).scalars():
                await session.execute(
                    stock_universe.insert().values(universe_id=uni.id, stock_id=stock.id)
                )
        await session.commit()


@pytest.fixture()
def job_db(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)

    async def _no_retry(fn, what=""):
        return await fn()

    monkeypatch.setattr(jobs_module, "_with_retry", _no_retry)
    return session_factory


async def test_ingest_shareholding_stores_and_is_idempotent(seeded, job_db):
    await _link_universe(job_db)
    provider = FakeShareholdingProvider()
    today = date(2026, 4, 25)  # expected quarter: 31 Mar 2026

    result = await ingest_shareholding(provider, today=today)
    assert result == {"fetched": 2, "rows": 8, "errors": 0}
    async with job_db() as session:
        assert await session.scalar(select(func.count(ShareholdingPeriod.id))) == 8

    # Both stocks now hold the expected quarter: nothing is due, no calls.
    provider.calls.clear()
    again = await ingest_shareholding(provider, today=today)
    assert again == {"fetched": 0, "rows": 0, "errors": 0}
    assert provider.calls == []

    # A new quarter falls due: refetch, same rows offered, still 8 stored.
    later = await ingest_shareholding(provider, today=date(2026, 7, 25))
    assert later["fetched"] == 2
    async with job_db() as session:
        assert await session.scalar(select(func.count(ShareholdingPeriod.id))) == 8


async def test_ingest_shareholding_isolates_a_failing_symbol(seeded, job_db):
    await _link_universe(job_db)
    provider = FakeShareholdingProvider(fail="TCS.NS")
    result = await ingest_shareholding(provider, today=date(2026, 4, 25))
    assert result == {"fetched": 1, "rows": 4, "errors": 1}


async def test_ingest_shareholding_without_token_is_a_quiet_no_op(job_db, monkeypatch):
    monkeypatch.setattr(jobs_module.settings, "upstox_analytics_token", "")
    assert await ingest_shareholding() == {"fetched": 0, "rows": 0, "errors": 0}


async def test_shareholding_endpoint(client, seeded, job_db):
    await _link_universe(job_db)
    await ingest_shareholding(FakeShareholdingProvider(), today=date(2026, 4, 25))
    resp = await client.get("/api/v1/stocks/RELIANCE/shareholding")
    assert resp.status_code == 200
    body = resp.json()
    assert body["insufficient_data"] is False
    assert [q["period_end"] for q in body["quarters"]] == [
        "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31",
    ]
    latest = body["quarters"][-1]
    assert latest["promoters"] == 50.0
    assert latest["institutions"] == pytest.approx(39.22, abs=0.001)
    assert body["change_pts"]["promoters"] == -0.07
    assert body["promoter_direction"] == "steady"
    assert body["from_period"] == "2025-06-30"


async def test_shareholding_endpoint_empty(client, seeded):
    body = (await client.get("/api/v1/stocks/RELIANCE/shareholding")).json()
    assert body["insufficient_data"] is True
    assert body["quarters"] == []
    assert body["change_pts"] == {}
