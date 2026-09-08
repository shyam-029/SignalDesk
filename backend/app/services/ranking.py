# Top-1000 universe ranking — pure decision logic (M1-T2, Plan 7).
#
# The eligibility rules E1-E12 and the rank/cutoff math live here as PURE
# functions: no DB, no network, no clock (today/reference data are injected),
# no provider calls. The job pass (app/jobs.rank_universe) orchestrates:
# fetch master -> match catalog -> fetch market caps -> evaluate -> persist.
# This file decides; everything else serves inputs to it.
#
# Rule order (first match wins; a symbol gets exactly one disposition):
#   1. E1  series not EQ/BE/BZ            -> excluded, not_ordinary_equity
#   2. E2  curated ETF                    -> excluded, etf
#   3. E4  curated REIT/InvIT/...         -> excluded, not_ordinary_equity
#   4. E5  ISIN match, symbol not in the
#          reviewed alias map             -> excluded, rename_unmapped
#   5. E5  catalog row whose old symbol is alias-mapped to a master symbol
#          ranked under its newer row     -> excluded, renamed (rename shadow;
#                                             NOT deactivated — same live entity)
#   6. E10 absent from master             -> excluded, absent_from_master
#                                             (deactivates the catalog row)
#   7. E9  >30 stale trading days         -> excluded, inactive_proxy
#                                             (deactivates the catalog row)
#   8. E7  no market cap this cycle       -> excluded, no_mcap
#   9. otherwise                          -> ranked (ranked_in / ranked_out)
#
# Decision 6 (one-cycle trigger): absent_from_master and inactive_proxy set
# active=False; reappearance (back in the master / fresh bars) re-activates.
# Decision 2 (E7 strict): a missing fresh market cap excludes — stored
# financials.market_cap is never used as ranking input and never estimated.

from bisect import bisect_right
from dataclasses import dataclass, replace

from app.data.ranking_exclusions import curated_exclusion
from app.providers.nse_master import NseMasterRow, classify_series

# Outcome values (ranking_audit.outcome).
RANKED_IN = "ranked_in"
RANKED_OUT = "ranked_out"
EXCLUDED = "excluded"

# Flag values (ranking_audit.flag). Only one flag is stored per symbol;
# precedence: renamed > restricted_segment > recent_listing > not_yet_priced.
FLAG_RENAMED = "renamed"
FLAG_RESTRICTED = "restricted_segment"
FLAG_RECENT = "recent_listing"
FLAG_UNPRICED = "not_yet_priced"
_FLAG_PRECEDENCE = (FLAG_RENAMED, FLAG_RESTRICTED, FLAG_RECENT, FLAG_UNPRICED)


@dataclass(frozen=True)
class CatalogStock:
    """Facts about one catalog row (from stocks)."""

    id: int
    symbol: str  # with .NS suffix
    name: str
    isin: str | None
    active: bool


@dataclass(frozen=True)
class PriceFacts:
    """Per-stock price facts (from daily_prices)."""

    last_bar_date: object | None = None  # date | None
    first_bar_date: object | None = None  # date | None


@dataclass(frozen=True)
class Candidate:
    """One ranking candidate: a master row joined to its catalog/price state.

    master is None for a catalog stock absent from the current master (E10
    path). stock_id is set once the row exists in the catalog (matching or
    just-created); catalog_symbol is the matched catalog symbol ("X.NS").
    match_kind: "direct" (symbol == catalog symbol), "alias" (resolved via
    the reviewed SYMBOL_ALIASES map), "isin" (ISIN match under a different,
    un-reviewed symbol — the rename_unmapped case), "new" (just created).
    """

    symbol: str  # bare identity: master symbol, else bare catalog symbol
    master: NseMasterRow | None
    stock_id: int | None
    catalog_symbol: str | None
    match_kind: str
    name: str
    mcap: float | None
    mcap_error: str | None
    prices: PriceFacts

    @property
    def series(self) -> str | None:
        return self.master.series if self.master else None

    @property
    def isin(self) -> str | None:
        if self.master and self.master.isin:
            return self.master.isin
        return None


@dataclass(frozen=True)
class Decision:
    """One symbol's disposition for one cycle (persisted to ranking_audit)."""

    symbol: str  # bare (master symbol, else bare catalog symbol)
    catalog_symbol: str | None
    stock_id: int | None
    series: str | None
    isin: str | None
    name: str | None
    outcome: str
    reason: str | None
    flag: str | None
    detail: str | None
    mcap: float | None = None
    rank: int | None = None
    # True -> set stocks.active=False (with delisted_reason/at); False keeps
    # or restores active=True (reversibility, decision 6).
    deactivate: bool = False
    # True -> the symbol is a curated ETF (sets stocks.is_etf=True, M6 data).
    is_etf: bool = False


@dataclass(frozen=True)
class RankContext:
    """Injected environment for evaluate(): clock, thresholds, calendar."""

    today: object  # date
    reference_dates: tuple[object, ...] = ()  # sorted distinct market bar dates
    ranked_size: int = 1000
    recent_window_days: int = 365
    stale_trading_limit: int = 30
    # Reviewed alias map (catalog-bare -> master-bare): rename-shadow lookup.
    symbol_aliases: dict[str, str] | None = None


def stale_trading_days(
    last_bar_date: object | None, reference_dates: tuple[object, ...]
) -> int | None:
    """Trading-calendar staleness: count market bar dates AFTER the last bar.

    Reference dates are distinct daily_prices dates across the whole market
    (top-liquid names trade every NSE trading day), so this is a real
    trading-day count without maintaining a holiday calendar. Returns None
    when the stock has no bars (the not_yet_priced boundary — E9 does not
    apply, decision 5).
    """
    if last_bar_date is None:
        return None
    idx = bisect_right(reference_dates, last_bar_date)
    return len(reference_dates) - idx


def reverse_aliases(symbol_aliases: dict[str, str]) -> dict[str, str]:
    """Invert the reviewed alias map (catalog-bare -> master-bare).

    SYMBOL_ALIASES maps the CATALOG symbol to the CURRENT NSE trading symbol
    ({"TATAMOTORS": "TMPV"}); matching master rows to catalog rows needs the
    reverse direction.
    """
    return {v: k for k, v in symbol_aliases.items()}


def match_master_to_catalog(
    rows: list[NseMasterRow],
    catalog: list[CatalogStock],
    symbol_aliases: dict[str, str],
) -> dict[str, tuple[int, str, str]]:
    """Match master rows to catalog rows (rule E5). Returns per-symbol matches.

    Matching order: direct symbol, then the reviewed alias map (a rename),
    then ISIN. "isin" matches mean a rename NOT in the reviewed alias map —
    the audit records rename_unmapped for human review; no catalog symbol is
    auto-updated (decision 3) and no second catalog row is created (one
    entry per ISIN). Symbols with no match at all return no entry (the job
    then creates a new catalog row — the IPO/new-listing path).
    """
    by_symbol = {c.symbol.upper(): c for c in catalog}
    by_isin: dict[str, CatalogStock] = {}
    for c in catalog:
        if c.isin:
            # First ISIN wins; duplicates would already be a data defect.
            by_isin.setdefault(c.isin.upper(), c)

    alias_reverse = reverse_aliases(symbol_aliases)
    matches: dict[str, tuple[int, str, str]] = {}
    for row in rows:
        hit: CatalogStock | None = by_symbol.get(f"{row.symbol}.NS")
        kind = "direct"
        if hit is None:
            catalog_bare = alias_reverse.get(row.symbol)
            if catalog_bare is not None:
                hit = by_symbol.get(f"{catalog_bare}.NS")
                kind = "alias"
        if hit is None and row.isin:
            hit = by_isin.get(row.isin.upper())
            kind = "isin"
        if hit is not None:
            matches[row.symbol] = (hit.id, hit.symbol, kind)
    return matches


def curated_excluded(row: NseMasterRow) -> tuple[str, str] | None:
    """Curated E2/E4 disposition for a master row (never rankable)."""
    return curated_exclusion(row.symbol)


def rankable_series(row: NseMasterRow) -> bool:
    """True when the master row's series admits ranking (E1 EQ/BE/BZ)."""
    return classify_series(row.series) in ("eligible", "flagged")


def build_candidates(
    rows: list[NseMasterRow],
    catalog: list[CatalogStock],
    matches: dict[str, tuple[int, str, str]],
    price_facts: dict[int, PriceFacts],
    mcaps: dict[str, tuple[float | None, str | None]] | None = None,
    symbol_aliases: dict[str, str] | None = None,
) -> list[Candidate]:
    """Assemble the full candidate list for evaluate().

    Two sources:
      - every master row (matched or new; curated/series-excluded rows are
        included so their audit rows exist),
      - every catalog stock ABSENT from the master (E10 path).

    Rename shadows (E5): when an absent catalog stock's bare symbol is a KEY
    in the reviewed alias map AND the map's target symbol is present in the
    master (ranked under its own catalog row), the absent row is the entity's
    OLD identity — it gets match_kind "shadow" and audits as reason
    "renamed" without deactivation, instead of being misread as delisted.
    mcaps maps master-bare-symbol -> (mcap | None, fetch-error | None).
    """
    mcaps = mcaps or {}
    symbol_aliases = symbol_aliases or {}
    matched_master_symbols = set(matches.keys())
    candidates: list[Candidate] = []
    matched_stock_ids: set[int] = set()

    for row in rows:
        hit = matches.get(row.symbol)
        stock_id, catalog_symbol, kind = (
            (hit[0], hit[1], hit[2]) if hit else (None, None, "new")
        )
        if stock_id is not None:
            matched_stock_ids.add(stock_id)
        mcap, mcap_error = mcaps.get(row.symbol, (None, None))
        candidates.append(
            Candidate(
                symbol=row.symbol,
                master=row,
                stock_id=stock_id,
                catalog_symbol=catalog_symbol,
                match_kind=kind,
                name=row.name,
                mcap=mcap,
                mcap_error=mcap_error,
                prices=price_facts.get(stock_id, PriceFacts())
                if stock_id is not None
                else PriceFacts(),
            )
        )

    for c in catalog:
        if c.id in matched_stock_ids:
            continue
        bare = c.symbol.split(".")[0]
        alias_target = symbol_aliases.get(bare)
        is_shadow = (
            alias_target is not None and alias_target in matched_master_symbols
        )
        candidates.append(
            Candidate(
                symbol=bare,
                master=None,
                stock_id=c.id,
                catalog_symbol=c.symbol,
                match_kind="shadow" if is_shadow else "direct",
                name=c.name,
                mcap=None,
                mcap_error=None,
                prices=price_facts.get(c.id, PriceFacts()),
            )
        )
    return candidates


def needs_mcap(candidate: Candidate) -> bool:
    """True when a market-cap fetch is worth spending on this candidate.

    Only candidates that can still be RANKED need a fresh mcap (E6): master
    rows with rankable series, not curated-excluded, not the rename_unmapped
    dead end. Everything else is excluded before mcap matters. Staleness
    (E9) is NOT pre-filtered here: the fetch also records the mcap actually
    seen for stale symbols, which the audit trail shows.
    """
    if candidate.master is None:
        return False
    if not rankable_series(candidate.master):
        return False
    if curated_excluded(candidate.master) is not None:
        return False
    if candidate.match_kind == "isin":
        return False
    return True


def _flag_for(candidate: Candidate, ctx: RankContext) -> str | None:
    """Single flag for an eligible candidate (precedence documented above)."""
    flags: list[str] = []
    if candidate.match_kind == "alias":
        flags.append(FLAG_RENAMED)
    if candidate.master and classify_series(candidate.master.series) == "flagged":
        flags.append(FLAG_RESTRICTED)
    first = candidate.prices.first_bar_date
    if first is not None and (ctx.today - first).days <= ctx.recent_window_days:
        flags.append(FLAG_RECENT)
    if candidate.prices.last_bar_date is None:
        flags.append(FLAG_UNPRICED)
    return flags[0] if flags else None


def evaluate(candidates: list[Candidate], ctx: RankContext) -> list[Decision]:
    """Apply rules E1-E12 and the rank/cutoff math. Pure; one decision per candidate.

    Deterministic ordering: eligible candidates sort by market cap
    descending, then symbol ascending (tiebreak); ranks are 1..N over ALL
    eligible candidates, so ranked_out rows carry their exact rank ("eligible,
    ranked 1,247" is a real stored answer).
    """
    decisions: list[Decision] = []
    eligible: list[tuple[float, str, Candidate]] = []

    for c in candidates:
        base = dict(
            symbol=c.symbol,
            catalog_symbol=c.catalog_symbol,
            stock_id=c.stock_id,
            series=c.series,
            isin=c.isin,
            name=c.name,
            mcap=c.mcap,
        )

        # 1. E1: instrument class from the master SERIES.
        if c.master is not None and not rankable_series(c.master):
            decisions.append(
                Decision(
                    **base,
                    outcome=EXCLUDED,
                    reason="not_ordinary_equity",
                    flag=None,
                    detail=f"series {c.master.series}",
                )
            )
            continue

        # 2/3. E2 + E4: curated exclusions (ETFs, REITs, InvITs, ...).
        if c.master is not None:
            curated = curated_excluded(c.master)
            if curated is not None:
                reason, detail = curated
                decisions.append(
                    Decision(
                        **base,
                        outcome=EXCLUDED,
                        reason=reason,
                        flag=None,
                        detail=detail,
                        is_etf=reason == "etf",
                    )
                )
                continue

        # 4. E5: ISIN match under a symbol not in the reviewed alias map.
        if c.match_kind == "isin":
            decisions.append(
                Decision(
                    **base,
                    outcome=EXCLUDED,
                    reason="rename_unmapped",
                    flag=None,
                    detail=(
                        f"ISIN matches {c.catalog_symbol}; extend SYMBOL_ALIASES "
                        "after review"
                    ),
                )
            )
            continue

        # 5/6. E5 rename shadow, then E10 absent-from-master. A shadow row is
        # the entity's OLD identity (alias-mapped, new symbol ranked under its
        # own row): it stays active and audits as renamed, never delisted.
        if c.master is None:
            if c.match_kind == "shadow":
                target = (ctx.symbol_aliases or {}).get(c.symbol, "?")
                decisions.append(
                    Decision(
                        **base,
                        outcome=EXCLUDED,
                        reason="renamed",
                        flag=None,
                        detail=(
                            f"renamed to {target} (ranked under its current symbol)"
                        ),
                    )
                )
            else:
                decisions.append(
                    Decision(
                        **base,
                        outcome=EXCLUDED,
                        reason="absent_from_master",
                        flag=None,
                        detail="not in the current NSE equity master",
                        deactivate=True,
                    )
                )
            continue

        # 6. E9: trading-day staleness against the market reference calendar.
        stale = stale_trading_days(c.prices.last_bar_date, ctx.reference_dates)
        if stale is not None and stale > ctx.stale_trading_limit:
            decisions.append(
                Decision(
                    **base,
                    outcome=EXCLUDED,
                    reason="inactive_proxy",
                    flag=None,
                    detail=(
                        f"last bar {c.prices.last_bar_date} "
                        f"({stale} trading days stale)"
                    ),
                    deactivate=True,
                )
            )
            continue

        # 7. E7: no fresh market cap this cycle (strict; fetch failures land
        # here too — the detail records the error, the pass reports partial).
        if c.mcap is None:
            detail = None
            if c.mcap_error:
                detail = f"provider fetch failed: {c.mcap_error}"
            elif c.master is not None:
                detail = "provider supplied no market cap"
            decisions.append(
                Decision(
                    **base,
                    outcome=EXCLUDED,
                    reason="no_mcap",
                    flag=None,
                    detail=detail,
                )
            )
            continue

        # 8. Eligible: rank it.
        eligible.append((float(c.mcap), c.symbol, c))

    eligible.sort(key=lambda t: (-t[0], t[1]))
    for position, (mcap, _symbol, c) in enumerate(eligible, start=1):
        outcome = RANKED_IN if position <= ctx.ranked_size else RANKED_OUT
        base = dict(
            symbol=c.symbol,
            catalog_symbol=c.catalog_symbol,
            stock_id=c.stock_id,
            series=c.series,
            isin=c.isin,
            name=c.name,
        )
        decisions.append(
            Decision(
                **base,
                outcome=outcome,
                reason=None if outcome == RANKED_IN else "beyond_cutoff",
                flag=_flag_for(c, ctx),
                detail=None,
                mcap=mcap,
                rank=position,
            )
        )

    return decisions


def cycle_reference_asof(reference_dates: tuple[object, ...], today: object) -> object:
    """The market-wide newest bar date (E9 reference); today as fallback."""
    return reference_dates[-1] if reference_dates else today


def decision_updates(decision: Decision) -> dict:
    """Map a Decision onto its stocks-row update (never deletes anything).

    active reflects THIS cycle's evaluation (reversibility, decision 6);
    mcap_rank/mcap_asof apply only to ranked_in symbols; is_etf is only ever
    set True (M6 owns any future correction); restrict_flag reflects the
    current cycle's series classification. delisted_at is set by the
    repository at write time (it owns the clock for persisted timestamps).
    """
    if decision.stock_id is None:
        return {}
    values: dict = {"active": not decision.deactivate}
    if decision.deactivate:
        values["delisted_reason"] = decision.reason
    else:
        values["delisted_reason"] = None
        values["delisted_at"] = None
    if decision.outcome == RANKED_IN:
        values["mcap_rank"] = decision.rank
        values["restrict_flag"] = (
            "restricted_segment" if decision.flag == FLAG_RESTRICTED else None
        )
    else:
        values["mcap_rank"] = None
        values["mcap_asof"] = None
        values["restrict_flag"] = None
    if decision.is_etf:
        values["is_etf"] = True
    return values


def with_mcap(candidate: Candidate, mcap: float | None, error: str | None) -> Candidate:
    """Return a copy of the candidate with the fetch result attached."""
    return replace(candidate, mcap=mcap, mcap_error=error)
