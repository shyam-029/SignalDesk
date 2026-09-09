# Database wiring — engine, session factory, ORM base, and FastAPI dependency.
#
# New concepts:
#  - create_async_engine: builds the async connection POOL to Postgres. It is
#    lazy — it connects on first use, not at import time.
#  - async_sessionmaker: a factory that produces independent AsyncSession
#    objects, each representing a unit of work / transaction.
#  - DeclarativeBase: the ORM registry. All models inherit from Base, and their
#    table definitions are collected into Base.metadata (used by Alembic).

from collections.abc import AsyncGenerator

from sqlalchemy import make_url
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def asyncpg_ready_url(raw: str) -> URL:
    """Normalize a Postgres URL for the asyncpg driver.

    Neon's console copy-paste gives a libpq URL (`?sslmode=require&channel_
    binding=require`), but SQLAlchemy passes URL query parameters to
    asyncpg.connect() as kwargs and asyncpg rejects libpq-style parameter
    NAMES (verified asyncpg 0.31.0: unexpected keyword argument). Two
    adjustments keep either URL form working everywhere the app builds an
    asyncpg engine:
      - `sslmode` is RENAMED to `ssl` (asyncpg accepts libpq-style VALUES on
        its own `ssl` parameter: 'require', 'verify-full', ...), dropped
        when an explicit `ssl` is already present.
      - `channel_binding` is DROPPED: asyncpg negotiates SCRAM channel
        binding automatically over TLS and has no such parameter.
    Non-asyncpg URLs pass through untouched (libpq dialects accept both).
    """
    url = make_url(raw)
    if not (url.get_backend_name() == "postgresql" and url.get_driver_name() == "asyncpg"):
        return url
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode
    query.pop("channel_binding", None)
    if query == dict(url.query):
        return url
    return url.set(query=query)


# Connection pool to PostgreSQL (lazy — connects on first query).
engine = create_async_engine(asyncpg_ready_url(settings.database_url), echo=False)

# Factory for per-operation sessions. expire_on_commit=False keeps attribute
# values accessible after a transaction commits.
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models. Registers tables on Base.metadata."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a session, ensure it is closed when done.

    Yields a new AsyncSession per request; the generator's finally block
    guarantees the session is released back to the pool.
    """
    async with SessionLocal() as session:
        yield session