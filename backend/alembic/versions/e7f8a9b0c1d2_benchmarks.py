"""benchmarks: index price store for M1-T6 (Plan 13, 14, 24/M1)

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-09-08 00:00:00.000000

M1-T6: benchmark index ingestion (^NSEI, ^NSEBANK, ^CNXIT, ^CRSLDX).
  - benchmarks: one row per index symbol (unique anchor for upserts)
  - benchmark_prices: OHLCV per index per date (unique anchor for idempotency)

Design: benchmarks live OUTSIDE the equity catalog on purpose. Reusing
daily_prices via linked Stock rows (one Plan 14 sketch) would pollute the
equity universe: benchmark rows would appear in /stocks, /screener and peer
sets. Separate tables keep benchmark data from interfering with equity
ranking/valuation while reusing the same OHLCV shape and upsert pattern.
All additive; no existing columns change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'benchmarks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('kind', sa.String(length=16), nullable=False,
                  server_default=sa.text("'index'")),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', name='uq_benchmarks_symbol'),
    )
    op.create_index(op.f('ix_benchmarks_symbol'), 'benchmarks', ['symbol'], unique=False)

    op.create_table(
        'benchmark_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('benchmark_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open', sa.Numeric(16, 4), nullable=False),
        sa.Column('high', sa.Numeric(16, 4), nullable=False),
        sa.Column('low', sa.Numeric(16, 4), nullable=False),
        sa.Column('close', sa.Numeric(16, 4), nullable=False),
        sa.Column('volume', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['benchmark_id'], ['benchmarks.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'benchmark_id', 'date', name='uq_benchmark_prices_benchmark_date'
        ),
    )
    op.create_index(
        op.f('ix_benchmark_prices_benchmark_id'), 'benchmark_prices',
        ['benchmark_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_benchmark_prices_benchmark_id'), table_name='benchmark_prices')
    op.drop_table('benchmark_prices')
    op.drop_index(op.f('ix_benchmarks_symbol'), table_name='benchmarks')
    op.drop_table('benchmarks')
