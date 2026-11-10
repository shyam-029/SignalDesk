# Provider selection (Phase 6.5 Part F; fallback mode 2026-11-10).
#
# yfinance is free, needs no key, and is the source every stored price,
# technical and alpha score is built on, so it stays PRIMARY for everything.
# When an Upstox Analytics token is configured, Upstox is a PRICE FALLBACK
# only (providers/fallback.py): it is asked for bars only when Yahoo's answer
# for a symbol is an error, empty or stale. Fundamentals, statements and
# profiles stay Yahoo-only. Without a token the app is yfinance-only.
#
# (MergingProvider, which queries both sources for every call and merges
# field by field, is kept for tests and manual use; the nightly no longer
# uses it: it doubled provider calls and mixed sources on normal nights.)
#
# The token is read through pydantic-settings (backend/.env locally, the
# UPSTOX_ANALYTICS_TOKEN secret in Actions), stays server-side, and is never
# logged or exposed to the frontend.

import logging

from app.config import settings
from app.providers.base import MarketDataError, MarketDataProvider
from app.providers.fallback import PriceFallbackProvider
from app.providers.yfinance_provider import YFinanceProvider
from app.providers.upstox_provider import UpstoxProvider

logger = logging.getLogger(__name__)


def build_default_market_provider() -> MarketDataProvider:
    """Build the ingestion provider: Yahoo, with Upstox price fallback if configured."""
    primary = YFinanceProvider()
    token = (settings.upstox_analytics_token or "").strip()
    if not token:
        logger.info("provider selection: yfinance only (no Upstox token configured)")
        return primary
    try:
        secondary = UpstoxProvider(token)
    except MarketDataError:
        logger.info("provider selection: yfinance only (Upstox unavailable)")
        return primary
    logger.info("provider selection: yfinance, with Upstox price fallback")
    return PriceFallbackProvider(primary, secondary)
