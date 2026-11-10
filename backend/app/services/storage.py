# Storage guardrails (M2-T1): canary projection + retention gate math.
#
# Pure functions, no I/O, no DB, no network. Numbers come from two places:
#   - the pinned operational constants below (measured production facts,
#     refreshed whenever a db-probe run reports a new reality), and
#   - live arguments callers pass (the retention pass measures the actual
#     database size; tests pass synthetic sizes).
#
# Measured facts they pin (remediation log, Phase 1, 2026-11-10):
#   - Neon enforced limit: neon.max_cluster_size = 1024 MB (read from the
#     production database by the Phase 1 db-probe; the earlier 0.5 GB
#     assumption was wrong).
#   - Production size: 561,414,144 bytes on 2026-11-10 (pg_database_size,
#     which INCLUDES dead-tuple and index bloat).
#   - Growth: 383 MB on 2026-09-09 to 561 MB on 2026-11-10 is ~2.9 MB/day,
#     a figure inflated by nightly rewrite churn that Phase 2 removes. The
#     band below is deliberately wide until a post-Phase-2 probe narrows it.
#   - Alpha pruning is NOT enabled (owner rule). Nothing here deletes data.

BYTES_PER_MB = 1_000_000

# Neon enforced limit: 1024 MB, as reported by neon.max_cluster_size.
NEON_CAP_BYTES = 1024 * 1024 * 1024

# Production database size at the last probe (2026-11-10: 561,414,144 B).
# Refresh after every db-probe run so the canary tracks reality.
BASELINE_BYTES = 561_414_144

# Daily growth band (low, high) in bytes/day: from the post-Phase-2 hope
# (~1 MB/day) up to the observed 2026-09-09..2026-11-10 rate (~3.1 MB/day).
GROWTH_BYTES_PER_DAY = (1_000_000, 3_100_000)

# Advisory alarm level (MB): the canary workflow and test raise an alarm at
# or above this. It is NOT a deletion trigger. Keep in sync with
# .github/workflows/backup.yml and settings.storage_cut_threshold_mb.
DEFAULT_CUT_THRESHOLD_MB = 800

# Plan 22 note: the alpha-depth cut would save up to ~100 MB if the owner
# ever approves it (documented estimate only).
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
    """True when the size alarm should be raised: size AT or ABOVE threshold.

    ADVISORY ONLY (used by the canary report). It must never gate a
    deletion: pg_database_size includes bloat, so crossing the line does not
    mean live data grew.
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
