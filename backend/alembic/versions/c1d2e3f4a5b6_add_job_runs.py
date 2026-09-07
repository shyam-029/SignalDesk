"""add job_runs

Revision ID: c1d2e3f4a5b6
Revises: 74b2071c0d29
Create Date: 2026-09-07 00:00:00.000000

Phase 7: durable job-status history for the scheduled ingestion passes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = '74b2071c0d29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'job_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_name', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('items_processed', sa.Integer(), nullable=True),
        sa.Column('items_failed', sa.Integer(), nullable=True),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_job_runs_job_name'), 'job_runs', ['job_name'], unique=False)
    op.create_index('ix_job_runs_job_started', 'job_runs', ['job_name', 'started_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_job_runs_job_started', table_name='job_runs')
    op.drop_index(op.f('ix_job_runs_job_name'), table_name='job_runs')
    op.drop_table('job_runs')
