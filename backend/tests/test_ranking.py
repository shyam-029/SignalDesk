# Top-1000 universe ranking tests (M1-T2, Plan 7).
#
# Zero-network like the rest of the suite:
#   - pure-rule tests build synthetic master rows / candidates directly;
#   - DB integration tests inject a synthetic master list and a stub
#     provider, with SessionLocal redirected to signaldesk_test via
#     monkeypatch (same pattern as test_jobs_status.py).
#
# Covered categories (plan section 5):
#   1. each eligibility rule E1-E12 in isolation
#   2. ranking math (order, tiebreak, cutoff, ranked_out rank)
#   3. audit-trail correctness (one row per symbol, reasons, idempotency)
#   4. catalog rows never deleted (E10 keeps history)
#   5. universe write: top1000 membership == ranked_in; other universes intact
#   6. NSE master parsing (synthetic CSV bytes)
#   7. job pass recording via _record_pass

import gzip
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import func, insert, select

from app import jobs as jobs_module
from app.data.ranking_exclusions import curated_exclusion
from app.models import DailyPrice, RankingAudit, RankingCycle, Stock, Universe, stock_universe
from app.providers.nse_master import NseMasterRow, classify_series, parse_instruments
from app.providers.base import Fundamentals, MarketDataError
from app.services import ranking as svc


def _row(symbol, series="EQ", isin=None, name=None):
    return NseMasterRow(symbol=symbol, name=name or symbol, series=series, isin=isin)


def _cand(
    symbol,
    master=None,
    stock_id=None,
    catalog_symbol=None,
    match_kind="direct",
    mcap=None,
    mcap_error=None,
    last_bar=None,
    first_bar=None,
):
    return svc.Candidate(
        symbol=symbol,
        master=master,
        stock_id=stock_id,
        catalog_symbol=catalog_symbol,
        match_kind=match_kind,
        name=(master.name if master else symbol),
        mcap=mcap,
        mcap_error=mcap_error,
        prices=svc.PriceFacts(last_bar_date=last_bar, first_bar_date=first_bar),
    )


def _ctx(ref=(), size=1000, today=None, aliases=None):
    return svc.RankContext(
        today=today or date(2026, 9, 8),
        reference_dates=tuple(ref),
        ranked_size=size,
        symbol_aliases=aliases,
    )


# --- Category 6: securities master parsing -----------------------------------


def _master_gzip(entries: list[dict]) -> bytes:
    """Gzipped instruments-master payload (the wire format Upstox serves)."""
    return gzip.compress(json.dumps(entries).encode("utf-8"))


def _inst(symbol, series="EQ", isin=None, name=None, segment="NSE_EQ"):
    return {
        "segment": segment,
        "instrument_type": series,
        "isin": isin,
        "name": name or symbol,
        "trading_symbol": symbol,
    }


def test_parse_instruments_reads_rows():
    rows = parse_instruments(
        _master_gzip(
            [_inst("RELIANCE", "EQ", "INE002A01018", "RELIANCE INDUSTRIES LTD")]
        )
    )
    assert len(rows) == 1
    assert rows[0].symbol == "RELIANCE"
    assert rows[0].name == "RELIANCE INDUSTRIES LTD"
    assert rows[0].series == "EQ"
    assert rows[0].isin == "INE002A01018"


def test_parse_instruments_skips_other_segments_and_blanks():
    content = _master_gzip(
        [
            _inst("AAA", "EQ", "INE111A01018"),
            _inst("FOOPT", "CE", segment="NSE_FO"),
            _inst("", "EQ"),
            _inst("BBB", "BE", "INE222B01018"),
        ]
    )
    rows = parse_instruments(content)
    assert [r.symbol for r in rows] == ["AAA", "BBB"]


def test_parse_instruments_dedupes_symbol_preferring_eq():
    content = _master_gzip(
        [
            _inst("DUAL", "BE", "INE111A01018"),
            _inst("DUAL", "EQ", "INE111A01018"),
        ]
    )
    rows = parse_instruments(content)
    assert len(rows) == 1
    assert rows[0].series == "EQ"


def test_parse_instruments_unreadable_payload_raises():
    with pytest.raises(MarketDataError):
        parse_instruments(b"not gzip at all")


def test_classify_series_eq_be_bz_and_other():
    assert classify_series("EQ") == "eligible"
    assert classify_series("BE") == "flagged"
    assert classify_series("BZ") == "flagged"
    assert classify_series("RR") == "excluded"  # REIT
    assert classify_series("IV") == "excluded"  # InvIT
    assert classify_series("SG") == "excluded"  # SGB
    assert classify_series("N0") == "excluded"  # debenture
    assert classify_series("") == "excluded"


# --- Category 1a: curated exclusions data (E2/E4) ----------------------------


def test_curated_etf_and_not_ordinary():
    assert curated_exclusion("NIFTYBEES") == ("etf", "ETF")
    assert curated_exclusion("EMBASSY") == ("not_ordinary_equity", "REIT")
    assert curated_exclusion("IRBINVIT") == ("not_ordinary_equity", "InvIT")
    assert curated_exclusion("RELIANCE") is None


# --- Category 1b: matching (E5) ----------------------------------------------


def _catalog(*entries):
    return [svc.CatalogStock(*e) for e in entries]


def test_match_direct_symbol():
    catalog = _catalog((1, "RELIANCE.NS", "Reliance", "INE002A01018", True))
    matches = svc.match_master_to_catalog([_row("RELIANCE")], catalog, {})
    assert matches["RELIANCE"] == (1, "RELIANCE.NS", "direct")


def test_match_alias_rename():
    catalog = _catalog((1, "TATAMOTORS.NS", "Tata Motors", "INE155A01022", True))
    matches = svc.match_master_to_catalog(
        [_row("TMPV", isin="INE155A01022")], catalog, {"TATAMOTORS": "TMPV"}
    )
    assert matches["TMPV"] == (1, "TATAMOTORS.NS", "alias")


def test_match_isin_is_rename_unmapped():
    catalog = _catalog((1, "OLDSYM.NS", "Old Name", "INE999A01019", True))
    matches = svc.match_master_to_catalog(
        [_row("NEWSYM", isin="INE999A01019")], catalog, {}
    )
    assert matches["NEWSYM"] == (1, "OLDSYM.NS", "isin")


def test_match_unknown_symbol_has_no_entry():
    matches = svc.match_master_to_catalog([_row("BRANDNEW")], _catalog(), {})
    assert "BRANDNEW" not in matches


# --- Category 1c: eligibility rules in isolation (evaluate) ------------------


def test_e1_series_excluded():
    d = svc.evaluate([_cand("SOMEBOND", master=_row("SOMEBOND", series="IL"))], _ctx())[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "not_ordinary_equity")
    assert d.detail == "series IL"


def test_e2_etf_excluded_and_flagged_is_etf():
    d = svc.evaluate([_cand("NIFTYBEES", master=_row("NIFTYBEES"), mcap=1.0)], _ctx())[0]
    assert (d.outcome, d.reason, d.detail) == (svc.EXCLUDED, "etf", "ETF")
    assert d.is_etf is True


def test_e4_reit_excluded_with_class_detail():
    d = svc.evaluate([_cand("EMBASSY", master=_row("EMBASSY"), mcap=1.0)], _ctx())[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "not_ordinary_equity")
    assert d.detail == "REIT"


def test_e5_rename_unmapped_excluded():
    d = svc.evaluate(
        [
            _cand(
                "NEWSYM",
                master=_row("NEWSYM", isin="INE999A01019"),
                stock_id=1,
                catalog_symbol="OLDSYM.NS",
                match_kind="isin",
                mcap=10.0,
            )
        ],
        _ctx(),
    )[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "rename_unmapped")
    assert d.deactivate is False


def test_e10_absent_from_master_excluded_and_deactivates():
    d = svc.evaluate(
        [_cand("OLDCO", master=None, stock_id=7, catalog_symbol="OLDCO.NS")], _ctx()
    )[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "absent_from_master")
    assert d.deactivate is True


def test_e5_rename_shadow_not_deactivated():
    """Old symbol still in the catalog, alias-mapped to a ranked new row."""
    master = _row("TMPV", isin="INE155A01022")
    matches = {"TMPV": (59, "TMPV.NS", "direct")}
    candidates = svc.build_candidates(
        [master],
        _catalog(
            (59, "TMPV.NS", "Tata PV", "INE155A01022", True),
            (19, "TATAMOTORS.NS", "Tata Motors", None, True),
        ),
        matches,
        {59: svc.PriceFacts(last_bar_date=date(2026, 9, 8), first_bar_date=date(2026, 8, 1))},
        mcaps={"TMPV": (500.0, None)},
        symbol_aliases={"TATAMOTORS": "TMPV"},
    )
    ds = {d.symbol: d for d in svc.evaluate(candidates, _ctx(aliases={"TATAMOTORS": "TMPV"}))}
    assert ds["TMPV"].outcome == svc.RANKED_IN
    shadow = ds["TATAMOTORS"]
    assert (shadow.outcome, shadow.reason) == (svc.EXCLUDED, "renamed")
    assert shadow.deactivate is False  # same live entity, never delisted
    assert "TMPV" in shadow.detail


def test_e5_alias_target_absent_still_deactivates():
    """Alias target NOT in the master: the old row really is gone."""
    candidates = svc.build_candidates(
        [],
        _catalog((19, "OLDSYM.NS", "Old Co", None, True)),
        {},
        {},
        symbol_aliases={"OLDSYM": "NEWSYM"},
    )
    d = svc.evaluate(candidates, _ctx())[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "absent_from_master")
    assert d.deactivate is True


def test_e9_stale_beyond_limit_excluded():
    ref = tuple(sorted(date(2026, 9, 8) - timedelta(days=i) for i in range(40)))
    last_bar = ref[8]  # 31 reference dates strictly after -> stale
    d = svc.evaluate(
        [
            _cand(
                "SLEEPY",
                master=_row("SLEEPY"),
                stock_id=3,
                catalog_symbol="SLEEPY.NS",
                mcap=10.0,
                last_bar=last_bar,
                first_bar=last_bar,
            )
        ],
        _ctx(ref=ref),
    )[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "inactive_proxy")
    assert d.deactivate is True
    assert "31 trading days stale" in d.detail


def test_e9_exactly_30_stale_days_is_eligible():
    ref = tuple(sorted(date(2026, 9, 8) - timedelta(days=i) for i in range(40)))
    last_bar = ref[9]  # exactly 30 reference dates after -> NOT excluded
    d = svc.evaluate(
        [
            _cand(
                "EDGE",
                master=_row("EDGE"),
                stock_id=3,
                catalog_symbol="EDGE.NS",
                mcap=10.0,
                last_bar=last_bar,
                first_bar=last_bar,
            )
        ],
        _ctx(ref=ref),
    )[0]
    assert d.outcome == svc.RANKED_IN
    assert d.deactivate is False


def test_e9_zero_bars_is_eligible_not_yet_priced():
    d = svc.evaluate(
        [_cand("FRESH", master=_row("FRESH"), stock_id=9, catalog_symbol="FRESH.NS", mcap=3.0)],
        _ctx(),
    )[0]
    assert d.outcome == svc.RANKED_IN
    assert d.flag == svc.FLAG_UNPRICED
    assert d.deactivate is False


def test_e7_no_mcap_excluded_strict():
    d = svc.evaluate(
        [_cand("NOMCAP", master=_row("NOMCAP"), stock_id=4, catalog_symbol="NOMCAP.NS")],
        _ctx(),
    )[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "no_mcap")
    assert "no market cap" in d.detail


def test_e7_fetch_failure_records_error_detail():
    d = svc.evaluate(
        [
            _cand(
                "ERRSYMBOL",
                master=_row("ERRSYMBOL"),
                stock_id=4,
                catalog_symbol="ERRSYMBOL.NS",
                mcap_error="MarketDataError: throttled",
            )
        ],
        _ctx(),
    )[0]
    assert (d.outcome, d.reason) == (svc.EXCLUDED, "no_mcap")
    assert "throttled" in d.detail


def test_e8_recent_listing_flagged():
    today = date(2026, 9, 8)
    d = svc.evaluate(
        [
            _cand(
                "IPO",
                master=_row("IPO"),
                stock_id=5,
                catalog_symbol="IPO.NS",
                mcap=8.0,
                last_bar=today - timedelta(days=10),
                first_bar=today - timedelta(days=10),
            )
        ],
        _ctx(today=today),
    )[0]
    assert d.outcome == svc.RANKED_IN
    assert d.flag == svc.FLAG_RECENT


def test_e12_derivatives_out_of_scope_no_crash():
    # A master row in a derivatives-only series never becomes a candidate
    # issue: it is simply E1-excluded like any other non-ordinary series.
    d = svc.evaluate([_cand("FUTIDX", master=_row("FUTIDX", series="IV"))], _ctx())[0]
    assert d.reason == "not_ordinary_equity"


# --- Category 2: ranking math -------------------------------------------------


def test_ranking_orders_desc_and_breaks_ties_by_symbol():
    today = date(2026, 9, 8)
    cands = [
        _cand("B", master=_row("B"), stock_id=2, catalog_symbol="B.NS", mcap=100.0),
        _cand("A", master=_row("A"), stock_id=1, catalog_symbol="A.NS", mcap=100.0),
        _cand("C", master=_row("C"), stock_id=3, catalog_symbol="C.NS", mcap=300.0),
    ]
    ds = {d.symbol: d for d in svc.evaluate(cands, _ctx(size=2, today=today))}
    assert ds["C"].rank == 1 and ds["C"].outcome == svc.RANKED_IN
    # Tie at 100: A sorts before B; A takes rank 2 (last ranked_in slot).
    assert ds["A"].rank == 2 and ds["A"].outcome == svc.RANKED_IN
    assert ds["B"].rank == 3 and ds["B"].outcome == svc.RANKED_OUT
    assert ds["B"].reason == "beyond_cutoff"


def test_ranked_out_carries_exact_rank():
    cands = [
        _cand(f"S{i}", master=_row(f"S{i}"), stock_id=i, catalog_symbol=f"S{i}.NS",
              mcap=1000.0 - i)
        for i in range(5)
    ]
    ds = svc.evaluate(cands, _ctx(size=2))
    outs = [d for d in ds if d.outcome == svc.RANKED_OUT]
    assert [d.rank for d in outs] == [3, 4, 5]


def test_flag_precedence_renamed_beats_restricted_and_recent():
    today = date(2026, 9, 8)
    d = svc.evaluate(
        [
            _cand(
                "TMPV",
                master=_row("TMPV", series="BE"),
                stock_id=1,
                catalog_symbol="TATAMOTORS.NS",
                match_kind="alias",
                mcap=50.0,
                last_bar=today - timedelta(days=5),
                first_bar=today - timedelta(days=5),
            )
        ],
        _ctx(today=today),
    )[0]
    assert d.flag == svc.FLAG_RENAMED


# --- Category 2b: helpers ------------------------------------------------------


def test_stale_trading_days_none_and_counts():
    ref = (date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3))
    assert svc.stale_trading_days(None, ref) is None
    assert svc.stale_trading_days(date(2026, 9, 2), ref) == 1
    assert svc.stale_trading_days(date(2026, 9, 3), ref) == 0
    assert svc.stale_trading_days(date(2026, 8, 1), ref) == 3


def test_cycle_reference_asof_prefers_market_data():
    ref = (date(2026, 9, 1), date(2026, 9, 5))
    assert svc.cycle_reference_asof(ref, date(2026, 9, 8)) == date(2026, 9, 5)
    assert svc.cycle_reference_asof((), date(2026, 9, 8)) == date(2026, 9, 8)


def test_decision_updates_ranked_and_deactivated():
    today = date(2026, 9, 8)
    ranked = svc.Decision(
        symbol="A", catalog_symbol="A.NS", stock_id=1, series="EQ", isin=None,
        name="A", outcome=svc.RANKED_IN, reason=None, flag=None, detail=None,
        mcap=5.0, rank=3,
    )
    upd = svc.decision_updates(ranked)
    assert upd["active"] is True
    assert upd["mcap_rank"] == 3
    assert "mcap_asof" not in upd  # repository stamps the cycle date
    out = svc.Decision(
        symbol="B", catalog_symbol="B.NS", stock_id=2, series=None, isin=None,
        name="B", outcome=svc.EXCLUDED, reason="inactive_proxy", flag=None,
        detail=None, mcap=None, rank=None, deactivate=True,
    )
    updo = svc.decision_updates(out)
    assert updo["active"] is False and updo["delisted_reason"] == "inactive_proxy"
    assert "delisted_at" not in updo  # repository stamps the timestamp
    absent = svc.Decision(
        symbol="X", catalog_symbol="X.NS", stock_id=None, series=None, isin=None,
        name="X", outcome=svc.EXCLUDED, reason="x", flag=None, detail=None,
        mcap=None, rank=None,
    )
    assert svc.decision_updates(absent) == {}


# --- Stub provider for DB integration -----------------------------------------


class StubRankProvider:
    """Market-cap stub: dict of bare master symbol -> mcap (or raising)."""

    name = "stub"

    def __init__(self, mcaps: dict[str, float], fail: set[str] | None = None):
        self.mcaps = mcaps
        self.fail = fail or set()

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        bare = symbol.split(".")[0]
        if bare in self.fail:
            raise MarketDataError(f"throttled {bare}")
        return Fundamentals(symbol=symbol, market_cap=self.mcaps.get(bare))

    async def get_price_history(self, symbol, period):
        return []

    async def get_stock_profile(self, symbol):
        raise MarketDataError("unused")


# --- Categories 3-5: DB integration (audit, idempotency, never-deletes) ------


async def _seed_catalog(session_factory):
    """Catalog: two rankable, one ETF-matched, one stale, one master-absent."""
    async with session_factory() as s:
        s.add_all(
            [
                Stock(symbol="RELIANCE.NS", name="Reliance", isin="INE002A01018"),
                Stock(symbol="TCS.NS", name="TCS", isin="INE467B01029"),
                Stock(symbol="NIFTYBEES.NS", name="Nifty BeES", isin="INE120A08018"),
                Stock(symbol="SLEEPY.NS", name="Sleepy Co", isin="INE333D01016"),
                Stock(symbol="OLDCO.NS", name="Old Co", isin="INE777B01017"),
            ]
        )
        await s.flush()
        ids = {
            r.symbol: r.id
            for r in (await s.execute(select(Stock))).scalars()
        }
        # Prices: RELIANCE/TCS fresh (5 market days); OLDCO has 40 bars ending
        # 5 market days ago (it stays the master-absent case); SLEEPY last bar
        # 35 distinct market dates ago -> inactive_proxy (E9).
        recent = [date(2026, 9, 8) - timedelta(days=i) for i in range(5)]
        oldeo = [date(2026, 9, 8) - timedelta(days=i) for i in range(5, 45)]
        for d in recent:
            s.add(DailyPrice(stock_id=ids["RELIANCE.NS"], date=d, open=1, high=1,
                             low=1, close=1, volume=1))
            s.add(DailyPrice(stock_id=ids["TCS.NS"], date=d, open=1, high=1,
                             low=1, close=1, volume=1))
        for d in oldeo:
            s.add(DailyPrice(stock_id=ids["OLDCO.NS"], date=d, open=1, high=1,
                             low=1, close=1, volume=1))
        for d in (date(2026, 8, 3), date(2026, 8, 4)):
            s.add(DailyPrice(stock_id=ids["SLEEPY.NS"], date=d, open=1, high=1,
                             low=1, close=1, volume=1))
        # A second universe that must stay untouched by ranking.
        s.add(Universe(name="nifty250"))
        uni = await s.scalar(select(Universe).where(Universe.name == "nifty250"))
        await s.execute(
            insert(stock_universe).values(universe_id=uni.id, stock_id=ids["TCS.NS"])
        )
        await s.commit()
        return ids


def _master_rows():
    return [
        _row("RELIANCE", isin="INE002A01018"),
        _row("TCS", isin="INE467B01029"),
        _row("NIFTYBEES", isin="INE120A08018"),
        _row("EMBASSY", isin="INE888R01011"),
        _row("SOMEBOND", series="IL"),
        _row("SLEEPY", isin="INE333D01016"),
        _row("NEWIPO", isin="INE555C01012"),
    ]


def _stub_provider():
    return StubRankProvider(
        mcaps={"RELIANCE": 100.0, "TCS": 50.0, "NEWIPO": 5.0, "EMBASSY": 90.0}
    )


async def _audit_rows(session_factory, cycle_id):
    async with session_factory() as s:
        return list(
            (await s.execute(
                select(RankingAudit).where(RankingAudit.cycle_id == cycle_id)
            )).scalars()
        )


async def test_full_ranking_pipeline(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    ids = await _seed_catalog(session_factory)

    result = await jobs_module.rank_universe(
        provider=_stub_provider(), master_rows=_master_rows()
    )

    # Result counts: ranked = RELIANCE, TCS, NEWIPO (ETF/REIT/series-excluded/
    # stale SLEEPY/master-absent OLDCO are out; all mcap fetches succeeded).
    assert result["ranked"] == 3
    assert result["excluded"] == 5  # NIFTYBEES, EMBASSY, SOMEBOND, SLEEPY, OLDCO
    assert result["errors"] == 0

    # One cycle row, dated today, universe top1000.
    async with session_factory() as s:
        cycles = list((await s.execute(select(RankingCycle))).scalars())
        assert len(cycles) == 1
        assert cycles[0].universe_name == "top1000"
        cycle_id = cycles[0].id

    # One audit row per master symbol + the absent catalog stock.
    rows = await _audit_rows(session_factory, cycle_id)
    by_symbol = {r.symbol: r for r in rows}
    assert len(rows) == 8  # 7 master rows + OLDCO (absent)
    assert by_symbol["RELIANCE"].outcome == "ranked_in"
    assert by_symbol["RELIANCE"].rank == 1
    assert by_symbol["RELIANCE"].mcap == 100.0
    assert by_symbol["TCS"].outcome == "ranked_in"
    assert by_symbol["NIFTYBEES"].reason == "etf"
    assert by_symbol["EMBASSY"].reason == "not_ordinary_equity"
    assert by_symbol["SOMEBOND"].reason == "not_ordinary_equity"
    assert by_symbol["SLEEPY"].reason == "inactive_proxy"
    assert "trading days stale" in by_symbol["SLEEPY"].detail
    assert by_symbol["OLDCO"].reason == "absent_from_master"
    assert by_symbol["OLDCO"].catalog_symbol == "OLDCO.NS"
    assert by_symbol["NEWIPO"].catalog_symbol == "NEWIPO.NS"  # created this run
    assert by_symbol["NEWIPO"].flag == "not_yet_priced"

    # Universe membership == ranked_in set; nifty250 untouched.
    async with session_factory() as s:
        newipo_id = await s.scalar(select(Stock.id).where(Stock.symbol == "NEWIPO.NS"))
        uni = await s.scalar(select(Universe).where(Universe.name == "top1000"))
        member_rows = (
            await s.execute(
                select(stock_universe).where(
                    stock_universe.c.universe_id == uni.id
                )
            )
        ).all()
        members = {r.stock_id for r in member_rows}
        assert members == {ids["RELIANCE.NS"], ids["TCS.NS"], newipo_id}
        n250 = await s.scalar(select(Universe).where(Universe.name == "nifty250"))
        n250_members = (
            await s.execute(
                select(stock_universe).where(stock_universe.c.universe_id == n250.id)
            )
        ).all()
        assert len(n250_members) == 1

    # Stocks metadata: ranks set, ETF flagged, delisted deactivated, new row.
    async with session_factory() as s:
        stocks = {
            r.symbol: r for r in (await s.execute(select(Stock))).scalars()
        }
        assert stocks["RELIANCE.NS"].mcap_rank == 1
        assert stocks["RELIANCE.NS"].active is True
        assert stocks["TCS.NS"].mcap_rank == 2
        assert stocks["NEWIPO.NS"].mcap_rank == 3
        assert stocks["NIFTYBEES.NS"].is_etf is True
        assert stocks["SLEEPY.NS"].active is False
        assert stocks["SLEEPY.NS"].delisted_reason == "inactive_proxy"
        assert stocks["SLEEPY.NS"].delisted_at is not None
        assert stocks["OLDCO.NS"].active is False
        assert stocks["OLDCO.NS"].delisted_reason == "absent_from_master"
        assert stocks["OLDCO.NS"].delisted_at is not None


async def test_rerun_same_day_is_idempotent(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_catalog(session_factory)

    first = await jobs_module.rank_universe(
        provider=_stub_provider(), master_rows=_master_rows()
    )
    async with session_factory() as s:
        cycle_before = (await s.execute(select(RankingCycle))).scalars().first()
        audit_before = (
            await s.execute(
                select(func.count()).select_from(RankingAudit)
            )
        ).scalar()
    second = await jobs_module.rank_universe(
        provider=_stub_provider(), master_rows=_master_rows()
    )
    async with session_factory() as s:
        cycles = list((await s.execute(select(RankingCycle))).scalars())
        assert len(cycles) == 1  # same-day re-run reuses the cycle row
        assert cycles[0].id == cycle_before.id
        audit_after = (
            await s.execute(select(func.count()).select_from(RankingAudit))
        ).scalar()
        assert audit_after == audit_before

        # No duplicate universe links.
        uni = await s.scalar(select(Universe).where(Universe.name == "top1000"))
        links = (
            await s.execute(
                select(stock_universe).where(stock_universe.c.universe_id == uni.id)
            )
        ).all()
        assert len(links) == first["ranked"] == second["ranked"]


async def test_catalog_rows_never_deleted_and_history_retained(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    ids = await _seed_catalog(session_factory)

    async with session_factory() as s:
        stocks_before = (
            await s.execute(select(func.count()).select_from(Stock))
        ).scalar()
        prices_before = (
            await s.execute(select(func.count()).select_from(DailyPrice))
        ).scalar()

    await jobs_module.rank_universe(
        provider=_stub_provider(), master_rows=_master_rows()
    )

    async with session_factory() as s:
        stocks_after = (
            await s.execute(select(func.count()).select_from(Stock))
        ).scalar()
        # +1: NEWIPO created (creation is allowed; deletion is not).
        assert stocks_after == stocks_before + 1
        assert (
            await s.execute(select(func.count()).select_from(DailyPrice))
        ).scalar() == prices_before

        # The deactivated row keeps every bar it ever had.
        oldeo_bars = (
            await s.execute(
                select(func.count())
                .select_from(DailyPrice)
                .where(DailyPrice.stock_id == ids["OLDCO.NS"])
            )
        ).scalar()
        assert oldeo_bars == 40


async def test_mcap_fetch_failure_is_isolated_and_audited(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_catalog(session_factory)
    provider = StubRankProvider(
        mcaps={"RELIANCE": 100.0, "TCS": 50.0}, fail={"NEWIPO"}
    )

    result = await jobs_module.rank_universe(
        provider=provider, master_rows=_master_rows()
    )
    assert result["errors"] == 1

    async with session_factory() as s:
        cycle = (await s.execute(select(RankingCycle))).scalars().first()
    rows = await _audit_rows(session_factory, cycle.id)
    newipo = next(r for r in rows if r.symbol == "NEWIPO")
    assert (newipo.outcome, newipo.reason) == ("excluded", "no_mcap")
    assert "throttled" in newipo.detail


async def test_rank_pass_recorded_in_job_runs(session_factory, monkeypatch):
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_catalog(session_factory)

    await jobs_module._record_pass(
        "rank_universe", jobs_module.rank_universe,
        _stub_provider(), _master_rows(),
    )

    from app.models import JobRun

    async with session_factory() as s:
        run = (
            await s.execute(
                select(JobRun).where(JobRun.job_name == "rank_universe")
            )
        ).scalars().first()
    assert run is not None
    assert run.status == "success"
    assert run.items_processed == 3  # "ranked" counted via _PROCESSED_KEYS


async def test_rank_universe_uses_injected_master_without_network(session_factory, monkeypatch):
    """master_rows injection never triggers the live master fetch."""
    monkeypatch.setattr(jobs_module, "SessionLocal", session_factory)
    await _seed_catalog(session_factory)

    async def boom():
        raise AssertionError("live master fetch must not run when injected")

    monkeypatch.setattr(jobs_module, "fetch_master_with_retry", boom)
    result = await jobs_module.rank_universe(
        provider=_stub_provider(), master_rows=_master_rows()
    )
    assert result["ranked"] == 3
