"""Item 6: reclaim index bloat online

Revision ID: 9a8b7c6d5e4f
Revises: b2c3d4e5f6a7
Create Date: 2026-11-12 00:00:00.000000

Measured 2026-11-10 (storage forensics): alpha_scores_pkey 93.8 MB with 0
scans, bloated by the old backfill's nightly delete+insert (fixed in
Phase 2); ix_daily_prices_stock_id (17.2 MB) and ix_alpha_scores_symbol
(9.0 MB) are redundant: the unique constraints (stock_id, date) and
(symbol, date) lead with the same column and serve those lookups.

All three run CONCURRENTLY (no table lock; reads and writes continue), so
they run outside a transaction. Database was 543 MB of the 1,024 MB cap on
2026-11-12; the rebuilt primary key needs roughly 11 MB. Owner approved
2026-11-12. Run through migrate.yml outside the nightly window.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '9a8b7c6d5e4f'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("REINDEX INDEX CONCURRENTLY alpha_scores_pkey")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_daily_prices_stock_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_alpha_scores_symbol")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_daily_prices_stock_id "
            "ON daily_prices (stock_id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_alpha_scores_symbol "
            "ON alpha_scores (symbol)"
        )
