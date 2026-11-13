# Per-stock read memo for the nightly snapshot builder (2026-11-13).
#
# Building one stock's snapshot calls ~17 routes on ONE database session
# (services/stock_snapshot.py). Several routes repeat the same read: alpha
# and technicals both load the last 200 closes, and the four valuation
# multiples each load the peer group's financials twice. Measured locally,
# that repetition was ~30 KB of ~190 KB read per stock.
#
# The builder puts an empty dict in session.info["snapshot_memo"]; the few
# repository functions below return a copy of their first answer for the
# same arguments on that session. The live API never sets the key, so its
# behaviour is unchanged, and a memo lives for one stock's session only
# (about a second), so it cannot serve data older than the reads it saves.

import copy
from typing import Any

MEMO_KEY = "snapshot_memo"


def memo_for(session: Any) -> dict | None:
    """The session's snapshot memo, or None outside the snapshot builder."""
    info = getattr(session, "info", None)
    return info.get(MEMO_KEY) if isinstance(info, dict) else None
