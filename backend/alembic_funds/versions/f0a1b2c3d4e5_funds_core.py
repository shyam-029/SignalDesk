"""Funds database, first tables: fund houses, funds, packed NAV history,
latest returns and monthly facts.

Schema from session 4's plan (2026-11-14). Holdings tables come later in
their own migration. Downgrade drops all five tables.

Revision ID: f0a1b2c3d4e5
Revises:
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fund_houses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("amfi_name", sa.Text(), nullable=True),
    )
    op.create_table(
        "funds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amfi_code", sa.String(16), nullable=False, unique=True),
        sa.Column("isin", sa.String(24), nullable=True),
        sa.Column("fund_house_id", sa.Integer(), sa.ForeignKey("fund_houses.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("asset_group", sa.String(16), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("amfi_category", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=True),
        sa.Column("benchmark", sa.Text(), nullable=True),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("min_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("etf_symbol", sa.String(32), nullable=True),
        sa.Column("latest_nav", sa.Numeric(14, 4), nullable=True),
        sa.Column("nav_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_funds_isin", "funds", ["isin"])
    op.create_index("ix_funds_fund_house_id", "funds", ["fund_house_id"])
    op.create_index("ix_funds_category", "funds", ["category"])
    op.create_table(
        "nav_history",
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id"), primary_key=True),
        sa.Column("yr", sa.SmallInteger(), primary_key=True),
        sa.Column("days", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("navs", postgresql.ARRAY(sa.Double()), nullable=False),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "cardinality(days) = cardinality(navs)", name="ck_nav_history_same_length"
        ),
    )
    op.create_table(
        "fund_returns",
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id"), primary_key=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        *[
            sa.Column(name, sa.Numeric(10, 4), nullable=True)
            for name in (
                "ret_1m", "ret_3m", "ret_6m", "ret_1y", "ret_3y", "ret_5y",
                "ret_10y", "ret_since_launch",
            )
        ],
        sa.Column("category_rank", sa.Integer(), nullable=True),
        sa.Column("category_size", sa.Integer(), nullable=True),
        sa.Column("volatility_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_drawdown_pct", sa.Numeric(10, 4), nullable=True),
    )
    op.create_table(
        "fund_facts_monthly",
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id"), primary_key=True),
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("aum_cr", sa.Numeric(16, 2), nullable=True),
        sa.Column("expense_ratio_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("regular_expense_ratio_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("turnover_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("manager", sa.Text(), nullable=True),
        sa.Column("ytm_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("avg_maturity_yrs", sa.Numeric(8, 3), nullable=True),
        sa.Column("mod_duration_yrs", sa.Numeric(8, 3), nullable=True),
        sa.Column("credit_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fund_facts_monthly")
    op.drop_table("fund_returns")
    op.drop_table("nav_history")
    op.drop_index("ix_funds_category", table_name="funds")
    op.drop_index("ix_funds_fund_house_id", table_name="funds")
    op.drop_index("ix_funds_isin", table_name="funds")
    op.drop_table("funds")
    op.drop_table("fund_houses")
