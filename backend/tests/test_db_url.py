# asyncpg_ready_url tests (M1-T5): the Neon console copy gives a libpq URL
# (?sslmode=require&channel_binding=require) and SQLAlchemy passes URL query
# params to asyncpg.connect() as kwargs; asyncpg 0.31.0 rejects the libpq
# NAMES (verified live: unexpected keyword argument). These tests pin the
# normalization so either secret form works on every asyncpg engine site
# (app engine, Alembic, NullPool job engine).

from sqlalchemy import make_url

from app.db import asyncpg_ready_url


def test_libpq_sslmode_is_renamed_to_ssl():
    url = asyncpg_ready_url("postgresql+asyncpg://u:p@h:5432/db?sslmode=require")
    assert "sslmode" not in url.query
    assert url.query["ssl"] == "require"


def test_neon_console_channel_binding_is_dropped():
    url = asyncpg_ready_url(
        "postgresql+asyncpg://u:p@h:5432/db?sslmode=require&channel_binding=require"
    )
    assert "sslmode" not in url.query
    assert "channel_binding" not in url.query
    assert url.query["ssl"] == "require"


def test_channel_binding_alone_is_dropped():
    url = asyncpg_ready_url("postgresql+asyncpg://u:p@h:5432/db?channel_binding=require")
    assert "channel_binding" not in url.query


def test_explicit_ssl_wins_and_sslmode_is_dropped():
    url = asyncpg_ready_url(
        "postgresql+asyncpg://u:p@h:5432/db?sslmode=verify-full&ssl=require"
    )
    assert "sslmode" not in url.query
    assert url.query["ssl"] == "require"


def test_url_without_params_is_untouched():
    raw = "postgresql+asyncpg://u:p@h:5432/db"
    assert asyncpg_ready_url(raw).render_as_string(hide_password=False) == raw


def test_asyncpg_url_with_ssl_already_set_is_untouched():
    raw = "postgresql+asyncpg://u:p@h:5432/db?ssl=require"
    assert asyncpg_ready_url(raw).render_as_string(hide_password=False) == raw


def test_bare_postgresql_url_is_upgraded_and_normalized():
    # A verbatim Neon console paste (no +asyncpg) must work everywhere.
    url = asyncpg_ready_url(
        "postgresql://u:p@h:5432/db?sslmode=require&channel_binding=require"
    )
    assert url.drivername == "postgresql+asyncpg"
    assert url.query["ssl"] == "require"
    assert "sslmode" not in url.query and "channel_binding" not in url.query


def test_explicit_psycopg2_driver_is_respected_not_swapped():
    url = asyncpg_ready_url("postgresql+psycopg2://u:p@h:5432/db?sslmode=require")
    assert url.drivername == "postgresql+psycopg2"
    assert url.query["sslmode"] == "require"


def test_non_postgres_url_is_untouched():
    url = asyncpg_ready_url("mysql+pymysql://u:p@h/db")
    assert url.drivername == "mysql+pymysql"


def test_make_url_roundtrip_preserves_credentials():
    raw = "postgresql+asyncpg://u:p%40ss@h:5432/db?sslmode=require"
    url = asyncpg_ready_url(raw)
    assert url.password == "p@ss"
    assert url.render_as_string(hide_password=False) == (
        "postgresql+asyncpg://u:p%40ss@h:5432/db?ssl=require"
    )
