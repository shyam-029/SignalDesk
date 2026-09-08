# Altman Z-Score — financial-distress diagnostic (M1-T3/T4/T6 task, Part D).
#
# SEPARATE from the SignalDesk Solvency Score (services/scores.py: D/E 50 /
# interest coverage 30 / current ratio 20). Altman is reported alongside, never
# blended into solvency, profitability or the Alpha composite.
#
# Selected formulation: Altman's Z'' (1995, emerging-market / non-manufacturing
# variant), Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4, where
#   X1 = Working Capital / Total Assets      (liquidity)
#   X2 = Retained Earnings / Total Assets    (cumulative profitability)
#   X3 = EBIT / Total Assets                 (operating productivity)
#   X4 = Book Value of Equity / Total Liabilities (leverage, market-value-free)
#
# Why Z'' and not the 1968 Z or 1993 Z' (textbook defaults):
#   - Z (1968) uses X4 = Market Value of Equity / Total Liabilities and
#     X5 = Sales / Total Assets. Market-value leverage is pro-cyclical for a
#     daily research screen, and X5 (asset turnover) penalizes asset-light
#     services/IT companies that dominate the Indian top-1000 — the exact
#     misapplication the task brief forbids (manufacturing formula on every
#     security). Z'' drops X5 entirely, which is why Altman designed it for
#     non-manufacturers.
#   - Z' (1993) keeps X5 with a small weight; same objection, weaker.
#   - Z'' replaces market equity with BOOK equity, so the score stays a pure
#     balance-sheet diagnostic instead of echoing today's price.
#   - Zones for Z'': Safe > 2.6, Grey 1.1-2.6, Distress < 1.1 (Altman 1995).
#
# What SignalDesk actually stores today (financials point-in-time snapshot +
# income-statement financial_periods): NONE of the four Z'' inputs.
# Total assets, current assets/liabilities, retained earnings and EBIT live on
# the balance sheet, which Semester 1 never ingested (Plan 5.4 is M2 scope).
# Consequence, enforced by this module: with no balance-sheet table, a valid
# Z'' is NOT calculable for any security today. compute_z_score() therefore
# returns status="unavailable" with reason="missing_balance_sheet" for every
# input — it never manufactures a score from income ratios, never treats
# missing values as zero, and never substitutes market cap for book equity.
# When M2 lands balance_sheet_periods, the ONLY change needed is a repository
# reader feeding the four inputs into from_balance_sheet(); the math, zones,
# metadata and tests below stay valid.
#
# Determinism: pure functions of explicit inputs; no clock, no network, no DB.

from dataclasses import dataclass, field


# Z'' coefficients (Altman 1995) and zones.
Z2_COEFFICIENTS = {"x1": 6.56, "x2": 3.26, "x3": 6.72, "x4": 1.05}
ZONE_SAFE = 2.6
ZONE_DISTRESS = 1.1
FORMULATION = "Altman Z'' (1995, non-manufacturing / emerging-market)"

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"

REASON_MISSING_BALANCE_SHEET = "missing_balance_sheet"
REASON_NON_APPLICABLE_FINANCIAL = "non_applicable_financial"
REASON_INVALID_INPUT = "invalid_input"

# Banks, NBFCs and insurers report non-standard balance sheets (no working
# capital, leverage is the business model): Z'' is not applicable even when
# M2 data exists. Sectors arrive from the stocks row; matching is
# substring-based and conservative (unknown sector => applicable, the score
# computes when inputs exist).
FINANCIAL_SECTOR_MARKERS = (
    "financial",
    "bank",
    "insurance",
    "nbfc",
    "housing finance",
)


@dataclass(frozen=True)
class AltmanInputs:
    """The four Z'' balance-sheet inputs (all in the same currency).

    None means the provider did not supply the field. total_liabilities of
    zero/negative is invalid (division), never coerced.
    """

    working_capital: float | None = None
    total_assets: float | None = None
    retained_earnings: float | None = None
    ebit: float | None = None
    book_equity: float | None = None
    total_liabilities: float | None = None


@dataclass(frozen=True)
class AltmanResult:
    """Deterministic Z'' outcome with full calculation metadata.

    status="available": score + zone + inputs_used are real.
    status="unavailable": score/zone are None; reason + missing_inputs say why.
    """

    status: str
    score: float | None
    zone: str | None  # "safe" | "grey" | "distress" | None
    formulation: str = FORMULATION
    inputs_used: dict[str, float] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)
    reason: str | None = None
    detail: str | None = None


def is_financial_sector(sector: str | None, industry: str | None = None) -> bool:
    """True when the company is a bank/financial (Z'' not applicable)."""
    haystack = f"{sector or ''} / {industry or ''}".lower()
    return any(marker in haystack for marker in FINANCIAL_SECTOR_MARKERS)


def _is_finite(value: float | None) -> bool:
    return (
        value is not None
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def zone_for(score: float) -> str:
    """Z'' zone: safe (>2.6), grey (1.1-2.6), distress (<1.1)."""
    if score > ZONE_SAFE:
        return "safe"
    if score < ZONE_DISTRESS:
        return "distress"
    return "grey"


def compute_z_score(
    inputs: AltmanInputs,
    sector: str | None = None,
    industry: str | None = None,
) -> AltmanResult:
    """Compute the Z'' distress score from explicit balance-sheet inputs.

    Rules (never violated):
      - financial-sector companies => unavailable/non_applicable_financial.
      - any missing/invalid input => unavailable (reason recorded, missing
        inputs listed). Missing is NEVER treated as zero.
      - total_assets <= 0 or total_liabilities <= 0 => invalid_input.
    """
    if is_financial_sector(sector, industry):
        return AltmanResult(
            status=STATUS_UNAVAILABLE,
            score=None,
            zone=None,
            missing_inputs=[],
            reason=REASON_NON_APPLICABLE_FINANCIAL,
            detail=(
                "Z'' is not applicable to banks/financials: non-standard "
                "balance sheets with no working capital, and leverage is the "
                "business model rather than a distress signal."
            ),
        )

    required = {
        "working_capital": inputs.working_capital,
        "total_assets": inputs.total_assets,
        "retained_earnings": inputs.retained_earnings,
        "ebit": inputs.ebit,
        "book_equity": inputs.book_equity,
        "total_liabilities": inputs.total_liabilities,
    }
    missing = [name for name, value in required.items() if not _is_finite(value)]
    if missing:
        return AltmanResult(
            status=STATUS_UNAVAILABLE,
            score=None,
            zone=None,
            missing_inputs=sorted(missing),
            reason=(
                REASON_MISSING_BALANCE_SHEET
                if set(missing) & {"total_assets", "total_liabilities"}
                or len(missing) >= 3
                else REASON_INVALID_INPUT
            ),
            detail=(
                "Balance-sheet inputs are not stored by SignalDesk yet "
                "(Semester 1 keeps income statements only); the score is not "
                "estimated from income ratios."
                if set(missing) & {"total_assets", "total_liabilities"}
                or len(missing) >= 3
                else "One or more Z'' inputs are missing or invalid; missing "
                "values are never treated as zero."
            ),
        )

    wc = inputs.working_capital or 0.0
    ta = inputs.total_assets or 0.0
    re = inputs.retained_earnings or 0.0
    ebit = inputs.ebit or 0.0
    eq = inputs.book_equity or 0.0
    tl = inputs.total_liabilities or 0.0
    if ta <= 0 or tl <= 0:
        bad = [
            name
            for name, value in (("total_assets", ta), ("total_liabilities", tl))
            if value <= 0
        ]
        return AltmanResult(
            status=STATUS_UNAVAILABLE,
            score=None,
            zone=None,
            missing_inputs=[],
            reason=REASON_INVALID_INPUT,
            detail=f"Non-positive denominators cannot form ratios: {', '.join(bad)}.",
        )

    x1 = wc / ta
    x2 = re / ta
    x3 = ebit / ta
    x4 = eq / tl
    score = round(
        Z2_COEFFICIENTS["x1"] * x1
        + Z2_COEFFICIENTS["x2"] * x2
        + Z2_COEFFICIENTS["x3"] * x3
        + Z2_COEFFICIENTS["x4"] * x4,
        2,
    )
    return AltmanResult(
        status=STATUS_AVAILABLE,
        score=score,
        zone=zone_for(score),
        inputs_used={
            "working_capital": wc,
            "total_assets": ta,
            "retained_earnings": re,
            "ebit": ebit,
            "book_equity": eq,
            "total_liabilities": tl,
            "x1": round(x1, 4),
            "x2": round(x2, 4),
            "x3": round(x3, 4),
            "x4": round(x4, 4),
        },
        missing_inputs=[],
        reason=None,
        detail=(
            f"Z'' = 6.56*{x1:.4f} + 3.26*{x2:.4f} + 6.72*{x3:.4f} "
            f"+ 1.05*{x4:.4f} = {score:.2f} ({zone_for(score)})."
        ),
    )


def inputs_from_balance_sheet_row(row) -> AltmanInputs:
    """Build AltmanInputs from a stored BalanceSheetPeriod row (Plan 5.4).

    Decimal columns become floats; None stays None (never zero-filled).
    ebit rides the same row (carried from the income statement at ingestion).
    """
    def _f(value) -> float | None:
        return float(value) if value is not None else None

    return AltmanInputs(
        working_capital=_f(row.working_capital),
        total_assets=_f(row.total_assets),
        retained_earnings=_f(row.retained_earnings),
        ebit=_f(row.ebit),
        book_equity=_f(row.book_equity),
        total_liabilities=_f(row.total_liabilities),
    )


def _unavailable_no_balance_sheet() -> AltmanResult:
    return AltmanResult(
        status=STATUS_UNAVAILABLE,
        score=None,
        zone=None,
        missing_inputs=[
            "book_equity",
            "ebit",
            "retained_earnings",
            "total_assets",
            "total_liabilities",
            "working_capital",
        ],
        reason=REASON_MISSING_BALANCE_SHEET,
        detail=(
            "No balance-sheet period is stored for this stock yet; the score "
            "is not estimated from income ratios."
        ),
    )


async def compute_stock_altman(session, stock) -> AltmanResult:
    """Compute one stock's Z'' from stored data (the API's single reader).

    Reads the latest annual balance_sheet_periods row via the repository and
    hands explicit inputs to compute_z_score. Pure read: no provider calls,
    no writes, deterministic per stored rows. Financial-sector companies are
    gated before the lookup; a stock with no stored balance sheet gets the
    honest unavailable result with the full missing-input list.
    """
    if is_financial_sector(stock.sector, stock.industry):
        return compute_z_score(
            AltmanInputs(), sector=stock.sector, industry=stock.industry
        )

    from app.repositories import balance_sheets as bs_repo

    row = await bs_repo.get_latest(session, stock.id)
    if row is None:
        return _unavailable_no_balance_sheet()
    return compute_z_score(
        inputs_from_balance_sheet_row(row),
        sector=stock.sector,
        industry=stock.industry,
    )
