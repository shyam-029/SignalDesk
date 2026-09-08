# Curated ranking exclusions (M1-T2, Plan 7 rules E2/E3/E4).
#
# The NSE securities master (EQUITY_L.csv) identifies instruments only by
# SERIES, and ETFs / REITs / InvITs appear inside the ordinary EQ/BE series —
# series alone cannot exclude them (verified against Plan 7 rule wording and
# the master's columns). Until the ETF/MF domains provide structured metadata
# (Plan 9, M6), these PROVISIONAL data lists carry the exclusion decisions.
# This extends D16/D64: exclusions are data, not code paths.
#
# Keys are bare NSE master symbols (no ".NS" suffix).

# E2: ETFs — excluded from the equity ranking entirely; ranked into the ETF
# domain (M6) instead. Sets stocks.is_etf when the symbol matches a catalog row.
ETF_SYMBOLS: frozenset[str] = frozenset(
    {
        "NIFTYBEES",
        "JUNIORBEES",
        "BANKBEES",
        "GOLDBEES",
        "SILVERBEES",
        "LIQUIDBEES",
        "HDFCNIFTY",
        "ICICINIFTY",
        "ITBEES",
        "PSUBNKBEES",
        "MOM100",
        "MON100",
        "MAFANG",
        "MAKEINDIA",
        "MOM50",
        "HDFCMID150",
    }
)

# E4: instruments that are NOT ordinary equity despite EQ-series listing:
# REITs and InvITs. Value names the class for the audit detail column.
NOT_ORDINARY_EQUITY: dict[str, str] = {
    "EMBASSY": "REIT",
    "MINDSPACE": "REIT",
    "BIRET": "REIT",
    "NEXUSSELECT": "REIT",
    "IRBINVIT": "InvIT",
    "PGINVIT": "InvIT",
    "INDIGRID": "InvIT",
}


def curated_exclusion(bare_symbol: str) -> tuple[str, str] | None:
    """Return (reason, detail) for a curated exclusion, or None.

    reason is "etf" (E2) or "not_ordinary_equity" (E4). E3 (mutual funds)
    needs no curated list: MF units never appear in the ordinary-equity
    series, so the series filter (E1) already covers them.
    """
    if bare_symbol in ETF_SYMBOLS:
        return ("etf", "ETF")
    klass = NOT_ORDINARY_EQUITY.get(bare_symbol)
    if klass is not None:
        return ("not_ordinary_equity", klass)
    return None
