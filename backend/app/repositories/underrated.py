# Batch inputs for the underrated scan (services/underrated.py): a handful of
# queries for the whole universe, never one round trip per stock.

import time
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Financials, FinancialPeriod, Stock
from app.repositories import strength as strength_repo
from app.repositories.stocks import active_universe_filter
from app.services import expectations as exp
from app.services import screener_cache
from app.services import underrated as svc

_LATEST_ALPHA_SQL = text(
    """
    SELECT DISTINCT ON (symbol) symbol, fundamental::float8 AS fundamental,
           (components_json->>'strength')::float8 AS strength
    FROM alpha_scores
    WHERE date >= (SELECT max(date) FROM alpha_scores) - 7
    ORDER BY symbol, date DESC
    """
)

_TTL_S = 1800
_cache: tuple[object, float, list[svc.Result]] | None = None


def reset_cache() -> None:
    global _cache
    _cache = None


def _f(v) -> float | None:
    return float(v) if v is not None else None


async def scan(session: AsyncSession, today: date | None = None) -> list[svc.Result]:
    """Every equity in the active universe, evaluated and ranked.

    Cached for 30 minutes and rebuilt when a job finishes (the same stamp the
    screener uses), so the page costs one small query until data changes.
    """
    global _cache
    stamp = await screener_cache._data_stamp(session)  # noqa: SLF001
    now = time.monotonic()
    if _cache is not None and _cache[0] == stamp and now - _cache[1] < _TTL_S:
        return _cache[2]

    stocks = (
        await session.execute(
            active_universe_filter(
                select(Stock.id, Stock.symbol, Stock.name, Stock.sector).where(
                    Stock.is_etf.is_(False)
                )
            )
        )
    ).all()
    alpha = {r.symbol: r for r in (await session.execute(_LATEST_ALPHA_SQL)).all()}
    caps = {
        r.stock_id: _f(r.market_cap)
        for r in (await session.execute(select(Financials.stock_id, Financials.market_cap))).all()
    }
    quarters: dict[int, list[exp.Quarter]] = {}
    annuals: dict[int, list[exp.Annual]] = {}
    for r in (
        await session.execute(
            select(
                FinancialPeriod.stock_id,
                FinancialPeriod.period_end,
                FinancialPeriod.period_type,
                FinancialPeriod.net_income,
                FinancialPeriod.revenue,
            )
        )
    ).all():
        if r.period_type == "quarterly":
            quarters.setdefault(r.stock_id, []).append(exp.Quarter(r.period_end, _f(r.net_income)))
        elif r.period_type == "annual":
            annuals.setdefault(r.stock_id, []).append(
                exp.Annual(r.period_end, _f(r.net_income), _f(r.revenue))
            )
    facts = await strength_repo.get_price_facts(
        session, today or date.today(), settings.active_universe
    )
    peers = {row.symbol: row for row in await screener_cache.get_rows(session)}

    results: list[svc.Result] = []
    for s in stocks:
        a = alpha.get(s.symbol)
        f = facts.get(s.symbol)
        peer = peers.get(s.symbol)
        from_high = None
        if f is not None and f.last_close and f.high_1y:
            from_high = (f.last_close / f.high_1y - 1.0) * 100.0
        results.append(
            svc.evaluate(
                svc.Inputs(
                    symbol=s.symbol,
                    name=s.name,
                    sector=s.sector,
                    fundamental=a.fundamental if a else None,
                    solvency=float(peer.solvency) if peer and peer.solvency is not None else None,
                    valuation_status=peer.valuation_status if peer else None,
                    strength=a.strength if a else None,
                    from_high_pct=from_high,
                    market_cap=caps.get(s.id),
                    quarters=quarters.get(s.id, []),
                    annuals=annuals.get(s.id, []),
                )
            )
        )
    results.sort(key=svc.rank_key)
    _cache = (stamp, now, results)
    return results
