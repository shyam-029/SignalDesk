# Ranking repository — all SQL for the top-1000 universe ranking (M1-T2).
#
# Read side: catalog facts + price facts + the market reference calendar.
# Write side: the ranking cycle row, the per-symbol audit trail, the stocks
# ranking-metadata updates (never deletes — E10), and the top1000 universe
# membership rebuild (universe is data, D16; prune+insert like seed.py).

from datetime import date, datetime, timezone

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyPrice,
    RankingAudit,
    RankingCycle,
    Stock,
    Universe,
    stock_universe,
)
from app.services.ranking import (
    RANKED_IN,
    CatalogStock,
    Decision,
    PriceFacts,
    decision_updates,
)

# Chunk size for bulk statements (keeps parameter counts modest).
_CHUNK = 500


async def load_catalog_facts(session: AsyncSession) -> list[CatalogStock]:
    """Every catalog stock with the facts matching needs (id, symbol, isin...)."""
    rows = (
        await session.execute(select(Stock.id, Stock.symbol, Stock.name, Stock.isin, Stock.active))
    ).all()
    return [
        CatalogStock(id=r.id, symbol=r.symbol, name=r.name, isin=r.isin, active=r.active)
        for r in rows
    ]


async def load_price_facts(
    session: AsyncSession,
) -> tuple[dict[int, PriceFacts], tuple[object, ...]]:
    """Per-stock first/last bar dates + the sorted market reference calendar.

    The reference calendar is the set of distinct daily_prices dates across
    the whole market: top-liquid names trade on every NSE trading day, so
    this set approximates the trading calendar without maintaining one (the
    E9 "trading-day gap" is therefore computed from data, not weekdays).
    """
    stats = (
        await session.execute(
            select(
                DailyPrice.stock_id,
                func.min(DailyPrice.date),
                func.max(DailyPrice.date),
            ).group_by(DailyPrice.stock_id)
        )
    ).all()
    facts = {r[0]: PriceFacts(last_bar_date=r[2], first_bar_date=r[1]) for r in stats}

    dates = (
        await session.execute(select(DailyPrice.date).distinct().order_by(DailyPrice.date))
    ).scalars().all()
    return facts, tuple(dates)


async def get_or_create_universe(session: AsyncSession, name: str) -> Universe:
    """Idempotent get-or-create of the ranked universe row (seed.py pattern)."""
    universe = await session.scalar(select(Universe).where(Universe.name == name))
    if universe is None:
        universe = Universe(name=name)
        session.add(universe)
        await session.flush()
    return universe


async def rebuild_universe_membership(
    session: AsyncSession, universe_id: int, stock_ids: list[int]
) -> None:
    """Replace the ranked universe's membership with exactly the ranked-in ids.

    Only association rows inside THIS universe change; no catalog row and no
    other universe is touched. Re-running with the same input is a no-op in
    effect (delete + identical insert).
    """
    await session.execute(
        delete(stock_universe).where(stock_universe.c.universe_id == universe_id)
    )
    values = [{"universe_id": universe_id, "stock_id": sid} for sid in stock_ids]
    if values:
        await session.execute(insert(stock_universe).values(values))


async def upsert_cycle(
    session: AsyncSession,
    cycle_date: date,
    universe_name: str,
    mcap_asof: date | None,
) -> RankingCycle:
    """Get-or-create the cycle row for cycle_date (same-day re-run reuses it)."""
    cycle = await session.scalar(
        select(RankingCycle).where(RankingCycle.cycle_date == cycle_date)
    )
    if cycle is None:
        cycle = RankingCycle(
            cycle_date=cycle_date, universe_name=universe_name, mcap_asof=mcap_asof
        )
        session.add(cycle)
        await session.flush()
    else:
        cycle.universe_name = universe_name
        cycle.mcap_asof = mcap_asof
    return cycle


async def replace_cycle_audit(
    session: AsyncSession, cycle_id: int, decisions: list[Decision]
) -> int:
    """Rebuild this cycle's audit rows deterministically (same-day idempotency).

    Delete-then-insert inside the caller's transaction: the unique anchor
    (cycle_id, symbol) stays valid and the audit content always mirrors the
    latest evaluation. Returns the number of rows written.
    """
    await session.execute(delete(RankingAudit).where(RankingAudit.cycle_id == cycle_id))
    rows = [
        {
            "cycle_id": cycle_id,
            "stock_id": d.stock_id,
            "symbol": d.symbol,
            "catalog_symbol": d.catalog_symbol,
            "series": d.series,
            "isin": d.isin,
            "name": d.name,
            "outcome": d.outcome,
            "reason": d.reason,
            "flag": d.flag,
            "detail": d.detail,
            "mcap": d.mcap,
            "rank": d.rank,
        }
        for d in decisions
    ]
    for i in range(0, len(rows), _CHUNK):
        await session.execute(insert(RankingAudit).values(rows[i : i + _CHUNK]))
    return len(rows)


async def apply_stock_updates(
    session: AsyncSession, decisions: list[Decision], cycle_date: date
) -> int:
    """Apply ranking metadata to stocks rows. Additive only — no deletes.

    active follows this cycle's evaluation (decision 6: one-cycle trigger,
    reversible); a deactivation stamps delisted_reason + delisted_at=now,
    re-activation clears both. Returns the number of stocks updated.

    Executemany requires homogeneous parameter dicts, so updates are grouped
    by their exact key set (ETF/reactivation variants add columns).
    """
    now = datetime.now(timezone.utc)
    params: list[dict] = []
    for d in decisions:
        values = decision_updates(d)
        if not values:
            continue
        if d.deactivate:
            values["delisted_at"] = now
        if d.outcome == RANKED_IN:
            values["mcap_asof"] = cycle_date
        values["stock_id"] = d.stock_id
        params.append(values)

    if not params:
        return 0

    groups: dict[tuple[str, ...], list[dict]] = {}
    for values in params:
        key = tuple(sorted(k for k in values if k != "stock_id"))
        groups.setdefault(key, []).append(values)

    updated = 0
    for key_set, group in groups.items():
        chunk = [{"id": v.pop("stock_id"), **{k: v[k] for k in key_set}} for v in group]
        for i in range(0, len(chunk), _CHUNK):
            await session.execute(update(Stock), chunk[i : i + _CHUNK])
            updated += len(chunk[i : i + _CHUNK])
    return updated


async def ensure_catalog_entries(
    session: AsyncSession,
    new_rows: list[tuple[str, str, str | None]],
) -> int:
    """Create catalog rows for master symbols never seen before (E8 IPO path).

    new_rows: (bare_symbol, name, isin). Symbols stored with the .NS suffix;
    names come from the master (creation, not a rewrite of existing rows —
    decision 8). Returns the number of rows created.
    """
    created = 0
    for bare, name, isin in new_rows:
        symbol = f"{bare}.NS"
        existing = await session.scalar(select(Stock).where(Stock.symbol == symbol))
        if existing is not None:
            continue
        session.add(Stock(symbol=symbol, name=name, isin=isin))
        created += 1
    if created:
        await session.flush()
    return created


async def finalize_cycle(
    session: AsyncSession, cycle_id: int, duration_ms: int
) -> None:
    """Stamp the cycle row as finished (finished_at + duration)."""
    await session.execute(
        update(RankingCycle)
        .where(RankingCycle.id == cycle_id)
        .values(finished_at=datetime.now(timezone.utc), duration_ms=duration_ms)
    )


async def cycle_audit_summary(session: AsyncSession, cycle_id: int) -> dict[str, int]:
    """Outcome counts for one cycle (used by logs and quick sanity checks)."""
    rows = (
        await session.execute(
            select(RankingAudit.outcome, func.count())
            .where(RankingAudit.cycle_id == cycle_id)
            .group_by(RankingAudit.outcome)
        )
    ).all()
    return {outcome: count for outcome, count in rows}


# Ranked-in stock ids for the universe rebuild (kept near the write helpers).
def ranked_in_ids(decisions: list[Decision]) -> list[int]:
    return [d.stock_id for d in decisions if d.outcome == RANKED_IN and d.stock_id]
