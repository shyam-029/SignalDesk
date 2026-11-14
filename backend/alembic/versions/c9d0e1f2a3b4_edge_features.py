"""Edge features: frozen monthly pick lists and computed edge snapshots.

Two new tables, nothing else touched. pick_lists holds each rating's top
shares frozen on the first trading night of a month (the public track
record); edge_snapshots holds the weekly similar-setups and Strength
back-test results. Both start empty. Downgrade drops them.

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pick_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("list_date", sa.Date(), nullable=False),
        sa.Column("rating", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=True),
        sa.Column("entry_close", sa.Numeric(16, 4), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "list_date", "rating", "symbol", name="uq_pick_lists_date_rating_symbol"
        ),
    )
    op.create_index("ix_pick_lists_list_date", "pick_lists", ["list_date"])
    op.create_table(
        "edge_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("asof", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("key", name="uq_edge_snapshots_key"),
    )


def downgrade() -> None:
    op.drop_table("edge_snapshots")
    op.drop_index("ix_pick_lists_list_date", table_name="pick_lists")
    op.drop_table("pick_lists")
