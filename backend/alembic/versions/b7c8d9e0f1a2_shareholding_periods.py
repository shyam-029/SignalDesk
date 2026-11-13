"""shareholding_periods: quarterly ownership pattern per stock

Revision ID: b7c8d9e0f1a2
Revises: 9a8b7c6d5e4f
Create Date: 2026-11-13 00:00:00.000000

Checklist section 6, step 3. One row per stock per quarter end with the
percent of shares held by promoters, foreign institutions, other domestic
institutions, mutual funds, and retail/other (Upstox share-holdings).
Additive only: one new table, no existing table or column changes.
Size: about 1,000 stocks x 4 quarters a year of small numeric rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = '9a8b7c6d5e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shareholding_periods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('promoters', sa.Numeric(7, 4), nullable=True),
        sa.Column('fii', sa.Numeric(7, 4), nullable=True),
        sa.Column('other_dii', sa.Numeric(7, 4), nullable=True),
        sa.Column('mutual_funds', sa.Numeric(7, 4), nullable=True),
        sa.Column('retail_and_other', sa.Numeric(7, 4), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_id', 'period_end',
                            name='uq_shareholding_periods_stock_period'),
    )
    op.create_index(
        op.f('ix_shareholding_periods_stock_id'), 'shareholding_periods',
        ['stock_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_shareholding_periods_stock_id'), table_name='shareholding_periods'
    )
    op.drop_table('shareholding_periods')
