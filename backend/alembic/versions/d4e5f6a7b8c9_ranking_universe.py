"""ranking: top-1000 universe audit + stocks ranking metadata

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-09-08 00:00:00.000000

M1-T2 (Plan 7 / 14): market-cap-ranked top-1000 universe.
  - stocks gains the ranking metadata columns (isin, active, delisted_reason,
    delisted_at, mcap_rank, mcap_asof, restrict_flag, is_etf)
  - ranking_cycles: one row per ranking cycle (unique by date)
  - ranking_audit: per-symbol disposition per cycle (the audit trail)
All additive; no existing columns change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stocks', sa.Column('isin', sa.String(length=24), nullable=True))
    op.create_index(op.f('ix_stocks_isin'), 'stocks', ['isin'], unique=False)
    op.add_column(
        'stocks',
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )
    op.add_column('stocks', sa.Column('delisted_reason', sa.String(length=64), nullable=True))
    op.add_column('stocks', sa.Column('delisted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('stocks', sa.Column('mcap_rank', sa.Integer(), nullable=True))
    op.add_column('stocks', sa.Column('mcap_asof', sa.Date(), nullable=True))
    op.add_column('stocks', sa.Column('restrict_flag', sa.String(length=32), nullable=True))
    op.add_column(
        'stocks',
        sa.Column('is_etf', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )

    op.create_table(
        'ranking_cycles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cycle_date', sa.Date(), nullable=False),
        sa.Column('universe_name', sa.String(length=32), nullable=False),
        sa.Column('mcap_asof', sa.Date(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cycle_date', name='uq_ranking_cycles_date'),
    )

    op.create_table(
        'ranking_audit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cycle_id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=True),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('catalog_symbol', sa.String(length=32), nullable=True),
        sa.Column('series', sa.String(length=8), nullable=True),
        sa.Column('isin', sa.String(length=24), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('reason', sa.String(length=32), nullable=True),
        sa.Column('flag', sa.String(length=32), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('mcap', sa.Numeric(20, 2), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['cycle_id'], ['ranking_cycles.id']),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cycle_id', 'symbol', name='uq_ranking_audit_cycle_symbol'),
    )
    op.create_index(
        op.f('ix_ranking_audit_cycle_id'), 'ranking_audit', ['cycle_id'], unique=False
    )
    op.create_index(
        'ix_ranking_audit_cycle_outcome', 'ranking_audit', ['cycle_id', 'outcome'], unique=False
    )
    op.create_index(
        op.f('ix_ranking_audit_stock_id'), 'ranking_audit', ['stock_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_ranking_audit_stock_id'), table_name='ranking_audit')
    op.drop_index('ix_ranking_audit_cycle_outcome', table_name='ranking_audit')
    op.drop_index(op.f('ix_ranking_audit_cycle_id'), table_name='ranking_audit')
    op.drop_table('ranking_audit')
    op.drop_table('ranking_cycles')
    op.drop_index(op.f('ix_stocks_isin'), table_name='stocks')
    op.drop_column('stocks', 'is_etf')
    op.drop_column('stocks', 'restrict_flag')
    op.drop_column('stocks', 'mcap_asof')
    op.drop_column('stocks', 'mcap_rank')
    op.drop_column('stocks', 'delisted_at')
    op.drop_column('stocks', 'delisted_reason')
    op.drop_column('stocks', 'active')
    op.drop_column('stocks', 'isin')
