# The funds database engine, created only when FUNDS_DATABASE_URL is set.
#
# Repositories take a session and never open one. Funds repositories take a
# funds session; nothing takes both.

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db import asyncpg_ready_url

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def configured() -> bool:
    return bool(settings.funds_database_url.strip())


def funds_sessionmaker() -> async_sessionmaker[AsyncSession] | None:
    """The funds session factory, or None when no funds database is set.

    Created lazily on first use. pool_pre_ping for the same reason as the
    stocks engine: Neon closes idle connections during long fetch phases.
    """
    global _engine, _factory
    if _factory is not None:
        return _factory
    if not configured():
        return None
    if _factory is None:
        _engine = create_async_engine(
            asyncpg_ready_url(settings.funds_database_url),
            echo=False,
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=2,
        )
        _factory = async_sessionmaker(bind=_engine, expire_on_commit=False)
    return _factory


def set_sessionmaker(factory: async_sessionmaker[AsyncSession] | None) -> None:
    """Point the funds session at another factory (tests), or reset it."""
    global _engine, _factory
    _engine = None
    _factory = factory


async def check() -> dict:
    """Is the funds database configured, reachable, and at which revision?

    Never returns the URL or the raw error text (it can carry the host).
    """
    factory = funds_sessionmaker()
    if factory is None:
        return {"configured": False, "reachable": False, "revision": None}
    try:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            revision = None
            try:
                revision = (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar()
            except Exception:  # noqa: BLE001 - no migrations applied yet
                await session.rollback()
        return {"configured": True, "reachable": True, "revision": revision}
    except Exception as exc:  # noqa: BLE001
        return {
            "configured": True,
            "reachable": False,
            "revision": None,
            "error": type(exc).__name__,
        }
