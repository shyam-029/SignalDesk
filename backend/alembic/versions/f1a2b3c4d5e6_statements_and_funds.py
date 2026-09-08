"""statements + funds: balance sheets, mutual funds, MF NAV history

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-08 00:00:00.000000

M1 follow-up (Plan 5.4 / 8 / 14, minimal viable slices):
  - balance_sheet_periods: annual balance-sheet snapshots (drives real
    Altman Z-Scores; yfinance balance_sheet + income_stmt EBIT)
  - mutual_funds / mf_nav_history: curated AMFI fund catalog + daily NAV
    (official NAVAll primary; mfapi.in history backfill as documented
    fallback, source recorded per row)
All additive; no existing columns change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'balance_sheet_periods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('period_type', sa.String(length=16), nullable=False),
        sa.Column('working_capital', sa.Numeric(20, 2), nullable=True),
        sa.Column('total_assets', sa.Numeric(20, 2), nullable=True),
        sa.Column('retained_earnings', sa.Numeric(20, 2), nullable=True),
        sa.Column('ebit', sa.Numeric(20, 2), nullable=True),
        sa.Column('book_equity', sa.Numeric(20, 2), nullable=True),
        sa.Column('total_liabilities', sa.Numeric(20, 2), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_id', 'period_end', 'period_type',
                            name='uq_balance_sheet_periods_stock_period'),
    )
    op.create_index(
        op.f('ix_balance_sheet_periods_stock_id'), 'balance_sheet_periods',
        ['stock_id'], unique=False,
    )

    op.create_table(
        'mutual_funds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('amfi_code', sa.String(length=16), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=True),
        sa.Column('plan', sa.String(length=16), nullable=True),
        sa.Column('option', sa.String(length=16), nullable=True),
        sa.Column('latest_nav', sa.Numeric(12, 4), nullable=True),
        sa.Column('nav_date', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'),
                  nullable=False),
        sa.Column('source', sa.String(length=16), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('amfi_code', name='uq_mutual_funds_amfi_code'),
    )
    op.create_index(
        op.f('ix_mutual_funds_amfi_code'), 'mutual_funds', ['amfi_code'],
        unique=False,
    )

    op.create_table(
        'mf_nav_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fund_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('nav', sa.Numeric(12, 4), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(['fund_id'], ['mutual_funds.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fund_id', 'date', name='uq_mf_nav_history_fund_date'),
    )
    op.create_index(
        op.f('ix_mf_nav_history_fund_id'), 'mf_nav_history', ['fund_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_mf_nav_history_fund_id'), table_name='mf_nav_history')
    op.drop_table('mf_nav_history')
    op.drop_index(op.f('ix_mutual_funds_amfi_code'), table_name='mutual_funds')
    op.drop_table('mutual_funds')
    op.drop_index(op.f('ix_balance_sheet_periods_stock_id'),
                  table_name='balance_sheet_periods')
    op.drop_table('balance_sheet_periods')
