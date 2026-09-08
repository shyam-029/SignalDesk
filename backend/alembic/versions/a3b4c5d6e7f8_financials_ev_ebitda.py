"""financials.ev_ebitda: stored pre-computed EV/EBITDA ratio

Revision ID: a3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Create Date: 2026-09-09 00:00:00.000000

Plan D65 pattern: Upstox supplies EV/EBITDA as a pre-computed ratio (never
as separate EV and EBITDA absolutes), so the snapshot stores the ratio and
relative valuation falls back to it when the absolutes are missing. This
fills the EV/EBITDA gap across the top-1000 without any request-path
provider calls. Additive only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'financials',
        sa.Column('ev_ebitda', sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('financials', 'ev_ebitda')
