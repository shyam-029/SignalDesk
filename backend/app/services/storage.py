# Storage guardrails (M2-T1): canary projection + retention gate math.
#
# Pure functions, no I/O, no DB, no network. Numbers come from two places:
#   - the pinned operational constants below (measured production facts,
#     refreshed whenever a db-probe run reports a new reality), and
#   - live arguments callers pass (the retention pass measures the actual
#     database size; tests pass synthetic sizes).
#
# Measured facts they pin (SEMESTER2_PROGRESS sections 8/12.3, 2026-09-09):
#   - Neon free plan hard cap: 0.5 GB = 512,000,000 bytes (NOT 512 MiB;
#     exceeding it suspends compute until the next billing month).
#   - Production baseline: 383 MB used (db-probe, 2026-09-09).
#   - Steady-state growth: ~0.6-1.0 MB/day (prices + alpha snapshots +
#     news at top-1000 breadth).
#   - Plan 22 first cut: alpha backfill depth to 1y outside top 250,
#     saving up to ~100 MB.

BYTES_PER_MB = 1_000_000

# Neon free plan hard cap (work log measurement convention: 512,000,000 B).
NEON_CAP_BYTES = 512_000_000

# Production database size at the last probe (2026-09-09: 383 MB).
# Refresh after every db-probe run so the canary tracks reality.
BASELINE_BYTES = 383_000_000

# Measured steady-state daily growth band (low, high) in bytes/day.
GROWTH_BYTES_PER_DAY = (600_000, 1_000_000)

# Retention gate: the first cut fires at or above this many MB (owner
# decision, 2026-09-09: canary + gated cut, never proactive).
DEFAULT_CUT_THRESHOLD_MB = 450

# Plan 22 note: the alpha-depth cut saves up to ~100 MB when it fires
# (documented estimate; the pass reports the real rowcount).
CUT_SAVINGS_ESTIMATE_MB = 100


def project_bytes(used_bytes: int, bytes_per_day: int, days: int) -> int:
    """Linear byte projection after `days` at a fixed daily growth rate.

    Steady-state growth is bars + daily snapshots + news, which accrue
    linearly at top-1000 breadth, so a linear model is the honest default;
    statement/dividend additions change the baseline, not the slope.
    """
    return used_bytes + bytes_per_day * days


def headroom_bytes(used_bytes: int, cap_bytes: int = NEON_CAP_BYTES) -> int:
    """Bytes remaining before the hard cap."""
    return cap_bytes - used_bytes


def cut_gate_fires(
    used_bytes: int, threshold_mb: int = DEFAULT_CUT_THRESHOLD_MB
) -> bool:
    """True when the retention cut should fire: size AT or ABOVE threshold.

    The gate is >= on purpose: exactly at the threshold the headroom left
    (cap - threshold) is smaller than the cut's own documented savings, so
    waiting longer buys nothing.
    """
    return used_bytes >= threshold_mb * BYTES_PER_MB


def canary_verdict(
    used_bytes: int = BASELINE_BYTES,
    horizons: tuple[int, ...] = (30, 60, 90),
) -> dict:
    """Worst-case cap projection for the canary test (CI-visible alarm).

    Projects every horizon at the HIGH end of the measured growth band and
    reports `ok` only when ALL horizons stay at or under the hard cap. The
    pinned baseline makes this test a live alarm: when a db-probe refresh
    of BASELINE_BYTES (or a real growth-rate change) pushes the projection
    past the cap, CI goes red and the gated retention cut becomes due.
    """
    low, high = GROWTH_BYTES_PER_DAY
    projections = {
        f"day_{h}": round(project_bytes(used_bytes, high, h) / BYTES_PER_MB, 1)
        for h in horizons
    }
    ok = all(mb * BYTES_PER_MB <= NEON_CAP_BYTES for mb in projections.values())
    return {
        "used_mb": round(used_bytes / BYTES_PER_MB, 1),
        "cap_mb": NEON_CAP_BYTES // BYTES_PER_MB,
        "headroom_mb": round(headroom_bytes(used_bytes) / BYTES_PER_MB, 1),
        "growth_mb_per_day_band": (
            round(low / BYTES_PER_MB, 2),
            round(high / BYTES_PER_MB, 2),
        ),
        "projections_worst_case_mb": projections,
        "ok": ok,
        "cut_threshold_mb": DEFAULT_CUT_THRESHOLD_MB,
        "cut_fires_at_baseline": cut_gate_fires(used_bytes),
    }
