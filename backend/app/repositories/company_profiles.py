# Company profile repository — get + idempotent upsert.

from sqlalchemy import func, select
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
    """
    stmt = pg_insert(CompanyProfile).values(
        stock_id=stock_id,
        business_summary=business_summary,
        ceo=ceo,
        employees=employees,
        website=website,
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_company_profiles_stock_id",
        set_={
            "business_summary": stmt.excluded.business_summary,
            "ceo": stmt.excluded.ceo,
            "employees": stmt.excluded.employees,
            "website": stmt.excluded.website,
            "source": stmt.excluded.source,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()
