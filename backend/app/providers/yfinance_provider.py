# yfinance implementation of MarketDataProvider.
#
# yfinance is a synchronous library; calling it would block the async event
# loop. We wrap each call in asyncio.to_thread so it runs in a worker thread
# without stalling the server. Any failure surfaces as MarketDataError, which
# the ingestion job catches per-symbol (D19: one bad symbol never aborts a run).

import asyncio
import logging
import math

import yfinance as yf

logger = logging.getLogger(__name__)

from app.providers.base import (
    CompanyProfile,
    FinancialPeriodDraft,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)


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


def _margin(part: float | None, base: float | None) -> float | None:
    """Compute part/base as a decimal margin; None when not computable.

    A margin is only computed from two real, finite numbers with a non-zero
    base. Anything else stays None (missing values are never invented).
    """
    if part is None or base is None or base == 0:
        return None
    if any(math.isnan(v) or math.isinf(v) for v in (part, base)):
        return None
    return part / base


class YFinanceProvider(MarketDataProvider):
    """Provider backed by Yahoo Finance (yfinance)."""

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        def _fetch() -> list[OHLCV]:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)
            except Exception as exc:  # network/parse errors from yfinance
                logger.warning(
                    "provider_failure provider=yfinance op=price_history symbol=%s error=%s",
                    symbol, exc,
                )
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
                        source="yfinance",
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
                logger.warning(
                    "provider_failure provider=yfinance op=info symbol=%s error=%s",
                    symbol, exc,
                )
                raise MarketDataError(f"yfinance info failed for {symbol}: {exc}") from exc

            return StockProfile(
                symbol=symbol,
                name=info.get("shortName") or info.get("longName"),
                sector=info.get("sector"),
                industry=info.get("industry"),
            )

        return await asyncio.to_thread(_fetch)

    async def get_company_profile(self, symbol: str) -> CompanyProfile:
        """Provider-sourced company background from the yfinance info dict.

        business_summary is Yahoo's own longBusinessSummary text (verbatim,
        never generated). The CEO is read from companyOfficers: the first
        officer whose title marks them chief executive. Fields the info dict
        omits stay None.
        """
        def _fetch() -> CompanyProfile:
            try:
                info = yf.Ticker(symbol).info
            except Exception as exc:
                logger.warning(
                    "provider_failure provider=yfinance op=info symbol=%s error=%s",
                    symbol, exc,
                )
                raise MarketDataError(f"yfinance info failed for {symbol}: {exc}") from exc

            ceo = None
            for officer in info.get("companyOfficers") or []:
                if not isinstance(officer, dict):
                    continue
                title = str(officer.get("title") or "")
                if "chief executive" in title.lower() or title.strip().upper() == "CEO":
                    ceo = officer.get("name") or None
                    break

            return CompanyProfile(
                symbol=symbol,
                business_summary=info.get("longBusinessSummary") or None,
                ceo=ceo,
                employees=info.get("fullTimeEmployees"),
                website=info.get("website") or None,
            )

        return await asyncio.to_thread(_fetch)

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        def _fetch() -> Fundamentals:
            try:
                info = yf.Ticker(symbol).info
            except Exception as exc:
                logger.warning(
                    "provider_failure provider=yfinance op=info symbol=%s error=%s",
                    symbol, exc,
                )
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

    # Annual/quarterly income-statement history (Phase 6.5 Part E). yfinance
    # exposes a few periods of columns on the `income_stmt` /
    # `quarterly_income_stmt` DataFrames: columns = period-end timestamps,
    # index = line items.
    async def get_financial_history(
        self, symbol: str, period_type: str = "annual"
    ) -> list[FinancialPeriodDraft]:
        def _fetch() -> list[FinancialPeriodDraft]:
            try:
                ticker = yf.Ticker(symbol)
                df = (
                    ticker.income_stmt
                    if period_type == "annual"
                    else ticker.quarterly_income_stmt
                )
            except Exception as exc:
                logger.warning(
                    "provider_failure provider=yfinance op=financial_history symbol=%s error=%s",
                    symbol, exc,
                )
                raise MarketDataError(
                    f"yfinance income_stmt failed for {symbol}: {exc}"
                ) from exc

            if df is None or df.empty:
                return []

            def _row(*names: str) -> dict:
                """Map the first matching line item to {period: value}."""
                for name in names:
                    if name in df.index:
                        return df.loc[name].to_dict()
                return {}

            revenue = _row("Total Revenue")
            operating = _row("Operating Income")
            net_income = _row("Net Income")
            eps = _row("Diluted EPS", "Basic EPS")

            periods: list[FinancialPeriodDraft] = []
            for col in df.columns:  # yfinance returns columns newest-first
                # Column labels are pandas Timestamps; .date() is a method.
                try:
                    end = col.date()
                except AttributeError:
                    continue
                rev = _as_float(revenue.get(col))
                ni = _as_float(net_income.get(col))
                oi = _as_float(operating.get(col))
                periods.append(
                    FinancialPeriodDraft(
                        period_end=end,
                        period_type=period_type,
                        revenue=rev,
                        net_income=ni,
                        # Backend-owned math: margins derive from the same
                        # period's figures, or stay None when uncomputable.
                        operating_margin=_margin(oi, rev),
                        net_margin=_margin(ni, rev),
                        eps=_as_float(eps.get(col)),
                        source="yfinance",
                    )
                )
            return periods

        return await asyncio.to_thread(_fetch)