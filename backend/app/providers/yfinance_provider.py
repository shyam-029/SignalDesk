# yfinance implementation of MarketDataProvider.
#
# yfinance is a synchronous library; calling it would block the async event
# loop. We wrap each call in asyncio.to_thread so it runs in a worker thread
# without stalling the server. Any failure surfaces as MarketDataError, which
# the ingestion job catches per-symbol (D19: one bad symbol never aborts a run).

import asyncio

import yfinance as yf

from app.providers.base import (
    Fundamentals,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)


class MarketDataError(Exception):
    """Raised when a market data provider fails for a specific symbol."""


def _as_float(value) -> float | None:
    """Safely coerce a provider value to float; return None if unusable.

    yfinance sometimes returns strings, NaN, or "Infinity" for missing fields;
    those become None so downstream code treats them as "not supplied".
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf checks
        return None
    return f


class YFinanceProvider(MarketDataProvider):
    """Provider backed by Yahoo Finance (yfinance)."""

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        def _fetch() -> list[OHLCV]:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)
            except Exception as exc:  # network/parse errors from yfinance
                raise MarketDataError(f"yfinance history failed for {symbol}: {exc}") from exc

            if hist is None or hist.empty:
                return []

            bars: list[OHLCV] = []
            for idx, row in hist.iterrows():
                bars.append(
                    OHLCV(
                        date=idx.date(),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )
            return bars

        # Run the blocking yfinance call off the event loop.
        return await asyncio.to_thread(_fetch)

    async def get_stock_profile(self, symbol: str) -> StockProfile:
        def _fetch() -> StockProfile:
            try:
                info = yf.Ticker(symbol).info
            except Exception as exc:
                raise MarketDataError(f"yfinance info failed for {symbol}: {exc}") from exc

            return StockProfile(
                symbol=symbol,
                name=info.get("shortName") or info.get("longName"),
                sector=info.get("sector"),
                industry=info.get("industry"),
            )

        return await asyncio.to_thread(_fetch)

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        def _fetch() -> Fundamentals:
            try:
                info = yf.Ticker(symbol).info
            except Exception as exc:
                raise MarketDataError(f"yfinance info failed for {symbol}: {exc}") from exc

            return Fundamentals(
                symbol=symbol,
                market_cap=_as_float(info.get("marketCap")),
                trailing_pe=_as_float(info.get("trailingPE")),
                enterprise_value=_as_float(info.get("enterpriseValue")),
                ebitda=_as_float(info.get("ebitda")),
                price_to_book=_as_float(info.get("priceToBook")),
                price_to_sales=_as_float(
                    info.get("priceToSalesTrailing12Months")
                ),
                # Profitability — raw decimals from the provider (0.18 = 18%).
                return_on_equity=_as_float(info.get("returnOnEquity")),
                return_on_assets=_as_float(info.get("returnOnAssets")),
                operating_margin=_as_float(info.get("operatingMargins")),
                profit_margin=_as_float(info.get("profitMargins")),
                # Solvency.
                debt_to_equity=_as_float(info.get("debtToEquity")),
                interest_coverage=_as_float(info.get("interestCoverage")),
                current_ratio=_as_float(info.get("currentRatio")),
            )

        return await asyncio.to_thread(_fetch)