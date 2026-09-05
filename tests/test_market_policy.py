from datetime import datetime, timezone


def test_regular_market_is_allowed_at_22_tehran_but_blocked_at_23():
    from src.market_policy import regular_market_allowed

    at_22 = datetime(2026, 9, 6, 18, 30, tzinfo=timezone.utc)  # 22:00 Tehran
    at_23 = datetime(2026, 9, 6, 19, 30, tzinfo=timezone.utc)  # 23:00 Tehran
    assert regular_market_allowed(at_22, is_holiday=False)
    assert not regular_market_allowed(at_23, is_holiday=False)


def test_regular_market_is_blocked_before_8_tehran():
    from src.market_policy import regular_market_allowed

    at_0730 = datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)  # 07:30 Tehran
    assert not regular_market_allowed(at_0730, is_holiday=False)


def test_daily_summary_waits_until_2330_and_never_runs_at_midnight():
    from src.market_policy import market_summary_day

    state = {
        "market_day_prices": {
            "date": "2026-09-06",
            "first_usd": 200000,
            "last_usd": 210000,
            "first_gold": 20000000,
            "last_gold": 19000000,
        }
    }
    at_2300 = datetime(2026, 9, 6, 19, 30, tzinfo=timezone.utc)
    at_2330 = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)
    at_midnight = datetime(2026, 9, 6, 20, 30, tzinfo=timezone.utc)
    assert market_summary_day(state, at_2300, is_holiday=False) is None
    assert market_summary_day(state, at_2330, is_holiday=False) == "2026-09-06"
    assert market_summary_day(state, at_midnight, is_holiday=False) is None


def test_market_and_summary_are_blocked_on_holiday():
    from src.market_policy import market_summary_day, regular_market_allowed

    state = {
        "market_day_prices": {
            "date": "2026-09-06",
            "first_usd": 200000,
            "last_usd": 210000,
            "first_gold": 20000000,
            "last_gold": 19000000,
        }
    }
    at_10 = datetime(2026, 9, 6, 6, 30, tzinfo=timezone.utc)
    at_2330 = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)
    assert not regular_market_allowed(at_10, is_holiday=True)
    assert market_summary_day(state, at_2330, is_holiday=True) is None
