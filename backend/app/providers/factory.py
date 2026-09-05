# Provider selection (Phase 6.5 Part F).
#
# Priority order per the approved plan: (1) free, (2) consistency and
# availability, (3) update frequency. yfinance is free, needs no key, and is
# already the app's proven source, so it stays PRIMARY. Upstox (when its
# Analytics token is configured) is the SECONDARY that fills gaps and
# missing fields through MergingProvider. Without a token the app operates
# yfinance-only, exactly as before.
#
# The token is read through pydantic-settings from backend/.env, stays
# server-side, and is never logged or exposed to the frontend.

import logging

from app.config import settings
from app.providers.base import MarketDataError, MarketDataProvider
from app.providers.merging import MergingProvider
from app.providers.yfinance_provider import YFinanceProvider
from app.providers.upstox_provider import UpstoxProvider

logger = logging.getLogger(__name__)


def build_default_market_provider() -> MarketDataProvider:
    """Build the ingestion provider: merged (yfinance+Upstox) or yfinance-only."""
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
    logger.info("provider selection: merged (primary=yfinance, secondary=upstox)")
    return MergingProvider(primary, secondary)
