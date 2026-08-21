# Analysis orchestration service — the single place that wires repositories to
# the pure valuation/scoring services.
#
# Design note: `valuation.py` / `scores.py` remain PURE (no I/O). This module is
# the thin DB-aware orchestrator: it resolves stocks, loads fundamentals (batched
# to avoid N+1), and hands them to the pure services. Routers call this instead
# of re-implementing the flow themselves.

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stock
from app.repositories import financials as fin_repo
from app.repositories import stocks as stock_repo
from app.services import explanation, scores as score_svc
from app.services import valuation as val_svc
from app.services.valuation import InsufficientDataError, ValuationResult


@dataclass(frozen=True)
class StockAnalysis:
    """Scores + valuation for one stock (used by the screener)."""

    symbol: str
    name: str
    sector: str | None
    industry: str | None
    profitability: int | None
    solvency: int | None
    valuation_status: str | None
    margin_pct: float | None


async def compute_stock_valuation(
    session: AsyncSession, stock: Stock, metric: str
) -> tuple[ValuationResult, list[str]]:
    """Valuation result + peer symbol list for one stock/metric.

    Raises InsufficientDataError if the target has no financials or an invalid
    multiple; NoPeersError if no valid peer multiples exist.
    """
    fundamentals = await fin_repo.get_financials(session, stock)
    if fundamentals is None:
        raise InsufficientDataError(f"No financial data for {stock.symbol}")

    current = val_svc.compute_multiple(metric, fundamentals)

    peers = await stock_repo.get_peers(session, stock)
    peer_fundamentals = await fin_repo.get_financials_batch(session, peers)

    peer_values: list[float | None] = []
    peer_symbols: list[str] = []
    for peer in peers:
        pf = peer_fundamentals.get(peer.id)
        peer_values.append(val_svc.compute_multiple(metric, pf) if pf else None)
        peer_symbols.append(peer.symbol)

    result = val_svc.relative_valuation(
        stock.symbol, metric, current, peer_values
    )
    return result, peer_symbols


async def compute_stock_scores(
    session: AsyncSession, stock: Stock
) -> tuple[score_svc.ComponentScore, score_svc.ComponentScore, str]:
    """Profitability + solvency scores and their combined explanation."""
    fundamentals = await fin_repo.get_financials(session, stock)
    if fundamentals is None:
        raise InsufficientDataError(f"No financial data for {stock.symbol}")

    profit = score_svc.profitability_score(fundamentals)
    solvency = score_svc.solvency_score(fundamentals)
    text = (
        explanation.profitability_explanation(profit)
        + " "
        + explanation.solvency_explanation(solvency)
    )
    return profit, solvency, text


async def analyze_stock(session: AsyncSession, stock: Stock) -> StockAnalysis:
    """Full per-stock analysis for the screener: scores + P/E valuation.

    Never raises for missing peers/data — those become None fields so the
    screener can include/exclude rows without failing the whole request.
    """
    fundamentals = await fin_repo.get_financials(session, stock)

    profit = score_svc.profitability_score(fundamentals) if fundamentals else None
    solvency = score_svc.solvency_score(fundamentals) if fundamentals else None

    valuation_status: str | None = None
    margin: float | None = None
    if fundamentals is not None:
        current = val_svc.compute_multiple("PE", fundamentals)
        peers = await stock_repo.get_peers(session, stock)
        peer_fundamentals = await fin_repo.get_financials_batch(session, peers)
        peer_values = [
            val_svc.compute_multiple("PE", peer_fundamentals.get(p.id))
            if peer_fundamentals.get(p.id)
            else None
            for p in peers
        ]
        try:
            vr = val_svc.relative_valuation(
                stock.symbol, "PE", current, peer_values
            )
            valuation_status = vr.status
            margin = vr.margin_pct
        except (val_svc.NoPeersError, InsufficientDataError):
            valuation_status = None

    return StockAnalysis(
        symbol=stock.symbol,
        name=stock.name,
        sector=stock.sector,
        industry=stock.industry,
        profitability=profit.score if profit else None,
        solvency=solvency.score if solvency else None,
        valuation_status=valuation_status,
        margin_pct=margin,
    )