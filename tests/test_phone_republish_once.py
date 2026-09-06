from datetime import datetime
from zoneinfo import ZoneInfo

import src.runtime_v10 as runtime_v10


TEHRAN = ZoneInfo("Asia/Tehran")


def test_today_phone_card_can_be_forced_once_even_if_old_card_already_sent():
    due = getattr(runtime_v10, "_phone_flagships_due_with_one_time_republish", None)
    assert callable(due), "runtime must expose a controlled one-time phone republish gate"

    now = datetime(2026, 9, 6, 16, 30, tzinfo=TEHRAN)
    state = {"phone_flagships_last_sent_date": "2026-09-06"}

    assert due(state, now) is True

    state["phone_flagships_republish_40_date"] = "2026-09-06"
    assert due(state, now) is False
