# MergingProvider — dual-provider facade (Phase 6.5 Part F).
#
# Combines two MarketDataProviders behind the existing abstraction. The
# primary provider (yfinance: free, no key, already proven in this app)
# always wins disagreements; the secondary (Upstox) fills gaps and missing
# fields. If the secondary fails or is unavailable, every method still
# returns the primary's data, so SignalDesk keeps operating yfinance-only.
#
# Merge rules (per the approved plan):
#   PRICES: keyed by date; on overlapping dates the primary bar wins
#           (both are daily bars, so "newest-bar-wins" falls back to the
#           primary as the fresher source); dates only one provider has are
#           gap-filled from the other; per-bar source attribution is kept on
#           OHLCV.source.
#   FINANCIALS: field-level coalesce; non-null beats null; when both providers
#           supply a field and they materially disagree (relative difference
#           beyond DISAGREEMENT_TOLERANCE), the primary value is kept and the
#           disagreement is logged (financial values only, never credentials).
#
# All merge logic is exposed as pure functions so it can be tested without
# any provider or network.

import logging
from collections.abc import Awaitable, Callable

from app.providers.base import (
    FinancialPeriodDraft,
    Fundamentals,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)

logger = logging.getLogger(__name__)

# Relative difference above which two provider values are considered a
# material disagreement (5%). Below it the choice between two plausible
# values is not worth logging or hand-wringing over.
DISAGREEMENT_TOLERANCE = 0.05

_FINANCIAL_FIELDS = ("revenue", "net_income", "operating_margin", "net_margin", "eps")


def _relatively_equal(a: float, b: float, tolerance: float) -> bool:
    """True when two values agree within `tolerance` relative difference."""
    if a == b:
        return True
    denominator = max(abs(a), abs(b))
    if denominator == 0:
        return True
    return abs(a - b) / denominator <= tolerance


def merge_price_bars(
    primary: list[OHLCV], secondary: list[OHLCV]
) -> list[OHLCV]:
    """Merge two bar series: primary wins collisions, secondary fills gaps.

    Returns bars sorted by date ascending with per-bar source attribution
    preserved (OHLCV.source), so a merged series still says where each bar
    came from.
    """
    by_date: dict = {}
    for bar in primary:
        by_date[bar.date] = bar
    for bar in secondary:
        # Primary owns overlapping dates; secondary only fills the gaps.
        by_date.setdefault(bar.date, bar)
    return [by_date[d] for d in sorted(by_date)]


def merge_fundamentals(
    primary: Fundamentals,
    secondary: Fundamentals,
    symbol: str,
    tolerance: float = DISAGREEMENT_TOLERANCE,
) -> Fundamentals:
    """Field-level coalesce of two fundamentals snapshots.

    Non-null beats null; material disagreements keep the primary value and
    are logged (field names and values only — never credentials).
    """
    values: dict[str, object] = {}
    filled: list[str] = []
    for field in (
        "market_cap", "trailing_pe", "enterprise_value", "ebitda",
        "price_to_book", "price_to_sales", "return_on_equity",
        "return_on_assets", "operating_margin", "profit_margin",
        "debt_to_equity", "interest_coverage", "current_ratio",
    ):
        p = getattr(primary, field)
        s = getattr(secondary, field)
        if p is None:
            values[field] = s
            if s is not None:
                filled.append(field)
            continue
        values[field] = p
        if s is not None and not _relatively_equal(float(p), float(s), tolerance):
            logger.info(
                "provider fundamentals disagreement symbol=%s field=%s "
                "primary=%.6g secondary=%.6g (primary kept)",
                symbol, field, float(p), float(s),
            )
    if filled:
        logger.info(
            "provider fundamentals gap-fill symbol=%s fields=%s",
            symbol, ",".join(sorted(filled)),
        )
    return Fundamentals(symbol=symbol, **values)  # type: ignore[arg-type]


def merge_financial_history(
    primary: list[FinancialPeriodDraft],
    secondary: list[FinancialPeriodDraft],
    symbol: str,
    tolerance: float = DISAGREEMENT_TOLERANCE,
) -> list[FinancialPeriodDraft]:
    """Period-level coalesce of two financial-history lists.

    Periods are keyed by (period_type, period_end). The primary value wins
    on material disagreement and is logged; the secondary fills missing
    fields and periods. Row source attribution: the provider that supplied
    every non-null field, or "merged" when fields came from both.
    """
    merged: dict[tuple[str, object], dict] = {}
    for draft in primary:
        key = (draft.period_type, draft.period_end)
        merged[key] = {
            "period_end": draft.period_end,
            "period_type": draft.period_type,
            **{f: getattr(draft, f) for f in _FINANCIAL_FIELDS},
            **{f"{f}_origin": ("primary" if getattr(draft, f) is not None else None)
               for f in _FINANCIAL_FIELDS},
        }
    for draft in secondary:
        key = (draft.period_type, draft.period_end)
        row = merged.setdefault(
            key,
            {
                "period_end": draft.period_end,
                "period_type": draft.period_type,
                **{f: None for f in _FINANCIAL_FIELDS},
                **{f"{f}_origin": None for f in _FINANCIAL_FIELDS},
            },
        )
        for field in _FINANCIAL_FIELDS:
            s = getattr(draft, field)
            p = row[field]
            origin_key = f"{field}_origin"
            if p is None:
                if s is not None:
                    row[field] = s
                    row[origin_key] = "secondary"
                continue
            if s is not None and not _relatively_equal(float(p), float(s), tolerance):
                logger.info(
                    "provider financial history disagreement symbol=%s "
                    "period=%s field=%s primary=%.6g secondary=%.6g (primary kept)",
                    symbol, draft.period_end.isoformat(), field, float(p), float(s),
                )

    periods: list[FinancialPeriodDraft] = []
    for key in sorted(merged.keys(), key=lambda k: (k[1], k[0])):
        row = merged[key]
        origins = [row[f"{f}_origin"] for f in _FINANCIAL_FIELDS if row[f"{f}_origin"]]
        if not origins:
            source = "merged"
        elif all(o == "primary" for o in origins):
            source = "yfinance"
        elif all(o == "secondary" for o in origins):
            source = "upstox"
        else:
            source = "merged"
        periods.append(
            FinancialPeriodDraft(
                period_end=row["period_end"],
                period_type=row["period_type"],
                **{f: row[f] for f in _FINANCIAL_FIELDS},
                source=source,
            )
        )
    return periods


class MergingProvider(MarketDataProvider):
    """Facade combining a primary and a secondary market-data provider.

    The secondary is best-effort: any failure on its side degrades to
    primary-only data for that call (logged, never fatal, never fabricated).
    """

    name = "merged"

    def __init__(self, primary: MarketDataProvider, secondary: MarketDataProvider):
        self.primary = primary
        self.secondary = secondary

    async def _safe(self, role: str, what: str, call: Callable[[], Awaitable]):
        """Run one provider call; return None instead of failing.

        The primary is allowed to fail through to the caller (both providers
        failing is a real error); only the secondary is swallowed here.
        """
        try:
            return await call()
        except NotImplementedError:
            if role == "secondary":
                logger.info("secondary provider lacks %s; skipping", what)
                return None
            raise
        except Exception as exc:
            if role == "secondary":
                logger.info("secondary provider failed for %s: %s", what, exc)
                return None
            raise

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        primary_bars = await self._safe(
            "primary", f"price history {symbol}",
            lambda: self.primary.get_price_history(symbol, period),
        ) or []
        secondary_bars = await self._safe(
            "secondary", f"price history {symbol}",
            lambda: self.secondary.get_price_history(symbol, period),
        ) or []
        merged = merge_price_bars(primary_bars, secondary_bars)
        filled = len(merged) - len(primary_bars)
        if filled > 0:
            logger.info(
                "price merge symbol=%s primary=%d secondary_gapfill=%d total=%d",
                symbol, len(primary_bars), filled, len(merged),
            )
        return merged

    async def get_stock_profile(self, symbol: str) -> StockProfile:
        primary_error: Exception | None = None
        try:
            profile = await self.primary.get_stock_profile(symbol)
        except NotImplementedError:
            raise
        except Exception as exc:
            profile = None
            primary_error = exc
        if profile is None:
            secondary = await self._safe(
                "secondary", f"stock profile {symbol}",
                lambda: self.secondary.get_stock_profile(symbol),
            )
            if secondary is None:
                raise primary_error  # both providers failed
            return secondary
        # Fill whatever identifying fields the primary lacked.
        missing = (profile.name is None, profile.sector is None, profile.industry is None)
        if any(missing):
            secondary = await self._safe(
                "secondary", f"stock profile {symbol}",
                lambda: self.secondary.get_stock_profile(symbol),
            )
            if secondary is not None:
                return StockProfile(
                    symbol=profile.symbol,
                    name=profile.name or secondary.name,
                    sector=profile.sector or secondary.sector,
                    industry=profile.industry or secondary.industry,
                )
        return profile

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        primary_error: Exception | None = None
        try:
            primary = await self.primary.get_fundamentals(symbol)
        except NotImplementedError:
            raise
        except Exception as exc:
            primary = None
            primary_error = exc
        if primary is None:
            secondary = await self._safe(
                "secondary", f"fundamentals {symbol}",
                lambda: self.secondary.get_fundamentals(symbol),
            )
            if secondary is None:
                raise primary_error  # both providers failed
            return secondary
        secondary = await self._safe(
            "secondary", f"fundamentals {symbol}",
            lambda: self.secondary.get_fundamentals(symbol),
        )
        if secondary is None:
            return primary
        return merge_fundamentals(primary, secondary, symbol)

    async def get_financial_history(
        self, symbol: str, period_type: str = "annual"
    ) -> list[FinancialPeriodDraft]:
        primary = await self._safe(
            "primary", f"financial history {symbol}",
            lambda: self.primary.get_financial_history(symbol, period_type),
        )
        if primary is None:
            primary = []
        secondary = await self._safe(
            "secondary", f"financial history {symbol}",
            lambda: self.secondary.get_financial_history(symbol, period_type),
        )
        if secondary is None:
            secondary = []
        return merge_financial_history(primary, secondary, symbol)
