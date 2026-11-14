# The funds database plumbing (second Neon project, 2026-11-14): optional
# engine, separate metadata, the packed NAV table, and the status check.
# Runs against the local signaldesk_funds_test database only; skipped when
# it does not exist.


import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import Base
from app.funds_db import session as funds_session
from app.funds_db.models import Fund, FundHouse, FundsBase, NavHistory

FUNDS_TEST_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/signaldesk_funds_test"


@pytest.fixture(autouse=True)
def _reset_funds_engine(monkeypatch):
    monkeypatch.setattr(settings, "funds_database_url", "")
    funds_session.set_sessionmaker(None)
    yield
    funds_session.set_sessionmaker(None)


@pytest.fixture()
async def funds_factory():
    engine = create_async_engine(FUNDS_TEST_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(FundsBase.metadata.drop_all)
            await conn.run_sync(FundsBase.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"local funds test database unavailable: {type(exc).__name__}")
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


def test_the_two_databases_never_share_tables():
    funds = set(FundsBase.metadata.tables)
    stocks = set(Base.metadata.tables)
    assert funds == {"fund_houses", "funds", "nav_history", "fund_returns", "fund_facts_monthly"}
    assert not funds & stocks


async def test_unset_url_means_no_engine_and_an_honest_status():
    assert funds_session.funds_sessionmaker() is None
    assert await funds_session.check() == {
        "configured": False, "reachable": False, "revision": None,
    }


async def test_an_unreachable_database_reports_only_the_error_type(monkeypatch):
    monkeypatch.setattr(
        settings, "funds_database_url",
        "postgresql://nobody:secret@127.0.0.1:1/somewhere",
    )
    got = await funds_session.check()
    assert got["configured"] is True and got["reachable"] is False
    text = repr(got)
    assert "secret" not in text and "127.0.0.1" not in text and "somewhere" not in text


async def test_packed_nav_history_round_trips_and_checks_lengths(funds_factory):
    funds_session.set_sessionmaker(funds_factory)
    async with funds_factory() as session:
        house = FundHouse(name="Example AMC", amfi_name="Example Mutual Fund")
        session.add(house)
        await session.flush()
        fund = Fund(amfi_code="120503", name="Example Flexi Cap Direct Growth",
                    fund_house_id=house.id, asset_group="equity", kind="open")
        session.add(fund)
        await session.flush()
        session.add(NavHistory(fund_id=fund.id, yr=2026, days=[2, 5, 6],
                               navs=[3349.1234, 3351.0001, 0.0123], source="amfi"))
        await session.commit()
        row = (await session.execute(select(NavHistory))).scalar_one()
        assert row.navs == [3349.1234, 3351.0001, 0.0123]  # double precision, exact
        assert (await session.scalar(select(Fund.active))) is True

    async with funds_factory() as session:
        session.add(NavHistory(fund_id=fund.id, yr=2025, days=[1, 2], navs=[10.0]))
        with pytest.raises(IntegrityError):
            await session.commit()

    status = await funds_session.check()
    assert status["configured"] is True and status["reachable"] is True


async def test_status_full_reports_the_funds_database(client, funds_factory):
    body = (await client.get("/status/full")).json()
    assert body["funds_db"] == {"configured": False, "reachable": False, "revision": None}
    funds_session.set_sessionmaker(funds_factory)
    body = (await client.get("/status/full")).json()
    assert body["funds_db"]["reachable"] is True
    # An unset funds database never degrades the stocks status.
    assert "funds" not in body["status"]
