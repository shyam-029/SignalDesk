# Mutual-fund repository — curated AMFI catalog + NAV history (Plan 8/14).
#
# Catalog anchor: amfi_code (official AMFI scheme code, unique). NAV anchor:
# (fund_id, date). The daily AMFI NAVAll file is primary; mfapi.in backfill
# rows carry source='mfapi' so provenance stays queryable (Plan 13).

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MutualFund, MutualFundNav


async def get_or_create_fund(
    session: AsyncSession,
    amfi_code: str,
    name: str,
    category: str | None = None,
    plan: str | None = None,
    option: str | None = None,
) -> MutualFund:
    """Get-or-create one fund row by AMFI code; refresh AMFI's verbatim name."""
    row = await session.scalar(
        select(MutualFund).where(MutualFund.amfi_code == str(amfi_code))
    )
    if row is None:
        row = MutualFund(
            amfi_code=str(amfi_code),
            name=name,
            category=category,
            plan=plan,
            option=option,
        )
        session.add(row)
        await session.flush()
        return row
    if name and row.name != name:
        row.name = name
    if plan and row.plan != plan:
        row.plan = plan
    if option and row.option != option:
        row.option = option
    return row


async def upsert_navs(
    session: AsyncSession, fund_id: int, points: list[tuple[date, float, str]]
) -> int:
    """Bulk-upsert NAV points [(date, nav, source)]; rows offered returned."""
    if not points:
        return 0
    stmt = pg_insert(MutualFundNav).values(
        [
            {"fund_id": fund_id, "date": d, "nav": nav, "source": src}
            for d, nav, src in points
        ]
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_mf_nav_history_fund_date",
        set_={"nav": stmt.excluded.nav, "source": stmt.excluded.source},
    )
    await session.execute(stmt)
    await session.commit()
    return len(points)


async def refresh_latest_nav(session: AsyncSession, fund_id: int) -> None:
    """Mirror the newest NAV row onto the fund's latest_nav/nav_date."""
    latest = await session.scalar(
        select(MutualFundNav)
        .where(MutualFundNav.fund_id == fund_id)
        .order_by(MutualFundNav.date.desc())
        .limit(1)
    )
    fund = await session.get(MutualFund, fund_id)
    if fund is not None and latest is not None:
        fund.latest_nav = latest.nav
        fund.nav_date = latest.date
        fund.source = latest.source
    await session.commit()


async def list_funds(session: AsyncSession) -> list[MutualFund]:
    """All active curated funds, ordered by category then name."""
    rows = await session.execute(
        select(MutualFund)
        .where(MutualFund.active.is_(True))
        .order_by(MutualFund.category, MutualFund.name)
    )
    return list(rows.scalars())


async def get_fund(session: AsyncSession, fund_id: int) -> MutualFund | None:
    return await session.get(MutualFund, fund_id)


async def get_nav_series(
    session: AsyncSession, fund_id: int, limit: int | None = None
) -> list[MutualFundNav]:
    """NAV rows oldest-first (bounded to the most recent `limit` points)."""
    q = (
        select(MutualFundNav)
        .where(MutualFundNav.fund_id == fund_id)
        .order_by(MutualFundNav.date.desc())
    )
    if limit is not None:
        q = q.limit(limit)
    rows = (await session.execute(q)).scalars().all()
    return sorted(rows, key=lambda r: r.date)
