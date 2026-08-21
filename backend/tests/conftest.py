# Pytest fixtures — isolate tests to the signaldesk_test database.
#
# Concepts:
#  - Fixture: a reusable setup/teardown function injected into tests by name.
#  - Dependency override: app.dependency_overrides[get_session] redirects
#    FastAPI's DB dependency to a test session factory, so the API endpoints
#    hit signaldesk_test — never the production signaldesk database.
#  - Base.metadata.create_all: builds the schema directly from the models
#    (simpler/faster than running Alembic in tests).
#
# Strategy:
#  - One async engine per test session (shared pool).
#  - Recreate the schema for every test (drop_all + create_all) so each test
#    starts from a clean slate.

from collections.abc import AsyncGenerator
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db import Base, get_session
from app.main import app
from app.models import DailyPrice, Stock

# Dedicated test database (separate from production `signaldesk`).
TEST_DATABASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/signaldesk_test"
)


@pytest.fixture()
async def engine():
    """Async engine bound to signaldesk_test.

    Function-scoped (NOT session-scoped) because pytest-asyncio gives each test
    its own event loop, and asyncpg connections are bound to the loop that
    created them. A fresh engine per test avoids cross-loop connection errors.
    """
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest.fixture()
async def session_factory(engine) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Recreate the schema and return a session factory per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory


@pytest.fixture()
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with the DB dependency overridden to the test factory.

    The `session_factory` fixture recreates the schema first; we override the
    app's get_session dependency so every request uses the test DB.
    """

    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
async def seeded(session_factory):
    """Insert two stocks + daily prices for endpoint tests."""
    async with session_factory() as session:
        session.add_all(
            [
                Stock(symbol="RELIANCE.NS", name="Reliance", sector="Energy"),
                Stock(symbol="TCS.NS", name="Tata Consultancy", sector="IT"),
            ]
        )
        await session.flush()

        rel = await session.scalar(select(Stock).where(Stock.symbol == "RELIANCE.NS"))
        tcs = await session.scalar(select(Stock).where(Stock.symbol == "TCS.NS"))

        today = date.today()
        session.add_all(
            [
                DailyPrice(stock_id=rel.id, date=today - timedelta(days=1),
                           open=100, high=105, low=99, close=104, volume=1000),
                DailyPrice(stock_id=rel.id, date=today,
                           open=104, high=106, low=103, close=105, volume=1200),
                DailyPrice(stock_id=tcs.id, date=today - timedelta(days=1),
                           open=50, high=52, low=49, close=51, volume=800),
                DailyPrice(stock_id=tcs.id, date=today,
                           open=51, high=53, low=50, close=52, volume=900),
            ]
        )
        await session.commit()