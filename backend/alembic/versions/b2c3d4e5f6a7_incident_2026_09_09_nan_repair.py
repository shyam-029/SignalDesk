"""Incident 2026-09-09 repair: purge NaN price bars, retire stale funds

Revision ID: b2c3d4e5f6a7
Revises: a3b4c5d6e7f8
Create Date: 2026-09-10 00:00:00.000000

Repairs data already corrupted by the overwrite bug fixed in code the same
day (provider NaN-row guard + field-level COALESCE upserts):

1. daily_prices / benchmark_prices: yfinance ex-dividend rows came back
   all-NaN OHLC with real volume and the old unconditional upsert stored
   them, destroying previously-good bars (prod: 2,257 NaN close bars across
   2,257 symbols on 2026-09-08, incl. all 16 curated ETFs; NaN serialized as
   null by pydantic -> empty last_price/return fields in the API). The code
   fix drops NaN rows at the provider, which also means the nightly 2y
   refetch will NOT overwrite these stored NaN rows anymore — they must be
   deleted explicitly. Deleting restores honesty: the date becomes a gap
   (like any unpriced day) instead of a fabricated empty row; dates Yahoo
   serves correctly today are re-fetched good by the next nightly run.
   NaN detection uses equality (PostgreSQL treats NaN as equal to itself and
   NULL = 'NaN' is NULL, so NULL-carrying rows survive the predicate).

2. mutual_funds: the three schemes whose AMFI rows are legacy/discontinued
   (empty plan/option, last NAV years old — 100878 HDFC Liquid 2015,
   108467 ICICI Prudential Large Cap 2020, 100357 ICICI Prudential Liquid
   2022) were matched by name-substring first-match and are retired with
   active=false (list_funds filters on active; NAV history is KEPT, not
   dropped — direct URLs stay honest). The matcher now tiers share-class
   matches, so the live Direct-Growth rows win going forward.

Idempotent: re-running deletes 0 and updates 0. The bar deletion is not
reversible from the database (the overwritten good values are gone), but
those dates are provider-refetchable where Yahoo serves them.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NaN detection via equality: PostgreSQL treats NaN as equal to itself
    # (verified PG 17: 'NaN'::numeric = 'NaN'::numeric -> true), and the
    # predicate is NULL-safe (NULL = 'NaN' -> NULL -> row kept).
    op.execute(
        "DELETE FROM daily_prices WHERE open = 'NaN' OR high = 'NaN' "
        "OR low = 'NaN' OR close = 'NaN'"
    )
    op.execute(
        "DELETE FROM benchmark_prices WHERE open = 'NaN' OR high = 'NaN' "
        "OR low = 'NaN' OR close = 'NaN'"
    )
    # Retire the dead schemes matched before share-class tiering (history
    # kept; only list visibility changes via mutual_funds.active).
    op.execute(
        "UPDATE mutual_funds SET active = false "
        "WHERE amfi_code IN ('100878', '108467', '100357')"
    )


def downgrade() -> None:
    # The only reversible step is the fund retirement; deleted NaN bars were
    # never real data (priceless rows) and are not restorable here.
    op.execute(
        "UPDATE mutual_funds SET active = true "
        "WHERE amfi_code IN ('100878', '108467', '100357')"
    )
