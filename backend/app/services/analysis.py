# Analysis orchestration service — the single place that wires repositories to
# the pure valuation/scoring services.
#
# Design note: `valuation.py` / `scores.py` remain PURE (no I/O). This module is
# the thin DB-aware orchestrator: it resolves stocks, loads fundamentals (batched
# to avoid N+1), and hands them to the pure services. Routers call this instead
# of re-implementing the flow themselves.

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Stock
from app.providers.base import Fundamentals, MarketDataProvider
from app.providers.upstox_provider import UpstoxProvider
from app.repositories import financials as fin_repo
from app.repositories import stocks as stock_repo
from app.services import explanation, scores as score_svc
from app.services import valuation as val_svc
from app.services.valuation import InsufficientDataError, ValuationResult

logger = logging.getLogger(__name__)

# --- Provider fallback for valuation multiples (Phase 6.5 user decision) ----
#
# When the stored snapshot cannot produce a multiple (e.g. yfinance `info`
# omits EBITDA for NBFCs, making EV/EBITDA incomputable), the pre-computed
# ratio is fetched from Upstox key ratios instead of failing the request.
# Results are cached in-process for an hour so a page of four metric queries
# does not hammer the API. The token never leaves this module and is never
# logged.
#
# Request-path rule (M1-T3 500 fix): live provider calls happen ONLY when
# explicitly allowed. Request paths (routers -> compute_stock_valuation)
# serve stored snapshots only; the nightly ingestion enriches the snapshots
# themselves. Before this rule, one /alpha request for an unclassified stock
# fanned out to thousands of sequential Upstox calls (one per NULL-cohort
# "peer" missing a multiple) and never returned.

_RATIO_FOR_METRIC = {"PE": "P/E", "PB": "P/B", "EV_EBITDA": "EV/EBITDA"}
_RATIO_TTL_SECONDS = 3600.0
_ratio_cache: dict[str, tuple[float, dict[str, float | None]]] = {}


async def _upstox_ratio(symbol: str, metric: str) -> float | None:
    """Return the Upstox pre-computed ratio for a metric (None if unavailable)."""
    ratio_name = _RATIO_FOR_METRIC.get(metric)
    if ratio_name is None:
        return None
    token = (settings.upstox_analytics_token or "").strip()
    if not token:
        return None

    cached = _ratio_cache.get(symbol)
    now = time.monotonic()
    if cached is None or now - cached[0] > _RATIO_TTL_SECONDS:
        try:
            provider = UpstoxProvider(token)
            ratios = await provider.get_key_ratios(symbol)
        except Exception as exc:
            logger.info(
                "Upstox ratio fallback unavailable for %s: %s", symbol, exc
            )
            ratios = {}
        _ratio_cache[symbol] = (now, ratios)
        cached = (now, ratios)

    value = cached[1].get(ratio_name)
    if value is not None:
        logger.info(
            "valuation multiple fallback symbol=%s metric=%s ratio=%.4g (upstox)",
            symbol, metric, value,
        )
    return value


async def _multiple_with_fallback(
    metric: str,
    fundamentals: Fundamentals | None,
    symbol: str,
    allow_live_fallback: bool = False,
) -> float | None:
    """Compute a multiple from the snapshot, optionally falling back to Upstox.

    allow_live_fallback=False (request-path default): stored snapshot only,
    never a network call. True (ingestion enrichment only): the pre-computed
    Upstox ratio fills the gap before the request fails.
    """
    if fundamentals is None:
        return await _upstox_ratio(symbol, metric) if allow_live_fallback else None
    value = val_svc.compute_multiple(metric, fundamentals)
    if value is None and allow_live_fallback:
        value = await _upstox_ratio(symbol, metric)
    return value


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
    session: AsyncSession,
    stock: Stock,
    metric: str,
    allow_live_fallback: bool = False,
) -> tuple[ValuationResult, list[str]]:
    """Valuation result + peer symbol list for one stock/metric.

    Raises InsufficientDataError if the target has no financials or an invalid
    multiple; NoPeersError if no valid peer multiples exist. The Upstox ratio
    fallback runs ONLY with allow_live_fallback=True (ingestion enrichment);
    request paths serve stored snapshots only (M1-T3 500 fix).
    """
    fundamentals = await fin_repo.get_financials(session, stock)
    # A missing snapshot falls through to InsufficientDataError below via
    # relative_valuation: request paths serve stored snapshots only (the
    # Upstox ratio fallback needs allow_live_fallback=True; M1-T3 500 fix).
    current = await _multiple_with_fallback(
        metric, fundamentals, stock.symbol, allow_live_fallback
    )

    peers = await stock_repo.get_peers(session, stock)
    peer_fundamentals = await fin_repo.get_financials_batch(session, peers)

    peer_values: list[float | None] = []
    peer_symbols: list[str] = []
    for peer in peers:
        value = await _multiple_with_fallback(
            metric, peer_fundamentals.get(peer.id), peer.symbol, allow_live_fallback
        )
        peer_values.append(value)
        peer_symbols.append(peer.symbol)

    result = val_svc.relative_valuation(
        stock.symbol, metric, current, peer_values
    )
    return result, peer_symbols


async def compute_stock_scores(
    session: AsyncSession, stock: Stock
) -> tuple[score_svc.ComponentScore, score_svc.ComponentScore, str]:
    """Profitability + solvency scores and their combined explanation.

    The Solvency Score methodology is FIXED (D/E 50 / interest coverage 30 /
    current ratio 20): the Altman Z-Score (services/altman.py) is a separate
    diagnostic surfaced on its own endpoint and is never folded in here or
    into the Alpha composite (Part E pipeline decision).
    """
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