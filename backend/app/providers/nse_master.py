# Securities master adapter — the ranking candidate source (M1-T2, Plan 7).
#
# DEVIATION NOTE (documented, "or equivalent" clause): Plan 7 named the NSE
# EQUITY_L.csv archive as the master source, but that URL now returns HTTP
# 404 (verified 2026-09-08, httpx and curl, with and without site cookies).
# This module reads the Upstox NSE instruments master instead — the SAME
# public, no-auth endpoint app.providers.upstox_provider already uses for
# the repair pass. Its instrument_type field carries the NSE series codes
# verbatim (EQ ordinary, BE/BZ trade-to-trade, RR REIT, IV InvIT, SG SGB,
# N* debentures), so rule E1's series semantics are unchanged; ISIN and
# company name are present, so E5 matching is unchanged.
#
# This module fetches and parses ONLY. Exclusion decisions live in the pure
# ranking service (app/services/ranking.py) so they stay unit-testable; the
# parser accepts raw gzipped bytes so tests never touch the network.

import asyncio
import gzip
import json
import logging

import httpx

from app.providers.base import MarketDataError

logger = logging.getLogger(__name__)

# Same proven endpoint as upstox_provider (public, no auth, gzipped JSON).
INSTRUMENTS_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
)

# E1 instrument class: ordinary equity shares. EQ = regular series; BE/BZ =
# ordinary equity in trade-to-trade / surveillance segments (eligible but
# flagged restricted_segment). Everything else (RR REITs, IV InvITs, SG SGBs,
# N* debentures, SM SME, ...) is not ordinary equity.
ELIGIBLE_SERIES: frozenset[str] = frozenset({"EQ"})
FLAGGED_SERIES: frozenset[str] = frozenset({"BE", "BZ"})

# Within-symbol series preference when a symbol lists more than once
# (e.g. moved between EQ and BE): the regular series wins.
_SERIES_PREFERENCE = {"EQ": 0, "BE": 1, "BZ": 2}


class NseMasterRow:
    """One securities-master row (a ranking candidate identity).

    symbol is the bare NSE trading symbol; series is the NSE series code as
    carried by the master's instrument_type field.
    """

    __slots__ = ("symbol", "name", "series", "isin")

    def __init__(self, symbol: str, name: str, series: str, isin: str | None):
        self.symbol = symbol
        self.name = name
        self.series = series
        self.isin = isin

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"NseMasterRow({self.symbol!r}, series={self.series!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, NseMasterRow)
            and (self.symbol, self.name, self.series, self.isin)
            == (other.symbol, other.name, other.series, other.isin)
        )

    def __hash__(self) -> int:
        return hash((self.symbol, self.series, self.isin))


def classify_series(series: str) -> str:
    """Classify a NSE series value per rule E1.

    Returns "eligible" (EQ), "flagged" (BE/BZ — eligible with
    restricted_segment flag) or "excluded" (anything else).
    """
    s = (series or "").strip().upper()
    if s in ELIGIBLE_SERIES:
        return "eligible"
    if s in FLAGGED_SERIES:
        return "flagged"
    return "excluded"


def parse_instruments(content: bytes) -> list[NseMasterRow]:
    """Parse the gzipped NSE instruments master into master rows.

    Only NSE_EQ segment rows are candidates (indices/FX/debt segments are
    out). Duplicate trading symbols collapse to their most-preferred series
    (EQ > BE > BZ — the audit trail records one disposition per symbol).
    Rows without a trading symbol are skipped.
    """
    try:
        entries = json.loads(gzip.decompress(content))
    except (OSError, ValueError) as exc:
        raise MarketDataError(f"Securities master unreadable: {exc}") from exc
    if not isinstance(entries, list):
        raise MarketDataError("Securities master: unexpected payload shape")

    by_symbol: dict[str, tuple[int, NseMasterRow]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("segment") != "NSE_EQ":
            continue
        symbol = (entry.get("trading_symbol") or "").strip().upper()
        series = (entry.get("instrument_type") or "").strip().upper()
        if not symbol or not series:
            continue
        row = NseMasterRow(
            symbol=symbol,
            name=(entry.get("name") or "").strip() or symbol,
            series=series,
            isin=(entry.get("isin") or "").strip() or None,
        )
        pref = _SERIES_PREFERENCE.get(series, len(_SERIES_PREFERENCE))
        existing = by_symbol.get(symbol)
        if existing is None or pref < existing[0]:
            by_symbol[symbol] = (pref, row)

    rows = [pair[1] for pair in by_symbol.values()]
    rows.sort(key=lambda r: r.symbol)
    return rows


async def fetch_master(client: httpx.AsyncClient | None = None) -> list[NseMasterRow]:
    """Download + parse the securities master. Raises MarketDataError on failure.

    Failures raise (no silent empty list): the ranking job treats a master
    outage as a whole-pass failure rather than ranking against no candidates.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    try:
        try:
            resp = await client.get(INSTRUMENTS_URL)
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Securities master fetch failed: {exc}") from exc
        if resp.status_code != 200:
            raise MarketDataError(
                f"Securities master returned HTTP {resp.status_code}"
            )
        rows = parse_instruments(resp.content)
        if not rows:
            raise MarketDataError(
                "Securities master parsed to zero rows; refusing to rank"
            )
        logger.info("Securities master loaded: %d rankable-candidate rows", len(rows))
        return rows
    finally:
        if owns_client:
            await client.aclose()


async def fetch_master_with_retry(retries: int = 2) -> list[NseMasterRow]:
    """Fetch the master with bounded retries (master outages are transient)."""
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            return await fetch_master()
        except MarketDataError:
            if attempt >= retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")
