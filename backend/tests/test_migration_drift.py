# Work list item 19: the migrations must build exactly the schema the models
# describe.
#
# Every other test builds its schema from the models (Base.metadata
# create_all), never from the migrations, so a model change without a
# matching migration (or a migration that diverges from the model) would pass
# CI and only surface when `migrate.yml` runs against production. This test
# builds a fresh, throwaway database purely from the Alembic migrations and
# asks Alembic's own autogenerate comparison for any difference from the
# models. Any difference fails CI with the list of changes.
#
# Synchronous on purpose: alembic's env.py runs its own event loop.

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db import Base
from tests.conftest import TEST_DATABASE_URL

BACKEND = Path(__file__).resolve().parents[1]
DRIFT_DB = "signaldesk_migration_drift"
ADMIN_DSN = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
DRIFT_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + f"/{DRIFT_DB}"


async def _recreate_db(drop_only: bool = False) -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{DRIFT_DB}" WITH (FORCE)')
        if not drop_only:
            await conn.execute(f'CREATE DATABASE "{DRIFT_DB}"')
    finally:
        await conn.close()


def _alembic_config() -> Config:
    # No ini file: env.py would otherwise call logging.fileConfig, which
    # disables the app's existing loggers for every later test.
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


async def _diff() -> list:
    engine = create_async_engine(DRIFT_URL)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: compare_metadata(
                    MigrationContext.configure(sync_conn, opts={"compare_type": True}),
                    Base.metadata,
                )
            )
    finally:
        await engine.dispose()


def _describe(diff) -> str:
    return "\n".join(f"  - {d!r}" for d in diff)


def test_migrations_match_models(monkeypatch):
    asyncio.run(_recreate_db())
    try:
        # env.py reads settings.database_url to choose its target.
        monkeypatch.setattr(settings, "database_url", DRIFT_URL)
        command.upgrade(_alembic_config(), "head")
        diff = [
            d for d in asyncio.run(_diff())
            # alembic's own bookkeeping table is not a model.
            if not (isinstance(d, tuple) and d[0] == "remove_table"
                    and getattr(d[1], "name", None) == "alembic_version")
        ]
    finally:
        asyncio.run(_recreate_db(drop_only=True))

    if diff:
        pytest.fail(
            "The schema built by the migrations differs from the models.\n"
            "Add a migration (or fix the model) so they match:\n" + _describe(diff)
        )
