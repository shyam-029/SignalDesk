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

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Connection pool to PostgreSQL (lazy — connects on first query).
engine = create_async_engine(settings.database_url, echo=False)

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