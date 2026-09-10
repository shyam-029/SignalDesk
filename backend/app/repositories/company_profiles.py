# Company profile repository — get + idempotent upsert.

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanyProfile


async def get_profile(session: AsyncSession, stock_id: int) -> CompanyProfile | None:
    """Return a stock's stored company profile (or None)."""
    return await session.scalar(
        select(CompanyProfile).where(CompanyProfile.stock_id == stock_id)
    )


async def upsert_profile(
    session: AsyncSession,
    stock_id: int,
    business_summary: str | None,
    ceo: str | None,
    employees: int | None,
    website: str | None,
    source: str | None,
) -> None:
    """Insert or overwrite the stock's profile (idempotent per stock).

    The summary is stored verbatim from the provider; fields the provider
    did not supply stay None (never generated).

    Field-level COALESCE on conflict (incident 2026-09-09, mirrors the
    financials snapshot guard in jobs._fetch_one_financials): a throttled
    provider night returns a sparse info dict, and a naive full overwrite
    destroyed previously-good values. Only columns the provider actually
    supplied change; `source` moves only when at least one field did.
    """
    stmt = pg_insert(CompanyProfile).values(
        stock_id=stock_id,
        business_summary=business_summary,
        ceo=ceo,
        employees=employees,
        website=website,
        source=source,
    )
    supplied = (
        stmt.excluded.business_summary.is_not(None)
        | stmt.excluded.ceo.is_not(None)
        | stmt.excluded.employees.is_not(None)
        | stmt.excluded.website.is_not(None)
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_company_profiles_stock_id",
        set_={
            "business_summary": func.coalesce(
                stmt.excluded.business_summary, CompanyProfile.business_summary
            ),
            "ceo": func.coalesce(stmt.excluded.ceo, CompanyProfile.ceo),
            "employees": func.coalesce(stmt.excluded.employees, CompanyProfile.employees),
            "website": func.coalesce(stmt.excluded.website, CompanyProfile.website),
            "source": case((supplied, stmt.excluded.source), else_=CompanyProfile.source),
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()
