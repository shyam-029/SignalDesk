# Reads and writes on the FUNDS database (second Neon project). Every function
# takes a funds session (app/funds_db/session.py) and never opens one.
#
# Data transfer is the budget to protect: the nightly appends today's NAV
# inside the database (no history is read back) and works out every fund's
# returns inside it too, so only the results leave it.

from datetime import date

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.funds_db.models import Fund, FundHouse, FundReturns, NavHistory
from app.services.fund_catalog import CatalogRow, fund_house_name

CHUNK = 500


async def upsert_houses(session: AsyncSession, amfi_names: set[str]) -> dict[str, int]:
    """{AMFI fund house name: id}, creating missing houses."""
    if amfi_names:
        stmt = pg_insert(FundHouse).values(
            [{"name": fund_house_name(n), "amfi_name": n} for n in sorted(amfi_names)]
        ).on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
    rows = (await session.execute(select(FundHouse.id, FundHouse.amfi_name))).all()
    return {r.amfi_name: r.id for r in rows if r.amfi_name}


async def upsert_funds(
    session: AsyncSession, rows: list[CatalogRow], houses: dict[str, int]
) -> dict[str, int]:
    """Write the catalog (AMFI is the source of every field written here);
    returns {amfi_code: id}. Rows whose values are unchanged are not rewritten."""
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start : start + CHUNK]
        stmt = pg_insert(Fund).values(
            [
                {
                    "amfi_code": r.amfi_code,
                    "isin": r.isin,
                    "fund_house_id": houses.get(r.fund_house),
                    "name": r.name,
                    "asset_group": r.heading.asset_group,
                    "category": r.heading.category,
                    "amfi_category": r.heading.amfi_category,
                    "kind": r.heading.fund_kind,
                    "latest_nav": r.nav,
                    "nav_date": r.nav_date,
                    "source": "amfi",
                    "active": True,
                }
                for r in chunk
            ]
        )
        ex = stmt.excluded
        changed = (
            Fund.name.is_distinct_from(ex.name)
            | Fund.isin.is_distinct_from(ex.isin)
            | Fund.fund_house_id.is_distinct_from(ex.fund_house_id)
            | Fund.category.is_distinct_from(ex.category)
            | Fund.amfi_category.is_distinct_from(ex.amfi_category)
            | Fund.asset_group.is_distinct_from(ex.asset_group)
            | Fund.kind.is_distinct_from(ex.kind)
            | Fund.latest_nav.is_distinct_from(ex.latest_nav)
            | Fund.nav_date.is_distinct_from(ex.nav_date)
            | Fund.active.is_distinct_from(ex.active)
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["amfi_code"],
            set_={
                "name": ex.name,
                "isin": ex.isin,
                "fund_house_id": ex.fund_house_id,
                "category": ex.category,
                "amfi_category": ex.amfi_category,
                "asset_group": ex.asset_group,
                "kind": ex.kind,
                "latest_nav": ex.latest_nav,
                "nav_date": ex.nav_date,
                "source": ex.source,
                "active": ex.active,
                "updated_at": func.now(),
            },
            where=changed,
        )
        await session.execute(stmt)
    codes = [r.amfi_code for r in rows]
    found = (
        await session.execute(select(Fund.amfi_code, Fund.id).where(Fund.amfi_code.in_(codes)))
    ).all()
    return {r.amfi_code: r.id for r in found}


async def deactivate_missing(session: AsyncSession, live_codes: set[str]) -> int:
    """Funds no longer in AMFI's live file are marked inactive (never deleted)."""
    result = await session.execute(
        update(Fund)
        .where(Fund.active.is_(True), Fund.amfi_code.not_in(live_codes))
        .values(active=False, updated_at=func.now())
    )
    return result.rowcount or 0


_APPEND_SQL = text(
    """
    INSERT INTO nav_history AS h (fund_id, yr, days, navs, source)
    VALUES (:fund_id, :yr, ARRAY[CAST(:day AS smallint)], ARRAY[CAST(:nav AS double precision)], 'amfi')
    ON CONFLICT (fund_id, yr) DO UPDATE
    SET days = h.days || EXCLUDED.days,
        navs = h.navs || EXCLUDED.navs,
        updated_at = now()
    WHERE NOT (EXCLUDED.days[1] = ANY (h.days))
    """
)


async def append_navs(session: AsyncSession, points: list[tuple[int, date, float]]) -> int:
    """Add one (fund id, date, NAV) point each, inside the database: no
    history is read back. A day already stored is left as it is."""
    params = [
        {"fund_id": fid, "yr": d.year, "day": d.timetuple().tm_yday, "nav": nav}
        for fid, d, nav in points
    ]
    written = 0
    for start in range(0, len(params), CHUNK):
        result = await session.execute(_APPEND_SQL, params[start : start + CHUNK])
        # The driver reports -1 for a multi-row batch; count only real numbers.
        written += max(result.rowcount or 0, 0)
    return written


async def funds_without_history(session: AsyncSession) -> list[tuple[int, str]]:
    """(id, amfi code) of active funds whose history has not been loaded yet.

    The nightly append gives every fund a row for the current year, so
    "loaded" is marked by launch_date, which write_history sets from the
    first NAV of the full history.
    """
    rows = (
        await session.execute(
            select(Fund.id, Fund.amfi_code)
            .where(Fund.active.is_(True), Fund.launch_date.is_(None))
            .order_by(Fund.id)
        )
    ).all()
    return [(r.id, r.amfi_code) for r in rows]


async def write_history(
    session: AsyncSession,
    fund_id: int,
    packed: dict[int, tuple[list[int], list[float]]],
    source: str,
) -> None:
    """Replace a fund's year rows with `packed` and set its launch date."""
    if not packed:
        return
    stmt = pg_insert(NavHistory).values(
        [
            {"fund_id": fund_id, "yr": yr, "days": days, "navs": navs, "source": source}
            for yr, (days, navs) in packed.items()
        ]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["fund_id", "yr"],
        set_={"days": stmt.excluded.days, "navs": stmt.excluded.navs,
              "source": stmt.excluded.source, "updated_at": func.now()},
    )
    await session.execute(stmt)
    first_year = min(packed)
    first_day = date(first_year, 1, 1).toordinal() + min(packed[first_year][0]) - 1
    await session.execute(
        update(Fund)
        .where(Fund.id == fund_id, Fund.launch_date.is_(None))
        .values(launch_date=date.fromordinal(first_day))
    )


async def get_history(session: AsyncSession, fund_id: int) -> list[tuple[int, list[int], list[float]]]:
    rows = (
        await session.execute(
            select(NavHistory.yr, NavHistory.days, NavHistory.navs)
            .where(NavHistory.fund_id == fund_id)
            .order_by(NavHistory.yr)
        )
    ).all()
    return [(r.yr, list(r.days), list(r.navs)) for r in rows]


# --- Returns, worked out inside the database ---------------------------------
# Same rule as services/funds.window_returns: the anchor is the first NAV at
# or after (latest date - window), and only if it is within 21 days of that
# target; otherwise the window is not covered and stays empty.

WINDOWS = {"1m": 30, "3m": 91, "6m": 182, "1y": 365, "3y": 1095, "5y": 1826, "10y": 3652}
ANCHOR_GAP_DAYS = 21

_ANCHORS_SQL = text(
    """
    WITH f AS (
        SELECT id, nav_date AS last_day, latest_nav::float8 AS last_nav
        FROM funds
        WHERE active AND nav_date IS NOT NULL AND latest_nav > 0
    ),
    w AS (SELECT * FROM unnest(CAST(:labels AS text[]), CAST(:days AS int[])) AS w(label, days))
    SELECT f.id, w.label, w.days, f.last_nav,
           (SELECT u.nav
              FROM nav_history n
              CROSS JOIN LATERAL unnest(n.days, n.navs) AS u(d, nav)
             WHERE n.fund_id = f.id
               AND n.yr BETWEEN extract(year FROM f.last_day - w.days)::int
                            AND extract(year FROM f.last_day - w.days + CAST(:gap AS int))::int
               AND make_date(n.yr, 1, 1) + (u.d - 1)
                   BETWEEN f.last_day - w.days AND f.last_day - w.days + CAST(:gap AS int)
             ORDER BY n.yr, u.d
             LIMIT 1) AS anchor_nav
    FROM f CROSS JOIN w
    """
)

# First NAV ever (since launch) and, over the last three years, the yearly
# volatility of the last year's daily changes and the deepest fall from a peak.
_SERIES_SQL = text(
    """
    WITH f AS (
        SELECT id, nav_date AS last_day FROM funds
        WHERE active AND nav_date IS NOT NULL AND latest_nav > 0
    ),
    first_pt AS (
        SELECT DISTINCT ON (n.fund_id) n.fund_id,
               make_date(n.yr, 1, 1) + (u.d - 1) AS day, u.nav
        FROM nav_history n
        CROSS JOIN LATERAL unnest(n.days, n.navs) AS u(d, nav)
        WHERE n.yr = (SELECT min(yr) FROM nav_history m WHERE m.fund_id = n.fund_id)
        ORDER BY n.fund_id, u.d
    ),
    pts AS (
        SELECT n.fund_id, make_date(n.yr, 1, 1) + (u.d - 1) AS day, u.nav
        FROM nav_history n
        JOIN f ON f.id = n.fund_id
        CROSS JOIN LATERAL unnest(n.days, n.navs) AS u(d, nav)
        WHERE n.yr >= extract(year FROM f.last_day)::int - 3
          AND make_date(n.yr, 1, 1) + (u.d - 1) > f.last_day - 1095
    ),
    moves AS (
        SELECT fund_id, day, nav,
               nav / lag(nav) OVER w - 1.0 AS chg,
               max(nav) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS peak
        FROM pts
        WINDOW w AS (PARTITION BY fund_id ORDER BY day)
    )
    SELECT f.id,
           fp.day AS first_day, fp.nav AS first_nav,
           (SELECT stddev_samp(m.chg) FROM moves m
             WHERE m.fund_id = f.id AND m.day > f.last_day - 365) AS daily_sd,
           (SELECT count(*) FROM moves m
             WHERE m.fund_id = f.id AND m.day > f.last_day - 365) AS year_points,
           (SELECT min(m.nav / m.peak - 1.0) FROM moves m WHERE m.fund_id = f.id) AS drawdown
    FROM f LEFT JOIN first_pt fp ON fp.fund_id = f.id
    """
)


async def return_inputs(session: AsyncSession) -> tuple[list, list]:
    """Rows for services.fund_returns.compute (small: a few per fund)."""
    anchors = (
        await session.execute(
            _ANCHORS_SQL,
            {"labels": list(WINDOWS), "days": list(WINDOWS.values()), "gap": ANCHOR_GAP_DAYS},
        )
    ).all()
    series = (await session.execute(_SERIES_SQL)).all()
    return anchors, series


async def fund_meta(session: AsyncSession) -> dict[int, tuple[str | None, date | None]]:
    rows = (
        await session.execute(
            select(Fund.id, Fund.category, Fund.nav_date).where(Fund.active.is_(True))
        )
    ).all()
    return {r.id: (r.category, r.nav_date) for r in rows}


async def write_returns(session: AsyncSession, rows: list[dict]) -> None:
    """Replace fund_returns with `rows` (latest only)."""
    await session.execute(FundReturns.__table__.delete())
    for start in range(0, len(rows), CHUNK):
        await session.execute(pg_insert(FundReturns).values(rows[start : start + CHUNK]))


# --- Reads for the /funds API ---------------------------------------------------

SORT_COLUMNS = {
    "name": Fund.name,
    "category": Fund.category,
    "latest_nav": Fund.latest_nav,
    "return_1m": FundReturns.ret_1m,
    "return_3m": FundReturns.ret_3m,
    "return_6m": FundReturns.ret_6m,
    "return_1y": FundReturns.ret_1y,
    "return_3y": FundReturns.ret_3y,
    "return_5y": FundReturns.ret_5y,
    "return_10y": FundReturns.ret_10y,
}


def _filters(stmt, *, category, asset_group, q):
    stmt = stmt.where(Fund.active.is_(True))
    if category:
        stmt = stmt.where(Fund.category == category)
    if asset_group:
        stmt = stmt.where(Fund.asset_group == asset_group)
    if q:
        for word in q.split()[:6]:
            stmt = stmt.where(Fund.name.ilike(f"%{word}%"))
    return stmt


async def list_funds_page(
    session: AsyncSession,
    *,
    sort: str,
    direction: str,
    category: str | None,
    asset_group: str | None,
    q: str | None,
    limit: int,
    offset: int,
):
    """(rows of (Fund, FundReturns | None, house name), total matching)."""
    base = (
        select(Fund, FundReturns, FundHouse.name.label("house"))
        .outerjoin(FundReturns, FundReturns.fund_id == Fund.id)
        .outerjoin(FundHouse, FundHouse.id == Fund.fund_house_id)
    )
    base = _filters(base, category=category, asset_group=asset_group, q=q)
    col = SORT_COLUMNS[sort]
    order = col.desc().nulls_last() if direction == "desc" else col.asc().nulls_last()
    rows = (
        await session.execute(base.order_by(order, Fund.name, Fund.id).limit(limit).offset(offset))
    ).all()
    count = select(func.count()).select_from(Fund)
    count = _filters(count, category=category, asset_group=asset_group, q=q)
    total = (await session.execute(count)).scalar() or 0
    return rows, total


async def get_fund_full(session: AsyncSession, fund_id: int):
    """(Fund, FundReturns | None, house name) or None."""
    return (
        await session.execute(
            select(Fund, FundReturns, FundHouse.name.label("house"))
            .outerjoin(FundReturns, FundReturns.fund_id == Fund.id)
            .outerjoin(FundHouse, FundHouse.id == Fund.fund_house_id)
            .where(Fund.id == fund_id)
        )
    ).first()


async def category_counts(session: AsyncSession) -> list[tuple[str | None, str | None, int]]:
    rows = (
        await session.execute(
            select(Fund.asset_group, Fund.category, func.count())
            .where(Fund.active.is_(True))
            .group_by(Fund.asset_group, Fund.category)
            .order_by(Fund.asset_group, Fund.category)
        )
    ).all()
    return [(r[0], r[1], int(r[2])) for r in rows]
