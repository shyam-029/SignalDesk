# Stock-page depth tests (checklist section 6, step 1): valuation history,
# risk and the return-on-equity breakdown. Pure service tests with
# hand-computed cases, then API tests over the test DB. Zero network.

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    BalanceSheetPeriod,
    Benchmark,
    BenchmarkPrice,
    DailyPrice,
    FinancialPeriod,
    Financials,
    Stock,
)
from app.services import depth as svc


def _bars(closes: list[float], start: date = date(2025, 1, 1)) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), c) for i, c in enumerate(closes)]


# --- Valuation history -------------------------------------------------------


def test_published_fact_respects_publication_lag():
    """A year's profit is not used until 60 days after its period end."""
    facts = [
        svc.AnnualFacts(period_end=date(2024, 3, 31), net_income=100.0),
        svc.AnnualFacts(period_end=date(2025, 3, 31), net_income=200.0),
    ]
    # 29 May 2025 is day 59 after 31 March: FY2025 is not public yet.
    assert svc._published_fact(facts, date(2025, 5, 29), "net_income") == 100.0
    # 30 May 2025 is day 60: FY2025 is public.
    assert svc._published_fact(facts, date(2025, 5, 30), "net_income") == 200.0
    # Before the first year was published there is nothing to use.
    assert svc._published_fact(facts, date(2024, 4, 30), "net_income") is None


def test_published_fact_does_not_fall_back_to_older_year():
    """A newest published year with a missing figure stays missing."""
    facts = [
        svc.AnnualFacts(period_end=date(2023, 3, 31), net_income=100.0),
        svc.AnnualFacts(period_end=date(2024, 3, 31), net_income=None),
    ]
    assert svc._published_fact(facts, date(2024, 12, 1), "net_income") is None


def test_pe_band_known_values():
    """P/E = close x shares / profit; band stats over every valid day."""
    # 200 days: 100 days at close 100, then 100 days at close 200.
    bars = _bars([100.0] * 100 + [200.0] * 100)
    facts = [svc.AnnualFacts(period_end=date(2024, 3, 31), net_income=1000.0)]
    # shares 100 -> market value 10,000 then 20,000 -> P/E 10 then 20.
    bands = svc.valuation_history(bars, facts, shares=100.0, is_financial=False)
    pe = next(b for b in bands if b.metric == "pe")
    assert pe.status == "available"
    assert pe.current == 20.0
    assert pe.low == 10.0 and pe.high == 20.0
    assert pe.median == 15.0
    # 100 of 200 days were below today's reading.
    assert pe.percentile == 50.0
    assert pe.vs_median_pct == pytest.approx(33.3, abs=0.1)
    assert pe.verdict == "above"
    assert pe.points_used == 200
    # Thinned for the chart, but the latest day is always kept.
    assert pe.series[-1] == (bars[-1][0], 20.0)
    assert len(pe.series) < 200


def test_missing_book_equity_and_revenue_are_unavailable_not_estimated():
    bars = _bars([100.0] * 150)
    facts = [svc.AnnualFacts(period_end=date(2024, 3, 31), net_income=1000.0)]
    bands = {b.metric: b for b in svc.valuation_history(bars, facts, 100.0, False)}
    assert bands["pe"].status == "available"
    assert bands["pb"].status == "unavailable"
    assert bands["pb"].reason == "missing_inputs"
    assert bands["pb"].current is None and bands["pb"].series == []
    assert bands["ps"].status == "unavailable"


def test_loss_year_has_no_current_pe():
    """A latest-year loss means there is no P/E to place inside a band."""
    bars = _bars([100.0] * 400, start=date(2024, 6, 1))
    facts = [
        svc.AnnualFacts(period_end=date(2024, 3, 31), net_income=1000.0),
        svc.AnnualFacts(period_end=date(2025, 3, 31), net_income=-50.0),
    ]
    pe = next(
        b for b in svc.valuation_history(bars, facts, 100.0, False) if b.metric == "pe"
    )
    assert pe.status == "unavailable"
    assert pe.reason == "no_current_reading"
    assert pe.current is None


def test_short_history_is_insufficient():
    bars = _bars([100.0] * 50)
    facts = [svc.AnnualFacts(period_end=date(2024, 3, 31), net_income=1000.0)]
    pe = next(
        b for b in svc.valuation_history(bars, facts, 100.0, False) if b.metric == "pe"
    )
    assert pe.status == "unavailable"
    assert pe.reason == "insufficient_history"
    assert pe.points_used == 50


def test_missing_share_count_makes_every_multiple_unavailable():
    bars = _bars([100.0] * 150)
    facts = [svc.AnnualFacts(period_end=date(2024, 3, 31), net_income=1000.0)]
    bands = svc.valuation_history(bars, facts, shares=None, is_financial=False)
    assert {b.status for b in bands} == {"unavailable"}
    assert {b.reason for b in bands} == {"missing_share_count"}


def test_price_to_sales_not_applicable_for_financials():
    bars = _bars([100.0] * 150)
    facts = [
        svc.AnnualFacts(
            period_end=date(2024, 3, 31),
            net_income=1000.0, revenue=5000.0, book_equity=4000.0,
        )
    ]
    bands = {b.metric: b for b in svc.valuation_history(bars, facts, 100.0, True)}
    assert bands["ps"].status == "not_applicable"
    assert bands["pe"].status == "available"
    assert bands["pb"].status == "available"
    assert bands["pb"].current == 2.5  # 100 x 100 / 4000


# --- Risk --------------------------------------------------------------------


def test_max_drawdown_with_recovery():
    # Peak 120 (day 1), trough 60 (day 3) = -50%; back to 120 on day 5.
    bars = _bars([100.0, 120.0, 90.0, 60.0, 100.0, 120.0, 130.0])
    dd = svc.max_drawdown(bars)
    assert dd.pct == -50.0
    assert dd.peak_date == bars[1][0]
    assert dd.trough_date == bars[3][0]
    assert dd.recovery_date == bars[5][0]
    assert dd.days_to_recover == 2


def test_max_drawdown_not_recovered():
    bars = _bars([100.0, 80.0, 90.0])
    dd = svc.max_drawdown(bars)
    assert dd.pct == -20.0
    assert dd.recovery_date is None
    assert dd.days_to_recover is None


def test_max_drawdown_rising_series_is_zero():
    dd = svc.max_drawdown(_bars([100.0, 101.0, 102.0]))
    assert dd.pct == 0.0
    assert dd.peak_date is None


def test_risk_insufficient_data():
    result = svc.risk(_bars([100.0, 101.0]), [])
    assert result.insufficient_data is True
    assert result.volatility_pct is None
    assert result.beta is None


def test_beta_of_a_doubled_benchmark_is_two():
    """A stock whose daily return is exactly twice the index has beta 2."""
    bench_closes = [100.0]
    stock_closes = [100.0]
    for i in range(150):
        r = 0.01 if i % 2 == 0 else -0.005
        bench_closes.append(bench_closes[-1] * (1 + r))
        stock_closes.append(stock_closes[-1] * (1 + 2 * r))
    result = svc.risk(_bars(stock_closes), _bars(bench_closes))
    assert result.beta == pytest.approx(2.0, abs=0.01)
    assert result.correlation == pytest.approx(1.0, abs=0.01)
    assert result.beta_pairs == 150
    assert result.volatility_pct == pytest.approx(
        2 * result.benchmark_volatility_pct, rel=0.01
    )


def test_beta_needs_enough_paired_days():
    stock = _bars([100.0 + i for i in range(50)])
    bench = _bars([200.0 + i for i in range(50)])
    result = svc.risk(stock, bench)
    assert result.beta is None
    assert result.beta_pairs == 49
    assert result.benchmark_volatility_pct is not None


def test_suspect_move_is_flagged():
    """A 60% one-day fall is reported as a likely unadjusted split."""
    closes = [100.0] * 5 + [40.0] * 5
    result = svc.risk(_bars(closes), [])
    assert result.suspect_move_pct == -60.0
    assert result.suspect_move_date == date(2025, 1, 6)
    assert result.worst_day_pct == -60.0


def test_normal_moves_are_not_flagged():
    result = svc.risk(_bars([100.0, 105.0, 98.0, 101.0]), [])
    assert result.suspect_move_pct is None
    assert result.current_drawdown_pct == pytest.approx(-3.81, abs=0.01)


# --- Return on equity breakdown ----------------------------------------------


def test_dupont_known_values():
    # margin 100/1000 = 10%; turnover 1000/2000 = 0.5; multiplier 2000/800 = 2.5
    # ROE = 0.10 x 0.5 x 2.5 = 12.5% (= 100 / 800).
    result = svc.dupont(
        [
            svc.DupontInputs(
                period_end=date(2025, 3, 31),
                net_income=100.0, revenue=1000.0,
                total_assets=2000.0, book_equity=800.0,
            )
        ],
        is_financial=False,
    )
    assert result.status == "available"
    year = result.years[0]
    assert year.net_margin_pct == 10.0
    assert year.asset_turnover == 0.5
    assert year.equity_multiplier == 2.5
    assert year.roe_pct == 12.5
    # One year: nothing to compare, so no driver is named.
    assert result.driver is None


def test_dupont_names_the_lever_that_moved_most():
    rows = [
        svc.DupontInputs(date(2023, 3, 31), 100.0, 1000.0, 2000.0, 800.0),
        # Margin doubles (10% -> 20%); turnover and leverage barely move.
        svc.DupontInputs(date(2025, 3, 31), 220.0, 1100.0, 2100.0, 850.0),
    ]
    result = svc.dupont(rows, is_financial=False)
    assert result.driver == "margin"
    assert result.from_period == date(2023, 3, 31)
    assert result.to_period == date(2025, 3, 31)
    assert result.roe_change_pts == pytest.approx(25.88 - 12.5, abs=0.01)


def test_dupont_missing_input_is_listed_not_computed():
    result = svc.dupont(
        [svc.DupontInputs(date(2025, 3, 31), 100.0, None, 2000.0, 800.0)],
        is_financial=False,
    )
    assert result.status == "unavailable"
    assert result.reason == "missing_inputs"
    assert result.years[0].missing == ["revenue"]
    assert result.years[0].roe_pct is None


def test_dupont_negative_equity_is_not_computed():
    result = svc.dupont(
        [svc.DupontInputs(date(2025, 3, 31), 100.0, 1000.0, 2000.0, -50.0)],
        is_financial=False,
    )
    assert result.status == "unavailable"
    assert result.years[0].missing == ["non_positive_base"]


def test_dupont_not_applicable_for_financials():
    result = svc.dupont(
        [svc.DupontInputs(date(2025, 3, 31), 100.0, 1000.0, 2000.0, 800.0)],
        is_financial=True,
    )
    assert result.status == "not_applicable"
    assert result.years == []


def test_dupont_drops_a_year_with_no_figures_at_all():
    rows = [
        svc.DupontInputs(date(2022, 3, 31)),
        svc.DupontInputs(date(2025, 3, 31), 100.0, 1000.0, 2000.0, 800.0),
    ]
    result = svc.dupont(rows, is_financial=False)
    assert [y.period_end for y in result.years] == [date(2025, 3, 31)]
    only_empty = svc.dupont([svc.DupontInputs(date(2022, 3, 31))], is_financial=False)
    assert only_empty.status == "unavailable"
    assert only_empty.years == []


def test_dupont_no_rows():
    result = svc.dupont([], is_financial=False)
    assert result.status == "unavailable"
    assert result.reason == "missing_balance_sheet"


# --- API ---------------------------------------------------------------------


async def _seed_depth(session_factory, sector: str = "Energy") -> None:
    """One stock with 400 bars, two fiscal years and a NIFTY series.

    The close doubles once (day 100): a move that large is treated as an
    unadjusted corporate action, so valuation history uses the 300 days after.
    """
    today = date.today()
    start = today - timedelta(days=399)
    async with session_factory() as session:
        stock = Stock(symbol="DEPTH.NS", name="Depth Ltd", sector=sector)
        session.add(stock)
        bench = Benchmark(symbol="^NSEI", name="NIFTY 50", kind="index")
        session.add(bench)
        await session.flush()
        for i in range(400):
            day = start + timedelta(days=i)
            close = 100.0 if i < 100 else 200.0
            session.add(
                DailyPrice(stock_id=stock.id, date=day, open=close, high=close,
                           low=close, close=close, volume=1000)
            )
            bclose = 1000.0 + i
            session.add(
                BenchmarkPrice(benchmark_id=bench.id, date=day, open=bclose,
                               high=bclose, low=bclose, close=bclose, volume=1)
            )
        # Both years published well before the price window opens.
        for year, income, revenue, assets, equity in (
            (today.year - 3, 80.0, 900.0, 1900.0, 760.0),
            (today.year - 2, 100.0, 1000.0, 2000.0, 800.0),
        ):
            end = date(year, 3, 31)
            session.add(
                FinancialPeriod(stock_id=stock.id, period_end=end,
                                period_type="annual", revenue=revenue,
                                net_income=income, eps=1.0, source="test")
            )
            session.add(
                BalanceSheetPeriod(stock_id=stock.id, period_end=end,
                                   period_type="annual", total_assets=assets,
                                   book_equity=equity, source="test")
            )
        # Market cap 20,000 at the latest close of 200 -> 100 shares.
        session.add(Financials(stock_id=stock.id, market_cap=20000))
        await session.commit()


async def test_valuation_history_endpoint(client, session_factory):
    await _seed_depth(session_factory)
    resp = await client.get("/api/v1/stocks/DEPTH/valuation-history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "DEPTH.NS"
    assert body["share_basis"] == "market_cap"
    assert body["publication_lag_days"] == 60
    bands = {b["metric"]: b for b in body["multiples"]}
    # The +100% day is a likely unadjusted corporate action: it is reported,
    # and only the 300 days from it onward (close 200) are used.
    assert body["suspect_move_pct"] == 100.0
    assert body["from_date"] == body["suspect_move_date"]
    # 100 shares, profit 100 -> P/E 200 on every used day (never the pre-move 100).
    assert bands["pe"]["status"] == "available"
    assert bands["pe"]["points_used"] == 300
    assert bands["pe"]["current"] == 200.0
    assert bands["pe"]["low"] == 200.0
    assert bands["pe"]["verdict"] == "near"
    # Book equity 800 -> P/B 25; revenue 1000 -> P/S 20.
    assert bands["pb"]["current"] == 25.0
    assert bands["ps"]["current"] == 20.0
    assert bands["pe"]["series"][-1]["value"] == 200.0


async def test_valuation_history_falls_back_to_eps_share_count(client, session_factory):
    await _seed_depth(session_factory)
    async with session_factory() as session:
        fin = await session.scalar(select(Financials))
        await session.delete(fin)
        await session.commit()
    body = (await client.get("/api/v1/stocks/DEPTH/valuation-history")).json()
    # Newest year: profit 100 / EPS 1 -> 100 shares, same answer.
    assert body["share_basis"] == "eps"
    bands = {b["metric"]: b for b in body["multiples"]}
    assert bands["pe"]["current"] == 200.0


async def test_valuation_history_without_financials_is_unavailable(client, seeded):
    body = (await client.get("/api/v1/stocks/RELIANCE/valuation-history")).json()
    assert body["share_basis"] is None
    assert all(b["status"] == "unavailable" for b in body["multiples"])
    assert all(b["current"] is None for b in body["multiples"])


async def test_risk_endpoint(client, session_factory):
    await _seed_depth(session_factory)
    resp = await client.get("/api/v1/stocks/DEPTH/risk")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bars_used"] == 400
    assert body["insufficient_data"] is False
    assert body["benchmark"] == "^NSEI"
    # One jump from 100 to 200: never below a prior peak.
    assert body["max_drawdown"]["pct"] == 0.0
    assert body["current_drawdown_pct"] == 0.0
    assert body["beta_pairs"] == 399
    assert body["beta"] is not None
    # The +100% day is flagged as a likely unadjusted corporate action.
    assert body["suspect_move_pct"] == 100.0
    assert body["benchmark_volatility_pct"] is not None


async def test_risk_endpoint_short_history(client, seeded):
    body = (await client.get("/api/v1/stocks/RELIANCE/risk")).json()
    assert body["insufficient_data"] is True
    assert body["volatility_pct"] is None
    assert body["beta"] is None
    assert body["underwater"] == []


async def test_quality_endpoint(client, session_factory):
    await _seed_depth(session_factory)
    resp = await client.get("/api/v1/stocks/DEPTH/quality")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "available"
    assert body["cash_flow_available"] is False
    assert len(body["years"]) == 2
    latest = body["years"][-1]
    assert latest["roe_pct"] == 12.5
    assert latest["net_margin_pct"] == 10.0
    assert latest["asset_turnover"] == 0.5
    assert latest["equity_multiplier"] == 2.5
    assert body["driver"] in ("margin", "turnover", "leverage")


async def test_quality_endpoint_financial_sector(client, session_factory):
    await _seed_depth(session_factory, sector="Financial Services")
    body = (await client.get("/api/v1/stocks/DEPTH/quality")).json()
    assert body["status"] == "not_applicable"
    assert body["years"] == []
    vh = (await client.get("/api/v1/stocks/DEPTH/valuation-history")).json()
    bands = {b["metric"]: b for b in vh["multiples"]}
    assert bands["ps"]["status"] == "not_applicable"
    assert bands["pe"]["status"] == "available"


async def test_quality_endpoint_no_balance_sheet(client, seeded):
    body = (await client.get("/api/v1/stocks/RELIANCE/quality")).json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "missing_balance_sheet"


async def test_depth_endpoints_unknown_symbol(client):
    for path in ("valuation-history", "risk", "quality"):
        resp = await client.get(f"/api/v1/stocks/NOPE/{path}")
        assert resp.status_code == 404


# --- Quarterly trend ---------------------------------------------------------


def _q(day: str, revenue, income, net_margin=None) -> svc.QuarterFacts:
    return svc.QuarterFacts(
        period_end=date.fromisoformat(day),
        revenue=revenue, net_income=income, net_margin=net_margin,
    )


def test_quarterly_trend_year_on_year():
    rows = [
        _q("2025-06-30", 100.0, 10.0, 0.10),
        _q("2025-09-30", 110.0, 11.0, 0.10),
        _q("2026-06-30", 120.0, 15.0, 0.125),
        _q("2026-09-30", 143.0, 11.0, 0.077),
    ]
    trend = svc.quarterly_trend(rows)
    assert trend.insufficient_data is False
    first, second, third, fourth = trend.quarters
    # No year-earlier quarter stored: change stays missing.
    assert first.revenue_yoy_pct is None and second.net_income_yoy_pct is None
    assert third.revenue_yoy_pct == 20.0
    assert third.net_income_yoy_pct == 50.0
    assert third.net_margin_yoy_pts == 2.5
    assert fourth.revenue_yoy_pct == 30.0
    assert fourth.net_income_yoy_pct == 0.0
    # 30% after 20%: sales growth is speeding up; two growing quarters in a row.
    assert trend.momentum == "faster"
    assert trend.revenue_growth_streak == 2


def test_quarterly_trend_no_growth_off_a_loss():
    rows = [_q("2025-09-30", 100.0, -5.0), _q("2026-09-30", 90.0, 8.0)]
    latest = svc.quarterly_trend(rows).quarters[-1]
    assert latest.revenue_yoy_pct == -10.0
    assert latest.net_income_yoy_pct is None
    assert svc.quarterly_trend(rows).revenue_growth_streak == 0


def test_quarterly_trend_gap_is_not_bridged():
    """A missing year-earlier quarter is not replaced by a neighbouring one."""
    rows = [_q("2025-06-30", 100.0, 10.0), _q("2026-09-30", 150.0, 20.0)]
    trend = svc.quarterly_trend(rows)
    assert trend.quarters[-1].revenue_yoy_pct is None
    assert trend.momentum is None


def test_quarterly_trend_empty_and_capped():
    assert svc.quarterly_trend([]).insufficient_data is True
    many = [
        _q(f"{2020 + i // 4}-{(3, 6, 9, 12)[i % 4]:02d}-28", 100.0 + i, 10.0)
        for i in range(20)
    ]
    assert len(svc.quarterly_trend(many).quarters) == svc.MAX_QUARTERS


async def test_quarterly_trend_endpoint(client, session_factory):
    await _seed_depth(session_factory)
    async with session_factory() as session:
        stock = await session.scalar(select(Stock).where(Stock.symbol == "DEPTH.NS"))
        for day, revenue, income in (
            ("2025-09-30", 200.0, 20.0), ("2026-09-30", 250.0, 30.0),
        ):
            session.add(
                FinancialPeriod(stock_id=stock.id, period_end=date.fromisoformat(day),
                                period_type="quarterly", revenue=revenue,
                                net_income=income, net_margin=income / revenue,
                                source="test")
            )
        await session.commit()
    body = (await client.get("/api/v1/stocks/DEPTH/quarterly-trend")).json()
    assert body["insufficient_data"] is False
    assert [q["period_end"] for q in body["quarters"]] == ["2025-09-30", "2026-09-30"]
    latest = body["quarters"][-1]
    assert latest["revenue_yoy_pct"] == 25.0
    assert latest["net_income_yoy_pct"] == 50.0
    assert latest["net_margin_pct"] == 12.0
    assert body["revenue_growth_streak"] == 1


async def test_quarterly_trend_endpoint_empty(client, seeded):
    body = (await client.get("/api/v1/stocks/RELIANCE/quarterly-trend")).json()
    assert body["insufficient_data"] is True
    assert body["quarters"] == []
