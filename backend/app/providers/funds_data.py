# Fund data providers — AMFI NAVAll parser + mfapi.in history (Plan 8/13).
#
# AMFI NAVAll (official, public, no key): semicolon-separated lines
#   code;isin_growth;isin_reinvest;scheme name;plan;option;nav;date
# (older 6-column shape handled defensively: NAV is second-to-last, date
# last). Header/section lines and unparseable rows are skipped, never
# guessed. Pure parsing lives here so tests never touch the network.

import logging
from datetime import date, datetime

import httpx

from app.data.funds import AMFI_NAVALL_URL, CuratedFund, MFAPI_SCHEME_URL
from app.providers.base import MarketDataError

logger = logging.getLogger(__name__)


class AmfiNavRow:
    """One parsed AMFI NAV row."""

    __slots__ = ("code", "name", "plan", "option", "nav", "date")

    def __init__(
        self,
        code: str,
        name: str,
        plan: str | None,
        option: str | None,
        nav: float,
        nav_date: date,
    ):
        self.code = code
        self.name = name
        self.plan = plan
        self.option = option
        self.nav = nav
        self.date = nav_date

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AmfiNavRow({self.code!r}, {self.name[:40]!r}, nav={self.nav})"


def _norm(value: str | None) -> str:
    """Case/whitespace-insensitive comparison key."""
    return " ".join((value or "").split()).lower()


def parse_navall(text: str) -> dict[str, AmfiNavRow]:
    """Parse the AMFI NAVAll payload into {scheme_code: row}.

    Skips headers, blank lines, and any row whose NAV or date cannot be
    parsed (never fabricates). Duplicate codes keep the first occurrence.
    """
    rows: dict[str, AmfiNavRow] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or ";" not in line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6:
            continue
        code = parts[0]
        if not code.isdigit():
            continue  # section header ("Open Ended Schemes(...)" rows)
        nav_raw, date_raw = parts[-2], parts[-1]
        try:
            nav = float(nav_raw)
        except ValueError:
            continue
        if nav != nav or nav <= 0:  # NaN / non-positive
            continue
        try:
            nav_date = datetime.strptime(date_raw, "%d-%b-%Y").date()
        except ValueError:
            continue
        name = parts[3] if len(parts) >= 4 else ""
        plan = parts[4] if len(parts) >= 7 else None
        option = parts[5] if len(parts) >= 7 else None
        if not name:
            continue
        row = AmfiNavRow(
            code=code, name=name, plan=plan or None, option=option or None,
            nav=nav, nav_date=nav_date,
        )
        rows.setdefault(code, row)
    return rows


def match_curated(
    rows: dict[str, AmfiNavRow], curated: CuratedFund
) -> AmfiNavRow | None:
    """Find the AMFI row for one curated entry (name + plan + option).

    Matching is substring-based and case-insensitive because the official
    file writes options inconsistently ("Growth", "Growth Option",
    "GROWTH OPTION") and renames funds periodically (the curated list is
    verified against the live file, 2026-09-08). Returns None when the fund
    is absent from today's file — the catalog simply does not gain a row
    (honest, logged upstream).
    """
    want_name = _norm(curated.match)
    want_plan = _norm(curated.plan)
    want_option = _norm(curated.option)
    for row in rows.values():
        if want_name not in _norm(row.name):
            continue
        if row.plan is not None and want_plan not in _norm(row.plan):
            continue
        if row.option is not None and want_option not in _norm(row.option):
            continue
        return row
    return None


async def fetch_amfi_navall(
    client: httpx.AsyncClient | None = None,
) -> str:
    """Download the official AMFI NAVAll file. Raises MarketDataError."""
    owns = client is None
    client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(60.0), follow_redirects=True
    )
    try:
        try:
            resp = await client.get(AMFI_NAVALL_URL)
        except httpx.HTTPError as exc:
            raise MarketDataError(f"AMFI NAVAll fetch failed: {exc}") from exc
        if resp.status_code != 200:
            raise MarketDataError(f"AMFI NAVAll returned HTTP {resp.status_code}")
        return resp.text
    finally:
        if owns:
            await client.aclose()


async def fetch_mfapi_history(
    code: str, client: httpx.AsyncClient | None = None
) -> list[tuple[date, float]]:
    """One scheme's NAV history from api.mfapi.in (documented fallback).

    Returns [(date, nav)] oldest-first. Rows with unparseable values are
    skipped; an unavailable mirror raises MarketDataError (the caller
    decides whether the backfill is fatal — the AMFI daily NAV still
    stands).
    """
    owns = client is None
    client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(30.0), follow_redirects=True
    )
    try:
        try:
            resp = await client.get(MFAPI_SCHEME_URL.format(code=code))
        except httpx.HTTPError as exc:
            raise MarketDataError(f"mfapi history fetch failed for {code}: {exc}") from exc
        if resp.status_code != 200:
            raise MarketDataError(
                f"mfapi history returned HTTP {resp.status_code} for {code}"
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise MarketDataError(f"mfapi history invalid JSON for {code}") from exc
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return []
        points: list[tuple[date, float]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                nav = float(str(entry.get("nav", "")).strip())
                d = datetime.strptime(str(entry.get("date", "")).strip(), "%d-%m-%Y").date()
            except (TypeError, ValueError):
                continue
            if nav > 0:
                points.append((d, nav))
        points.sort(key=lambda p: p[0])
        return points
    finally:
        if owns:
            await client.aclose()
