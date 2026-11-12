"""Widen daily_prices.volume to BIGINT (work list item 18)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-11 00:00:00.000000

daily_prices.volume was a 4-byte INTEGER (max 2,147,483,647). A single day
above 2.1 billion shares for one symbol would make that symbol's whole
upsert fail. benchmark_prices.volume is already BIGINT; this matches it.

INTEGER -> BIGINT rewrites the table and its indexes under an ACCESS
EXCLUSIVE lock, so it briefly needs free space for a second copy of
daily_prices plus its indexes. Run it through migrate.yml outside the
nightly window, after checking Neon headroom. Every existing value fits, so
no data changes. The downgrade narrows back and fails loudly if any stored
volume no longer fits in INTEGER.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "daily_prices",
        "volume",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "daily_prices",
        "volume",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
