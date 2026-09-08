# Curated mutual-fund universe + official data-source endpoints (Plan 8/13).
#
# The catalog is CURATED (about two dozen major schemes across categories):
# Plan 29 leaves the full-universe cut rule (top by AUM per category, ~800)
# to M4, so this slice ships a small, verifiable list instead of pretending
# at completeness. Each entry matches an AMFI row by scheme-name substring
# PLUS plan/option, which is resilient to punctuation differences in the
# official file and cannot hit the wrong share class.
#
# Sources (Plan 13):
#   PRIMARY   AMFI NAVAll file (official, public, no key) — daily NAV.
#   FALLBACK  api.mfapi.in scheme history (third-party mirror; documented
#             fallback only) — one-time history backfill, source='mfapi'.

from dataclasses import dataclass

AMFI_NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
# The older www.amfiindia.com URL issues an HTTP redirect to portal.amfiindia;
# portal is used directly (verified 2026-09-08, curl -L).
MFAPI_SCHEME_URL = "https://api.mfapi.in/mf/{code}"

# One-time history backfill depth (trading days): ~3y, matching the Plan 14
# NAV-history default. Keeps the backfill to ~750 rows per fund.
MFAPI_BACKFILL_DAYS = 750


@dataclass(frozen=True)
class CuratedFund:
    """One curated fund: how to find it in the AMFI file and how to label it."""

    match: str  # case-insensitive substring of the AMFI scheme name
    name: str  # display name for the catalog
    category: str
    plan: str = "Direct Plan"
    option: str = "Growth"


CURATED_FUNDS: tuple[CuratedFund, ...] = (
    CuratedFund("Parag Parikh Flexi Cap", "Parag Parikh Flexi Cap Fund", "Flexi Cap"),
    CuratedFund("HDFC Flexi Cap", "HDFC Flexi Cap Fund", "Flexi Cap"),
    CuratedFund("Kotak Flexi Cap", "Kotak Flexi Cap Fund", "Flexi Cap"),
    CuratedFund("ICICI Prudential Large Cap", "ICICI Prudential Large Cap Fund", "Large Cap"),
    CuratedFund("Mirae Asset Large Cap", "Mirae Asset Large Cap Fund", "Large Cap"),
    CuratedFund("Axis Large Cap", "Axis Large Cap Fund", "Large Cap"),
    CuratedFund("Canara Robeco Large and Mid Cap", "Canara Robeco Large and Mid Cap Fund", "Large & Mid Cap"),
    CuratedFund("HDFC Mid Cap", "HDFC Mid Cap Fund", "Mid Cap"),
    CuratedFund("Nippon India Growth Mid Cap", "Nippon India Growth Mid Cap Fund", "Mid Cap"),
    CuratedFund("Nippon India Small Cap", "Nippon India Small Cap Fund", "Small Cap"),
    CuratedFund("Quant Small Cap", "Quant Small Cap Fund", "Small Cap"),
    CuratedFund("Axis Small Cap", "Axis Small Cap Fund", "Small Cap"),
    CuratedFund("Quant ELSS Tax Saver", "Quant ELSS Tax Saver Fund", "ELSS"),
    CuratedFund("Mirae Asset ELSS Tax Saver", "Mirae Asset ELSS Tax Saver Fund", "ELSS"),
    CuratedFund("UTI Nifty 50 Index", "UTI Nifty 50 Index Fund", "Index"),
    CuratedFund(
        "ICICI Prudential Nifty 50 Index", "ICICI Prudential Nifty 50 Index Fund",
        "Index", option="Cumulative",
    ),
    CuratedFund("Motilal Oswal Nasdaq 100", "Motilal Oswal Nasdaq 100 FOF", "International"),
    CuratedFund("ICICI Prudential Balanced Advantage", "ICICI Prudential Balanced Advantage Fund", "Hybrid"),
    CuratedFund("HDFC Balanced Advantage", "HDFC Balanced Advantage Fund", "Hybrid"),
    CuratedFund("ICICI Prudential Liquid", "ICICI Prudential Liquid Fund", "Liquid"),
    CuratedFund("HDFC Liquid", "HDFC Liquid Fund", "Liquid"),
)
