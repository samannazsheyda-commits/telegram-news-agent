from datetime import datetime, timezone


def test_fresh_car_instant_view_is_forced_once_today():
    from src import runtime_v9 as v9

    now = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)
    state = {"car_last_sent_date": "2026-09-06", "car_native_republish_date": "2026-09-06"}

    due = getattr(v9, "_car_due_with_one_time_instant_republish", None)
    assert callable(due)
    assert due(state, now) is True
    assert state["car_instant_republish_fresh_2_date"] == "2026-09-06"
    assert due(state, now) is False
