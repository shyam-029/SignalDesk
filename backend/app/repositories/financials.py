# Financials repository — hand the ORM snapshot to services as a domain object.
#
# The `financials` table is one row per stock (a point-in-time snapshot), so
# "latest financials" is simply that row. We map it to the Fundamentals dataclass
# (raw values; scores/valuation services normalize percents themselves).

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Financials, Stock
from app.providers.base import Fundamentals


def _to_fundamentals(row: Financials, symbol: str) -> Fundamentals:
    """Map a Financials ORM row onto the Fundamentals dataclass."""
    return Fundamentals(
        symbol=symbol,
        market_cap=_dec(row.market_cap),
        trailing_pe=_dec(row.trailing_pe),
        enterprise_value=_dec(row.enterprise_value),
        ebitda=_dec(row.ebitda),
        price_to_book=_dec(row.price_to_book),
        price_to_sales=_dec(row.price_to_sales),
        return_on_equity=_dec(row.return_on_equity),
        return_on_assets=_dec(row.return_on_assets),
        operating_margin=_dec(row.operating_margin),
        profit_margin=_dec(row.profit_margin),
        debt_to_equity=_dec(row.debt_to_equity),
        interest_coverage=_dec(row.interest_coverage),
        current_ratio=_dec(row.current_ratio),
    )


def _dec(value) -> float | None:
    """Convert a Decimal/None to float (or None). Numeric columns return Decimal."""
    return float(value) if value is not None else None


# Field name -> display key used by the /fundamentals endpoint (key_ratios).
KEY_RATIO_FIELDS: dict[str, str] = {
    "market_cap": "market_cap",
    "trailing_pe": "trailing_pe",
    "enterprise_value": "enterprise_value",
    "ebitda": "ebitda",
    "price_to_book": "price_to_book",
    "price_to_sales": "price_to_sales",
    "return_on_equity": "return_on_equity",
    "return_on_assets": "return_on_assets",
    "operating_margin": "operating_margin",
    "profit_margin": "profit_margin",
    "debt_to_equity": "debt_to_equity",
    "interest_coverage": "interest_coverage",
    "current_ratio": "current_ratio",
}


async def get_financials_row(
    session: AsyncSession, stock: Stock
) -> Financials | None:
    """Return the raw Financials ORM row for a stock (or None)."""
    return await session.scalar(
        select(Financials).where(Financials.stock_id == stock.id)
    )


def to_key_ratios(row: Financials) -> dict[str, float | None]:
    """Flatten a Financials row into a dict of raw values for key_ratios."""
    return {key: _dec(getattr(row, field)) for field, key in KEY_RATIO_FIELDS.items()}


async def get_financials(
    session: AsyncSession, stock: Stock
) -> Fundamentals | None:
    """Return the latest financial snapshot as a Fundamentals object.

    Returns None when the stock has no snapshot row (not yet ingested).
    """
    row = await get_financials_row(session, stock)
    if row is None:
        return None
    return _to_fundamentals(row, stock.symbol)


async def get_financials_batch(
    session: AsyncSession, stocks: list[Stock]
) -> dict[int, Fundamentals | None]:
    """Fetch financial snapshots for many stocks in ONE query (avoids N+1).

    Returns {stock_id: Fundamentals | None} for the given stocks.
    """
    if not stocks:
        return {}
    ids = [s.id for s in stocks]
    rows = (
        await session.execute(
            select(Financials).where(Financials.stock_id.in_(ids))
        )
    ).scalars().all()

    by_id = {s.id: s for s in stocks}
    result: dict[int, Fundamentals | None] = {}
    for row in rows:
        result[row.stock_id] = _to_fundamentals(row, by_id[row.stock_id].symbol)
    for s in stocks:
        result.setdefault(s.id, None)
    return result