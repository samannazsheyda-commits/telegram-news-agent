from datetime import datetime, timezone


def test_corrected_native_car_post_is_forced_once_today():
    from src import runtime_v9 as v9

    now = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)
    state = {"car_last_sent_date": "2026-09-06"}

    due = getattr(v9, "_car_due_with_one_time_native_republish", None)
    assert callable(due), "native Telegram car republish hook must exist"
    assert due(state, now) is True
    assert state["car_native_republish_date"] == "2026-09-06"
    assert due(state, now) is False
