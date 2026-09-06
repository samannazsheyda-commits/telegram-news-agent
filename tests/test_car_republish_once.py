from datetime import datetime, timezone


def test_corrected_car_telegraph_is_forced_once_today():
    from src import runtime_v9 as v9

    now = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)
    state = {"car_last_sent_date": "2026-09-06"}

    assert v9._car_due_with_one_time_telegraph_republish(state, now) is True
    assert state["car_telegraph_republish_date"] == "2026-09-06"
    assert v9._car_due_with_one_time_telegraph_republish(state, now) is False
