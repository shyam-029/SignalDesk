# Shared router helpers (symbol normalization + stock resolution).

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models import Stock
from app.repositories import stocks as stock_repo


def normalize_symbol(symbol: str) -> str:
    """Accept 'RELIANCE' or 'reliance.ns' and normalize to 'RELIANCE.NS'."""
    s = symbol.strip().upper()
    if "." not in s:
        s += ".NS"
    return s


async def resolve_stock(session: AsyncSession, symbol: str) -> Stock:
    """Normalize the symbol, look it up, and raise 404 if absent."""
    sym = normalize_symbol(symbol)
    stock = await stock_repo.get_stock(session, sym)
    if stock is None:
        raise NotFoundError(f"Stock {sym} not found", {"symbol": sym})
    return stock