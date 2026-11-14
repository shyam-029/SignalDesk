# The fund catalog from AMFI's daily NAV file (funds database, 2026-11-14).
# Pure parsing, no I/O.
#
# The file is a sequence of blocks:
#
#   Open Ended Schemes(Equity Scheme - Large Cap Fund)     <- category heading
#   Axis Mutual Fund                                       <- fund house
#   code;isin_growth;isin_reinvest;name;plan;option;nav;date
#   ...
#
# Owner decision: direct plans, growth option only (equity, hybrid and debt
# all in scope), plus ETFs, which have no plans. AMFI writes the plan and
# option columns for about 60% of rows; for the rest (blank or "-") the
# share class is read from the scheme name. A scheme whose last NAV is more
# than STALE_DAYS older than the file's newest date is treated as closed.
#
# AMFI spells most categories two ways ("Equity Scheme - Large Cap Fund" and
# "Equity Schemes - Large Cap Fund", "Debt Scheme - Short Duration Fund" and
# "Income/Debt Oriented Schemes - Short Term Fund"); `tidy_category` maps
# them to one label so a category ranks all its funds together.

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

STALE_DAYS = 30

_HEADING = re.compile(r"^(Open Ended|Close Ended|Interval Fund) Schemes\s*\((.*)\)\s*$")

# Second spellings -> the SEBI label used for the category.
_ALIASES = {
    "Banking and PSU Debt Fund": "Banking and PSU Fund",
    "Short Term Fund": "Short Duration Fund",
    "Ultra Short Term Fund": "Ultra Short Duration Fund",
    "Medium Term Fund": "Medium Duration Fund",
    "Medium to Long Term Fund": "Medium to Long Duration Fund",
    "Long Term Fund": "Long Duration Fund",
    "Dynamic Term Fund": "Dynamic Bond",
    "ELSS- Tax Saver Fund": "ELSS",
    "Sectoral Fund": "Sectoral/ Thematic",
    "Thematic Fund": "Sectoral/ Thematic",
    "Balanced Advantage Fund/ Dynamic Asset Allocation": "Balanced Advantage",
    "Dynamic Asset Allocation or Balanced Advantage": "Balanced Advantage",
    "Equity Savings Fund": "Equity Savings",
    "Multi Asset Allocation Fund": "Multi Asset Allocation",
    "Childrens' Fund": "Children's Fund",
    "Children’s Fund": "Children's Fund",
    "Fund of Funds investing overseas": "FoF Overseas",
    "Fund of Funds Scheme (Domestic)": "FoF Domestic",
    "Other ETFs": "Other ETF",
    "ETFs investing overseas": "Overseas ETF",
    "Ultra Short to Short Term Fund": "Low Duration Fund",
}

# Index funds are filed under three headings; the asset is read from the name
# where the heading does not say (a gilt or bond index fund is debt).
_DEBT_INDEX_WORDS = {"gilt", "sdl", "bond", "bonds", "gsec", "g", "psu", "debt", "crisil", "corporate", "tbill", "liquid"}

_WORDS = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class Heading:
    kind: str  # open | closed
    asset_group: str  # equity | hybrid | debt | other
    category: str  # tidied
    amfi_category: str  # verbatim
    fund_kind: str  # open | closed | etf | index | fof


def parse_heading(line: str) -> Heading | None:
    m = _HEADING.match(line.strip())
    if not m:
        return None
    structure, inner = m.group(1), m.group(2).strip()
    group_raw, _, label = inner.partition(" - ")
    group_raw = group_raw.strip()
    label = " ".join(label.split()) or group_raw
    g = group_raw.lower()
    label_l = label.lower()
    kind = "open" if structure == "Open Ended" else "closed"

    if "etf" in g or "etf" in label_l.split():
        fund_kind = "etf"
    elif g.startswith("index funds") or label_l == "index funds":
        fund_kind = "index"
    elif "fund of funds" in g or label_l.startswith("fof"):
        fund_kind = "fof"
    else:
        fund_kind = kind

    if g.startswith("equity") or label_l in ("elss", "equity etf") or "equity funds" in label_l:
        asset_group = "equity"
    elif g.startswith("hybrid") or label_l in ("hybrid etf", "hybrid fund"):
        asset_group = "hybrid"
    elif (
        g.startswith("debt")
        or g.startswith("income")
        or g == "gilt"
        or label_l in ("debt etf", "debt funds")
    ):
        asset_group = "debt"
    elif g == "growth":  # old close-ended equity schemes
        asset_group = "equity"
    else:
        asset_group = "other"

    category = _ALIASES.get(label, label)
    if fund_kind == "index":
        category = {"debt": "Debt Index Funds", "hybrid": "Hybrid Index Funds"}.get(
            asset_group, "Index Funds"
        )
    elif fund_kind == "etf" and not category.lower().endswith("etf"):
        category = f"{category} ETF"
    return Heading(kind, asset_group, category, inner, fund_kind)


def refine_index_heading(h: Heading, name: str) -> Heading:
    """An index fund under the generic 'Index Funds' heading: equity unless
    its name says it tracks bonds."""
    if h.fund_kind != "index" or h.asset_group != "other":
        return h
    words = set(_WORDS.findall(name.lower()))
    if words & _DEBT_INDEX_WORDS:
        return Heading(h.kind, "debt", "Debt Index Funds", h.amfi_category, h.fund_kind)
    return Heading(h.kind, "equity", "Index Funds", h.amfi_category, h.fund_kind)


def is_direct_growth(name: str, plan: str | None, option: str | None) -> bool:
    """Direct plan, growth option, from the columns or else the name."""
    if plan and plan not in ("-",):
        if "direct" not in plan.lower():
            return False
        if option and option not in ("-",):
            return "growth" in option.lower() and "idcw" not in option.lower()
    words = set(_WORDS.findall(name.lower()))
    if plan in (None, "", "-") and "direct" not in words:
        return False
    if words & {"regular", "idcw", "dividend", "bonus", "payout", "reinvestment"}:
        return False
    return "growth" in words


@dataclass(frozen=True)
class CatalogRow:
    amfi_code: str
    isin: str | None
    name: str
    fund_house: str
    heading: Heading
    nav: float
    nav_date: date


def _isin(value: str) -> str | None:
    v = value.strip()
    return v if len(v) == 12 and v.startswith("IN") else None


def parse_catalog(text: str) -> tuple[list[CatalogRow], dict]:
    """Direct growth plans and ETFs with a recent NAV, plus counts for the log."""
    rows: list[CatalogRow] = []
    heading: Heading | None = None
    house: str | None = None
    seen: set[str] = set()
    counts = {"lines": 0, "other_share_class": 0, "unparsed": 0}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ";" not in line:
            h = parse_heading(line)
            if h is not None:
                heading, house = h, None
            else:
                house = line
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 8 or not parts[0].isdigit():
            continue
        counts["lines"] += 1
        if heading is None or house is None:
            counts["unparsed"] += 1
            continue
        code, isin_growth, _, name, plan, option, nav_raw, date_raw = parts[:8]
        if heading.fund_kind != "etf" and not is_direct_growth(
            name, plan or None, option or None
        ):
            counts["other_share_class"] += 1
            continue
        try:
            nav = float(nav_raw)
            nav_date = datetime.strptime(date_raw, "%d-%b-%Y").date()
        except ValueError:
            counts["unparsed"] += 1
            continue
        if not (nav > 0) or code in seen:
            continue
        seen.add(code)
        rows.append(CatalogRow(
            code, _isin(isin_growth), name, house, refine_index_heading(heading, name),
            nav, nav_date,
        ))
    newest = max((r.nav_date for r in rows), default=None)
    if newest is not None:
        cutoff = newest - timedelta(days=STALE_DAYS)
        live = [r for r in rows if r.nav_date >= cutoff]
        counts["stale"] = len(rows) - len(live)
        rows = live
    counts["kept"] = len(rows)
    counts["newest"] = newest
    return rows, counts


def fund_house_name(amfi_name: str) -> str:
    """'Axis Mutual Fund' -> 'Axis'; kept verbatim otherwise."""
    name = " ".join(amfi_name.split())
    for suffix in (" Mutual Fund", " Mutual fund", " MF"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name
