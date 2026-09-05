# Upstox adapter for MarketDataProvider (Phase 6.5 Part F).
#
# Authentication (verified against the official docs, 2026-09-05): Upstox uses
# OAuth 2.0, but supports "manual token generation" from the developer
# dashboard for non-interactive apps. We consume that token via the standard
# `Authorization: Bearer <token>` header for read-only APIs; no interactive
# OAuth flow is implemented. The token arrives through `settings.upstox_analytics_token`
# (backend/.env), is kept server-side, is never logged, and never reaches the
# frontend.
#
# Endpoints used (v2, all read-only):
#   GET /historical-candle/{instrument_key}/day/{to_date}/{from_date}
#       Daily OHLCV; the API serves at most ~1 year of daily candles per
#       call, so multi-year periods are fetched as sequential windows.
#   GET /fundamentals/{isin}/key-ratios      -> P/E, P/B, ROA, ROE (ratios)
#   GET /fundamentals/{isin}/profile         -> sector classification
#   GET /fundamentals/{isin}/income-statement -> annual revenue/net profit/
#       operating profit (values in CRORE; converted to rupees here so units
#       match the yfinance adapter) + EPS from the full statement.
#
# Instrument resolution: Upstox addresses instruments by
# `NSE_EQ|<ISIN>`, not by trading symbol. The official instruments master
# (https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz)
# maps trading_symbol -> (instrument_key, isin); it is downloaded once per
# process and cached in memory. Fields Upstox does not provide (market cap,
# P/S, EV and EBITDA as absolute values, solvency ratios) stay None: this
# adapter reports limitations instead of inventing values.
#
# httpx is async natively, so no thread offloading is needed here.

import asyncio
import calendar
import gzip
import json
import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

import httpx

from app.providers.base import (
    FinancialPeriodDraft,
    Fundamentals,
    MarketDataError,
    MarketDataProvider,
    OHLCV,
    StockProfile,
)

logger = logging.getLogger(__name__)

# Days per period string (yfinance-style suffixes we ingest).
_PERIOD_DAYS = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 732,
    "5y": 1830,
    "10y": 3660,
    "max": 3660,
}

# Upstox reports income-statement values in crore of rupees.
_CRORE = 1e7

# "Mar 2026" / "Jun 2025" style reporting-period labels.
_PERIOD_LABEL_RE = re.compile(r"^([A-Za-z]{3})\s+(\d{4})$")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_period_label(label: str) -> date | None:
    """Parse an Upstox reporting-period label into a period-end date.

    "Mar 2026" -> 2026-03-31 (Indian fiscal year end), "Jun 2025" ->
    2025-06-30, etc. Returns None for anything unparseable so callers skip
    the period instead of guessing a date.
    """
    if not label:
        return None
    match = _PERIOD_LABEL_RE.match(label.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    year = int(match.group(2))
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_ratio_value(raw) -> float | None:
    """Parse an Upstox ratio value ("20.15", "8.94%", "-") into a float.

    Percent-suffixed ratios are converted to decimals (8.94% -> 0.0894) so
    they match the Fundamentals convention (roe/roa as decimals). Anything
    unparseable becomes None.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in {"-", "--"}:
        return None
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    try:
        value = float(text)
    except ValueError:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value / 100.0 if is_percent else value


def parse_instruments(payload: bytes) -> dict[str, tuple[str, str]]:
    """Parse the NSE instruments master gz into {symbol: (instrument_key, isin)}.

    Only cash-equity rows are kept (segment NSE_EQ, instrument_type EQ), and
    the first occurrence of a symbol wins. This is the symbol -> ISIN bridge
    that lets the rest of the app keep using "RELIANCE.NS" style symbols.
    """
    try:
        entries = json.loads(gzip.decompress(payload).decode("utf-8"))
    except Exception as exc:
        raise MarketDataError(f"Upstox instruments file is unreadable: {exc}") from exc

    out: dict[str, tuple[str, str]] = {}
    for entry in entries:
        if entry.get("segment") != "NSE_EQ" or entry.get("instrument_type") != "EQ":
            continue
        symbol = entry.get("trading_symbol")
        isin = entry.get("isin")
        key = entry.get("instrument_key")
        if not symbol or not isin or not key:
            continue
        out.setdefault(str(symbol).upper(), (str(key), str(isin)))
    return out


class UpstoxProvider(MarketDataProvider):
    """Provider backed by the Upstox v2 REST API (read-only, Bearer token)."""

    name = "upstox"

    BASE_URL = "https://api.upstox.com/v2"
    INSTRUMENTS_URL = (
        "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    )
    # The daily-candle API serves at most about a year per call.
    _WINDOW_DAYS = 365

    def __init__(
        self,
        token: str,
        client: httpx.AsyncClient | None = None,
        instrument_map: dict[str, tuple[str, str]] | None = None,
    ):
        # No credential, no provider: callers fall back to yfinance.
        if not token or not token.strip():
            raise MarketDataError("Upstox token missing; provider not constructed")
        # The token is stored privately, used only in the auth header, and
        # never logged or included in error messages.
        self._token = token.strip()
        self._client = client or httpx.AsyncClient(
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
            timeout=httpx.Timeout(30.0),
        )
        # Optional pre-resolved map (tests / callers that already know ISINs).
        self._instrument_map = instrument_map
        self._instruments: dict[str, tuple[str, str]] | None = instrument_map
        self._instruments_loaded = instrument_map is not None
        self._instruments_lock = asyncio.Lock()

    # --- internals ---------------------------------------------------------

    async def _get_data(self, path: str, params: dict | None = None) -> dict:
        """GET one v2 endpoint and return its `data` object.

        Requests use full URLs (BASE_URL + path) so the join never depends on
        httpx base_url merging. Any transport, HTTP, or envelope failure
        raises MarketDataError with a terse message that never includes the
        token or the raw body.
        """
        try:
            resp = await self._client.get(f"{self.BASE_URL}{path}", params=params)
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Upstox request failed for {path}: {exc}") from exc
        if resp.status_code != 200:
            raise MarketDataError(
                f"Upstox returned HTTP {resp.status_code} for {path}"
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise MarketDataError(f"Upstox returned invalid JSON for {path}") from exc
        if not isinstance(body, dict) or body.get("status") != "success":
            raise MarketDataError(f"Upstox reported an error for {path}")
        data = body.get("data")
        return data if isinstance(data, dict) else (data or {})

    async def _get_instrument(self, symbol: str) -> tuple[str, str]:
        """Resolve "RELIANCE.NS" -> (instrument_key, isin), loading the map once."""
        bare = symbol.split(".")[0].upper()
        if not self._instruments_loaded:
            async with self._instruments_lock:
                if not self._instruments_loaded:
                    await self._load_instruments()
        hit = (self._instruments or {}).get(bare)
        if hit is None:
            raise MarketDataError(f"Upstox instrument not found for {symbol}")
        return hit

    async def _load_instruments(self) -> None:
        try:
            resp = await self._client.get(self.INSTRUMENTS_URL)
            resp.raise_for_status()
            self._instruments = parse_instruments(resp.content)
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Upstox instruments download failed: {exc}") from exc
        self._instruments_loaded = True
        logger.info(
            "Upstox instruments loaded: %d NSE equity entries",
            len(self._instruments or {}),
        )

    async def _candles_window(
        self, instrument_key: str, to_day: date, from_day: date
    ) -> list[list]:
        key = quote(instrument_key, safe="")  # "NSE_EQ|INE..." is path-unsafe
        data = await self._get_data(
            f"/historical-candle/{key}/day/{to_day.isoformat()}/{from_day.isoformat()}"
        )
        candles = data.get("candles")
        return candles if isinstance(candles, list) else []

    # --- MarketDataProvider contract ---------------------------------------

    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        instrument_key, _ = await self._get_instrument(symbol)

        days = _PERIOD_DAYS.get(period)
        if days is None:
            raise MarketDataError(f"Unsupported period '{period}' for Upstox")
        end = date.today()
        start = end - timedelta(days=days)

        by_date: dict[date, OHLCV] = {}
        # Sequential windows, newest first (the API caps daily history at
        # ~1 year per call, so multi-year periods need several requests).
        cursor_end = end
        while cursor_end >= start:
            cursor_start = max(start, cursor_end - timedelta(days=self._WINDOW_DAYS))
            for row in await self._candles_window(instrument_key, cursor_end, cursor_start):
                if not isinstance(row, list) or len(row) < 6:
                    continue  # malformed candle: skip, never guess
                try:
                    bar_date = date.fromisoformat(str(row[0])[:10])
                    bar = OHLCV(
                        date=bar_date,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=int(row[5]),
                        source="upstox",
                    )
                except (TypeError, ValueError):
                    continue
                # Newest window wins on overlap; earlier windows gap-fill.
                by_date.setdefault(bar.date, bar)
            if cursor_start <= start:
                break
            cursor_end = cursor_start - timedelta(days=1)

        return [by_date[d] for d in sorted(by_date)]

    async def get_stock_profile(self, symbol: str) -> StockProfile:
        _, isin = await self._get_instrument(symbol)
        data = await self._get_data(f"/fundamentals/{isin}/profile")
        # Upstox provides sector classification but no company display name;
        # name stays None (the merge fills it from the primary provider).
        return StockProfile(
            symbol=symbol,
            name=None,
            sector=data.get("sector"),
            industry=None,
        )

    async def get_key_ratios(self, symbol: str) -> dict[str, float | None]:
        """Raw named ratios (P/E, P/B, ROA, ROE, ROCE, EV/EBITDA) for a symbol.

        Used by get_fundamentals and by the valuation fallback (a pre-computed
        EV/EBITDA ratio cannot be split into EV and EBITDA, so the fallback
        consumes the ratio directly).
        """
        _, isin = await self._get_instrument(symbol)
        data = await self._get_data(f"/fundamentals/{isin}/key-ratios")
        ratios: dict[str, float | None] = {}
        for entry in data if isinstance(data, list) else []:
            if isinstance(entry, dict) and entry.get("name"):
                ratios[str(entry["name"])] = parse_ratio_value(entry.get("company_value"))
        return ratios

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        _, isin = await self._get_instrument(symbol)
        ratios = await self.get_key_ratios(symbol)

        # Income statement (categories only): fills margins the snapshot lacks.
        op_margin = net_margin = None
        try:
            income = await self._get_data(
                f"/fundamentals/{isin}/income-statement",
                params={"type": "consolidated", "time_period": "yearly"},
            )
            cats: dict[str, dict[str, float]] = {}
            for block in income.get("income_statement") or []:
                if not isinstance(block, dict):
                    continue
                category = str(block.get("category") or "")
                for hist in block.get("history") or []:
                    label = str(hist.get("period") or "")
                    raw = hist.get("value")
                    if not label or raw is None:
                        continue
                    try:
                        cats.setdefault(category, {})[label] = float(raw)
                    except (TypeError, ValueError):
                        continue
            rev = cats.get("revenue", {})
            if rev:
                op = cats.get("operating_profit", {})
                ni = cats.get("net_profit", {})
                # Latest period that has both a numerator and revenue.
                for label in sorted(
                    set(op) | set(ni),
                    key=lambda l: parse_period_label(l) or date.min,
                    reverse=True,
                ):
                    base = rev.get(label)
                    if base:
                        if label in op and op_margin is None:
                            op_margin = op[label] / base
                        if label in ni and net_margin is None:
                            net_margin = ni[label] / base
                    if op_margin is not None and net_margin is not None:
                        break
        except MarketDataError:
            pass  # income enrichment is best-effort; ratios above already stand

        # Balance sheet: current ratio + debt/equity (yfinance omits both often).
        current_ratio = debt_to_equity = None
        try:
            balance = await self._get_data(
                f"/fundamentals/{isin}/balance-sheet",
                params={"type": "consolidated", "fs": "true"},
            )
            lines: dict[str, dict[str, float]] = {}
            for line in balance.get("full_statement") or []:
                if not isinstance(line, dict):
                    continue
                particular = str(line.get("particular") or "")
                for hist in line.get("history") or []:
                    label = str(hist.get("period") or "")
                    raw = hist.get("value")
                    if not label or raw is None:
                        continue
                    try:
                        lines.setdefault(particular, {})[label] = float(raw)
                    except (TypeError, ValueError):
                        continue

            def _latest(particular: str) -> tuple[str, float] | None:
                entries = lines.get(particular, {})
                for label in sorted(
                    entries, key=lambda l: parse_period_label(l) or date.min, reverse=True
                ):
                    if entries[label]:
                        return label, entries[label]
                return None

            ca = _latest("Current Assets")
            cl = _latest("Current Liabilities")
            if ca and cl and ca[0] == cl[0] and cl[1] != 0:
                current_ratio = ca[1] / cl[1]
            tl = _latest("Total Liabilities")
            eq = _latest("Equity Capital")
            if tl and eq and eq[1] != 0:
                # Percent units, matching the yfinance debtToEquity convention.
                debt_to_equity = tl[1] / eq[1] * 100.0
        except MarketDataError:
            pass  # balance enrichment is best-effort

        # Only fields Upstox actually supplies are mapped; the rest stay None.
        # EV/EBITDA arrives as a pre-computed ratio, not as EV and EBITDA
        # values, so neither absolute field can be derived from it.
        return Fundamentals(
            symbol=symbol,
            trailing_pe=ratios.get("P/E"),
            price_to_book=ratios.get("P/B"),
            return_on_equity=ratios.get("ROE"),
            return_on_assets=ratios.get("ROA"),
            operating_margin=op_margin,
            profit_margin=net_margin,
            current_ratio=current_ratio,
            debt_to_equity=debt_to_equity,
        )

    async def get_financial_history(
        self, symbol: str, period_type: str = "annual"
    ) -> list[FinancialPeriodDraft]:
        if period_type not in ("annual", "quarterly"):
            raise MarketDataError(f"Unsupported period_type '{period_type}' for Upstox")
        _, isin = await self._get_instrument(symbol)
        data = await self._get_data(
            f"/fundamentals/{isin}/income-statement",
            params={
                "type": "consolidated",
                "time_period": "yearly" if period_type == "annual" else "quarterly",
                "fs": "true" if period_type == "annual" else "false",
            },
        )

        units = str(data.get("units_in") or "crore").lower()
        if units != "crore":
            # Unknown units cannot be converted honestly; refuse rather than
            # store values in the wrong scale.
            raise MarketDataError(
                f"Upstox income statement units '{units}' are not supported"
            )

        # EPS per reporting-period label; diluted preferred over basic.
        eps_by_label: dict[str, float] = {}
        for line in data.get("full_statement") or []:
            if not isinstance(line, dict):
                continue
            particular = str(line.get("particular") or "")
            if particular not in ("EPS - Diluted", "EPS - Basic"):
                continue
            for hist in line.get("history") or []:
                label = str(hist.get("period") or "")
                value = hist.get("value")
                if label and value is not None:
                    try:
                        if particular == "EPS - Diluted" or label not in eps_by_label:
                            eps_by_label[label] = float(value)
                    except (TypeError, ValueError):
                        continue

        # category -> {period label: value (rupees)}.
        categories: dict[str, dict[str, float]] = {}
        for block in data.get("income_statement") or []:
            if not isinstance(block, dict):
                continue
            category = str(block.get("category") or "")
            if category not in ("revenue", "operating_profit", "net_profit"):
                continue
            for hist in block.get("history") or []:
                label = str(hist.get("period") or "")
                raw = hist.get("value")
                if not label or raw is None:
                    continue
                try:
                    value = float(raw) * _CRORE
                except (TypeError, ValueError):
                    continue
                categories.setdefault(category, {})[label] = value

        def _margins(part: dict[str, float], base: dict[str, float]) -> dict[str, float]:
            return {
                label: part[label] / base[label]
                for label in part
                if label in base and base[label] != 0
            }

        op_margins = _margins(categories.get("operating_profit", {}), categories.get("revenue", {}))
        net_margins = _margins(categories.get("net_profit", {}), categories.get("revenue", {}))

        labels = set(categories.get("revenue", {})) \
            | set(categories.get("operating_profit", {})) \
            | set(categories.get("net_profit", {}))

        periods: list[FinancialPeriodDraft] = []
        for label in labels:
            period_end = parse_period_label(label)
            if period_end is None:
                continue  # unknown period label: skip, never fabricate a date
            rev = categories.get("revenue", {}).get(label)
            ni = categories.get("net_profit", {}).get(label)
            op = categories.get("operating_profit", {}).get(label)
            periods.append(
                FinancialPeriodDraft(
                    period_end=period_end,
                    period_type=period_type,
                    revenue=rev,
                    net_income=ni,
                    operating_margin=op_margins.get(label),
                    net_margin=net_margins.get(label),
                    eps=eps_by_label.get(label),
                    source="upstox",
                )
            )
        return periods
