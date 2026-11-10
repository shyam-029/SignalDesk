# No-op guard for INSERT ... ON CONFLICT DO UPDATE (Phase 2 remediation).
#
# Postgres writes a NEW row version for every conflicting row an upsert
# touches, even when every value is identical. The nightly passes re-offer
# whole histories (2y of bars, every alpha snapshot), so without a guard each
# run rewrites ~1M unchanged rows: dead tuples, index churn and WAL for
# nothing. These helpers let an upsert:
#   - skip conflicting rows whose new values equal the stored ones
#     (DO UPDATE ... WHERE <any column IS DISTINCT FROM its new value>), and
#   - report what it actually wrote via RETURNING (xmax = 0): True for a new
#     row, False for an updated one. Skipped rows return nothing.
#
# IS DISTINCT FROM (not <>) so NULL compares as a value: NULL -> 5 is a
# change, NULL -> NULL is not.

from typing import Any

from sqlalchemy import ColumnElement, literal_column, or_

# RETURNING expression: xmax is 0 for a freshly inserted row version and the
# locking transaction id for one produced by the ON CONFLICT update.
INSERTED_FLAG = literal_column("(xmax = 0)").label("inserted")


def any_distinct(model: Any, new_values: dict[str, Any]) -> ColumnElement[bool]:
    """WHERE clause: true when any stored column differs from its new value.

    `new_values` maps column name -> the expression the DO UPDATE would set
    (typically from `stmt.excluded`, possibly COALESCEd with the stored
    value). Pass only data columns: bookkeeping columns such as updated_at
    always differ and would defeat the guard.
    """
    return or_(
        *(getattr(model, col).is_distinct_from(expr) for col, expr in new_values.items())
    )
