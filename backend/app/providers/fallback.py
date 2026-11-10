# Upstox as a PRICE FALLBACK behind Yahoo (owner decision, 2026-11-10).
#
# Yahoo (yfinance) stays the primary source for everything: all stored
# history, technicals and alpha are built on its dividend/split-ADJUSTED
# prices, and switching sources would change what stored prices mean (that
# waits on the adjusted-price-seam decision). Upstox is asked for price bars
# ONLY when Yahoo's answer for a symbol is unusable:
#
#   - Yahoo raised (network error, throttling, parse failure),
#   - Yahoo returned no bars, or
#   - Yahoo's newest bar is older than STALE_AFTER_DAYS (the silently frozen
#     frame seen for RELIANCE/TCS in 2026-09: no error, just old data).
#
# The two series are then merged with Yahoo winning every date it has and
# Upstox filling only the missing dates (merging.merge_price_bars), each bar
# keeping its `source`. Every fallback is logged and counted so the nightly
# summary shows how often Yahoo needed help.
#
# Known trade-off, accepted for the failure case only: Upstox candles are
# exchange (unadjusted) prices, so a filled date can sit inside an adjusted
# series. That beats a frozen or missing series and only happens when Yahoo
# has already failed.
#
# Everything else (fundamentals, statements, profiles, balance sheets) is
# Yahoo-only, exactly as the nightly behaved before the token was available:
# no change to stored financial data.

import logging
from datetime import date, timedelta

from app.providers.base import (
    CompanyProfile,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)
from app.providers.merging import merge_price_bars

logger = logging.getLogger(__name__)

# Same tolerance as jobs.STALE_FRAME_MAX_AGE_DAYS (weekends + a holiday).
STALE_AFTER_DAYS = 5


class PriceFallbackProvider(MarketDataProvider):
    """Yahoo for everything; Upstox price bars only when Yahoo's are unusable."""

    def __init__(
        self,
        primary: MarketDataProvider,
        secondary: MarketDataProvider,
        today: date | None = None,
    ):
        self.primary = primary
        self.secondary = secondary
        self._today = today
        # reason -> count, read by the ingestion pass for its summary.
        self.fallbacks: dict[str, int] = {}
        self.fallback_failures = 0

    def _reason(self, bars: list[OHLCV] | None, error: Exception | None) -> str | None:
        if error is not None:
            return "primary_error"
        if not bars:
            return "primary_empty"
        newest = max(b.date for b in bars)
        if newest < (self._today or date.today()) - timedelta(days=STALE_AFTER_DAYS):
            return "primary_stale"
        return None

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        primary_bars: list[OHLCV] = []
        primary_error: Exception | None = None
        try:
            primary_bars = await self.primary.get_price_history(symbol, period)
        except MarketDataError as exc:
            primary_error = exc

        reason = self._reason(primary_bars, primary_error)
        if reason is None:
            return primary_bars  # the normal night: Yahoo only

        self.fallbacks[reason] = self.fallbacks.get(reason, 0) + 1
        try:
            secondary_bars = await self.secondary.get_price_history(symbol, period)
        except MarketDataError as exc:
            self.fallback_failures += 1
            logger.warning(
                "upstox_fallback symbol=%s reason=%s outcome=secondary_failed error=%s",
                symbol, reason, type(exc).__name__,
            )
            if primary_error is not None:
                raise primary_error
            return primary_bars  # stale/empty Yahoo: the caller's guards decide

        merged = merge_price_bars(primary_bars, secondary_bars)
        logger.info(
            "upstox_fallback symbol=%s reason=%s primary_bars=%d filled_from_upstox=%d",
            symbol, reason, len(primary_bars), len(merged) - len(primary_bars),
        )
        return merged

    # Everything else: Yahoo only (unchanged nightly behaviour).
    async def get_stock_profile(self, symbol: str) -> StockProfile:
        return await self.primary.get_stock_profile(symbol)

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        return await self.primary.get_fundamentals(symbol)

    async def get_balance_sheet(self, *args, **kwargs):
        return await self.primary.get_balance_sheet(*args, **kwargs)

    async def get_financial_history(self, *args, **kwargs):
        return await self.primary.get_financial_history(*args, **kwargs)

    async def get_company_profile(self, symbol: str) -> CompanyProfile:
        return await self.primary.get_company_profile(symbol)
