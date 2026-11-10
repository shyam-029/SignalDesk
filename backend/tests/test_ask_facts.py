# Pure tests for the precomputed price-history facts (no DB, no network).
# Known synthetic series with hand-checkable answers.

from datetime import date, timedelta

from app.services import ask_facts

START = date(2025, 1, 1)


def _bars(closes: list[float]):
    """Daily bars (date, close, high, low); high/low bracket the close by 1."""
    return [
        (START + timedelta(days=i), c, c + 1.0, c - 1.0) for i, c in enumerate(closes)
    ]


def test_too_few_bars_returns_none():
    assert ask_facts.price_history_facts(_bars([100.0] * (ask_facts.MIN_BARS - 1))) is None


def test_biggest_gain_and_drop_are_exact():
    closes = [100.0] * 40
    closes[10] = 110.0   # +10% on day 10, then back down -> -9.0909% on day 11
    closes[11] = 100.0
    closes[20] = 90.0    # -10% on day 20, then +11.11% on day 21
    closes[21] = 100.0
    facts = ask_facts.price_history_facts(_bars(closes))
    top_gain = facts["biggest_gains"][0]
    top_drop = facts["biggest_drops"][0]
    assert top_gain["change_pct"] == 11.11 and top_gain["date"] == (START + timedelta(days=21)).isoformat()
    assert top_drop["change_pct"] == -10.0 and top_drop["date"] == (START + timedelta(days=20)).isoformat()
    assert len(facts["biggest_gains"]) <= ask_facts.TOP_MOVES


def test_up_down_counts_and_average_move():
    # Alternate +1 / -1 around 100: 39 changes -> 20 up, 19 down (starting up).
    closes = [100.0 + (i % 2) for i in range(40)]
    facts = ask_facts.price_history_facts(_bars(closes))
    assert facts["trading_days"] == 39
    assert facts["up_days"] + facts["down_days"] == 39
    assert facts["avg_abs_daily_move_pct"] > 0


def test_max_drawdown_peak_and_trough_dates():
    closes = [100.0] * 5 + [200.0] + [100.0] * 34  # peak 200 on day 5, falls to 100
    facts = ask_facts.price_history_facts(_bars(closes))
    assert facts["max_drawdown_pct"] == -50.0
    assert facts["max_drawdown_peak_date"] == (START + timedelta(days=5)).isoformat()
    assert facts["max_drawdown_trough_date"] == (START + timedelta(days=6)).isoformat()


def test_52_week_high_low_come_with_dates_and_distance():
    closes = [100.0] * 40
    closes[15] = 150.0
    closes[30] = 80.0
    facts = ask_facts.price_history_facts(_bars(closes))
    assert facts["high_52w"] == 151.0 and facts["high_52w_date"] == (START + timedelta(days=15)).isoformat()
    assert facts["low_52w"] == 79.0 and facts["low_52w_date"] == (START + timedelta(days=30)).isoformat()
    # last close 100 versus high 151 -> -33.77%
    assert facts["pct_from_52w_high"] == -33.77


def test_recent_closes_are_the_latest_ten_in_order():
    closes = [100.0 + i for i in range(60)]
    facts = ask_facts.price_history_facts(_bars(closes))
    recent = facts["recent_closes"]
    assert len(recent) == ask_facts.RECENT_CLOSES
    assert [r["close"] for r in recent] == [150.0 + i for i in range(10)]
    assert recent[-1]["date"] == facts["as_of"]


def test_window_is_one_trading_year():
    closes = [100.0] * 600
    closes[5] = 500.0  # a spike far older than a year must not appear
    facts = ask_facts.price_history_facts(_bars(closes))
    assert facts["trading_days"] == ask_facts.WINDOW_BARS
    assert all(abs(m["change_pct"]) < 1 for m in facts["biggest_gains"] + facts["biggest_drops"]) or not (
        facts["biggest_gains"] or facts["biggest_drops"]
    )


def test_flat_series_has_no_moves_and_no_drawdown():
    facts = ask_facts.price_history_facts(_bars([100.0] * 40))
    assert facts["biggest_gains"] == [] and facts["biggest_drops"] == []
    assert facts["max_drawdown_pct"] == 0.0
    assert facts["avg_abs_daily_move_pct"] == 0.0
