# Altman Z-Score tests (M1-T3/T4/T6 Part D). Pure service tests + API tests.
# Zero network: the service is pure math over explicit inputs; the API reads
# the test DB through the standard client fixture.

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Financials, Stock
from app.services import altman as svc


# --- Known input/output cases (hand-computed Z'') ---------------------------


def test_known_safe_case():
    """Healthy manufacturer-style balance sheet -> safe zone."""
    # X1 = 200/1000 = 0.2; X2 = 300/1000 = 0.3; X3 = 150/1000 = 0.15;
    # X4 = 600/400 = 1.5.
    # Z = 6.56*0.2 + 3.26*0.3 + 6.72*0.15 + 1.05*1.5
    #   = 1.312 + 0.978 + 1.008 + 1.575 = 4.873 -> 4.87 safe.
    result = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=200.0,
            total_assets=1000.0,
            retained_earnings=300.0,
            ebit=150.0,
            book_equity=600.0,
            total_liabilities=400.0,
        ),
        sector="Capital Goods",
    )
    assert result.status == "available"
    assert result.score == pytest.approx(4.87, abs=0.01)
    assert result.zone == "safe"
    assert result.reason is None
    assert result.missing_inputs == []
    assert set(result.inputs_used) >= {
        "working_capital", "total_assets", "retained_earnings",
        "ebit", "book_equity", "total_liabilities", "x1", "x2", "x3", "x4",
    }
    assert result.inputs_used["x1"] == pytest.approx(0.2)
    assert result.inputs_used["x4"] == pytest.approx(1.5)
    assert "4.87" in (result.detail or "")
    assert result.formulation.startswith("Altman Z''")


def test_known_distress_case():
    """Distressed balance sheet -> distress zone."""
    # X1 = -100/1000 = -0.1; X2 = -200/1000 = -0.2; X3 = -50/1000 = -0.05;
    # X4 = 100/900 = 0.1111.
    # Z = -0.656 - 0.652 - 0.336 + 0.1167 = -1.527 -> -1.53 distress.
    result = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=-100.0,
            total_assets=1000.0,
            retained_earnings=-200.0,
            ebit=-50.0,
            book_equity=100.0,
            total_liabilities=900.0,
        ),
        sector="Textiles",
    )
    assert result.status == "available"
    assert result.score == pytest.approx(-1.53, abs=0.01)
    assert result.zone == "distress"


def test_known_grey_case():
    """Borderline balance sheet -> grey zone."""
    # X1 = 100/1000 = 0.1; X2 = 50/1000 = 0.05; X3 = 80/1000 = 0.08;
    # X4 = 400/600 = 0.6667.
    # Z = 0.656 + 0.163 + 0.5376 + 0.7 = 2.0566 -> 2.06 grey.
    result = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=100.0,
            total_assets=1000.0,
            retained_earnings=50.0,
            ebit=80.0,
            book_equity=400.0,
            total_liabilities=600.0,
        ),
        sector="Chemicals",
    )
    assert result.status == "available"
    assert result.score == pytest.approx(2.06, abs=0.01)
    assert result.zone == "grey"


# --- Missing / invalid inputs ------------------------------------------------


def test_all_missing_is_unavailable_missing_balance_sheet():
    result = svc.compute_z_score(svc.AltmanInputs(), sector="IT")
    assert result.status == "unavailable"
    assert result.score is None
    assert result.zone is None
    assert result.reason == "missing_balance_sheet"
    assert "working_capital" in result.missing_inputs
    assert "total_assets" in result.missing_inputs


def test_partially_missing_never_treated_as_zero():
    """One missing input must not silently become zero."""
    full = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=200.0, total_assets=1000.0, retained_earnings=300.0,
            ebit=150.0, book_equity=600.0, total_liabilities=400.0,
        ),
        sector="IT",
    )
    assert full.status == "available"
    partial = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=200.0, total_assets=1000.0, retained_earnings=None,
            ebit=150.0, book_equity=600.0, total_liabilities=400.0,
        ),
        sector="IT",
    )
    assert partial.status == "unavailable"
    assert partial.score is None
    assert partial.missing_inputs == ["retained_earnings"]
    assert partial.reason == "invalid_input"


def test_zero_total_assets_is_invalid():
    result = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=10.0, total_assets=0.0, retained_earnings=5.0,
            ebit=5.0, book_equity=50.0, total_liabilities=50.0,
        ),
        sector="IT",
    )
    assert result.status == "unavailable"
    assert result.reason == "invalid_input"
    assert result.score is None


def test_nan_and_inf_inputs_are_invalid():
    result = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=float("nan"), total_assets=1000.0,
            retained_earnings=300.0, ebit=150.0, book_equity=600.0,
            total_liabilities=400.0,
        ),
        sector="IT",
    )
    assert result.status == "unavailable"
    assert "working_capital" in result.missing_inputs
    result = svc.compute_z_score(
        svc.AltmanInputs(
            working_capital=200.0, total_assets=float("inf"),
            retained_earnings=300.0, ebit=150.0, book_equity=600.0,
            total_liabilities=400.0,
        ),
        sector="IT",
    )
    assert result.status == "unavailable"
    assert "total_assets" in result.missing_inputs


# --- Non-applicable company type ---------------------------------------------


def test_financial_sector_is_non_applicable():
    for sector in ("Financial Services", "Banks", "Housing Finance Ltd"):
        result = svc.compute_z_score(
            svc.AltmanInputs(
                working_capital=200.0, total_assets=1000.0,
                retained_earnings=300.0, ebit=150.0, book_equity=600.0,
                total_liabilities=400.0,
            ),
            sector=sector,
        )
        assert result.status == "unavailable"
        assert result.reason == "non_applicable_financial"
        assert result.score is None


def test_non_financial_sector_is_applicable():
    assert svc.is_financial_sector("Information Technology") is False
    assert svc.is_financial_sector(None) is False
    assert svc.is_financial_sector("Financial Services") is True
    assert svc.is_financial_sector("Auto", industry="Banks") is True


# --- Zone boundaries ----------------------------------------------------------


def test_zone_boundaries():
    assert svc.zone_for(2.61) == "safe"
    assert svc.zone_for(2.6) == "grey"
    assert svc.zone_for(1.1) == "grey"
    assert svc.zone_for(1.09) == "distress"


# --- Determinism --------------------------------------------------------------


def test_deterministic_recalculation():
    kwargs = dict(
        working_capital=200.0, total_assets=1000.0, retained_earnings=300.0,
        ebit=150.0, book_equity=600.0, total_liabilities=400.0,
    )
    first = svc.compute_z_score(svc.AltmanInputs(**kwargs), sector="IT")
    second = svc.compute_z_score(svc.AltmanInputs(**kwargs), sector="IT")
    assert first == second


# --- Stored-row reader (real scores from balance_sheet_periods) --------------


def test_inputs_from_balance_sheet_row_maps_decimals():
    """Decimal columns map to floats; None stays None (never zero)."""
    from datetime import date
    from decimal import Decimal

    from app.models import BalanceSheetPeriod

    row = BalanceSheetPeriod(
        stock_id=1,
        period_end=date(2026, 3, 31),
        period_type="annual",
        working_capital=Decimal("200"),
        total_assets=Decimal("1000"),
        retained_earnings=Decimal("300"),
        ebit=Decimal("150"),
        book_equity=Decimal("600"),
        total_liabilities=Decimal("400"),
        source="yfinance",
    )
    inputs = svc.inputs_from_balance_sheet_row(row)
    assert inputs.working_capital == 200.0
    assert inputs.total_assets == 1000.0
    assert inputs.ebit == 150.0
    row2 = BalanceSheetPeriod(
        stock_id=1, period_end=date(2025, 3, 31), period_type="annual",
        source="yfinance",
    )
    empty = svc.inputs_from_balance_sheet_row(row2)
    assert empty.working_capital is None
    assert empty.total_assets is None


async def test_compute_stock_altman_available_with_balance_sheet(
    session_factory,
):
    """A stored balance sheet yields the real hand-computed Z'' score."""
    from datetime import date
    from decimal import Decimal

    from app.models import BalanceSheetPeriod
    from app.services.altman import compute_stock_altman

    async with session_factory() as session:
        stock = Stock(symbol="ZS.NS", name="Z", sector="IT", industry="IT Services")
        session.add(stock)
        await session.flush()
        # The 4.87 safe case scaled x10: same ratios, same score.
        session.add(
            BalanceSheetPeriod(
                stock_id=stock.id, period_end=date(2026, 3, 31),
                period_type="annual",
                working_capital=Decimal("2000"), total_assets=Decimal("10000"),
                retained_earnings=Decimal("3000"), ebit=Decimal("1500"),
                book_equity=Decimal("6000"), total_liabilities=Decimal("4000"),
                source="yfinance",
            )
        )
        await session.commit()

    async with session_factory() as session:
        stock = await session.scalar(select(Stock).where(Stock.symbol == "ZS.NS"))
        result = await compute_stock_altman(session, stock)
    assert result.status == "available"
    assert result.score == pytest.approx(4.87, abs=0.01)
    assert result.zone == "safe"
    assert result.inputs_used["x1"] == pytest.approx(0.2)


async def test_compute_stock_altman_unavailable_without_balance_sheet(
    session_factory,
):
    """No stored balance sheet: honest unavailable, full missing-input list."""
    from app.services.altman import compute_stock_altman

    async with session_factory() as session:
        stock = Stock(symbol="NB.NS", name="NB", sector="IT", industry="IT")
        session.add(stock)
        await session.commit()

    async with session_factory() as session:
        stock = await session.scalar(select(Stock).where(Stock.symbol == "NB.NS"))
        result = await compute_stock_altman(session, stock)
    assert result.status == "unavailable"
    assert result.reason == "missing_balance_sheet"
    assert result.score is None
    assert "total_assets" in result.missing_inputs


# --- API ----------------------------------------------------------------------


async def _seed_altman_stock(session_factory, sector="IT"):
    async with session_factory() as session:
        stock = Stock(symbol="ALT.NS", name="Alt", sector=sector, industry="IT Services")
        session.add(stock)
        await session.flush()
        session.add(
            Financials(
                stock_id=stock.id, trailing_pe=Decimal("20.00"),
                return_on_equity=Decimal("0.1800"),
                debt_to_equity=Decimal("50.00"),
            )
        )
        await session.commit()


async def test_altman_endpoint_unavailable_with_reason(client, session_factory):
    """Today's stored data cannot form Z'': the API says so, with metadata."""
    await _seed_altman_stock(session_factory)
    r = await client.get("/api/v1/stocks/ALT/altman")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "ALT.NS"
    assert body["status"] == "unavailable"
    assert body["score"] is None
    assert body["zone"] is None
    assert body["reason"] == "missing_balance_sheet"
    assert "total_assets" in body["missing_inputs"]
    assert "Altman Z''" in body["formulation"]
    assert body["detail"]


async def test_altman_endpoint_financial_sector(client, session_factory):
    await _seed_altman_stock(session_factory, sector="Financial Services")
    r = await client.get("/api/v1/stocks/ALT/altman")
    assert r.status_code == 200
    assert r.json()["reason"] == "non_applicable_financial"


async def test_altman_endpoint_unknown_symbol_404(client, session_factory):
    r = await client.get("/api/v1/stocks/ZZZ/altman")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_altman_does_not_change_solvency(client, session_factory):
    """The existing Solvency Score is intact: same inputs, same outputs."""
    await _seed_altman_stock(session_factory)
    r = await client.get("/api/v1/stocks/ALT/scores")
    assert r.status_code == 200
    body = r.json()
    # ROE 18% -> 90 (weight .4 -> only profitability component => 90),
    # D/E 50 -> 100 (only solvency component => 100).
    assert body["profitability"] == 90
    assert body["solvency"] == 100
