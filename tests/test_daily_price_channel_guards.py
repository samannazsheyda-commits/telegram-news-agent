from datetime import datetime, timezone

from src import runtime_v13


HTML = '''
<div class="tgme_widget_message" data-post="bikhabaar/1">
  <div class="tgme_widget_message_text">📱 قیمت روز موبایل | امروز</div>
  <time datetime="2026-09-07T07:15:00+00:00"></time>
</div>
<div class="tgme_widget_message" data-post="bikhabaar/2">
  <div class="tgme_widget_message_text">🚘 قیمت روز خودرو | بازار ایران</div>
  <time datetime="2026-09-07T07:20:00+00:00"></time>
</div>
'''


class Response:
    text = HTML
    def raise_for_status(self):
        return None


class Session:
    def get(self, *args, **kwargs):
        return Response()


def test_channel_guard_detects_phone_and_car_posts_for_same_tehran_day():
    now = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
    assert runtime_v13.channel_has_daily_price_post(HTML, now, "phone") is True
    assert runtime_v13.channel_has_daily_price_post(HTML, now, "car") is True


def test_phone_daily_guard_repairs_stale_state_and_suppresses_second_post(monkeypatch):
    now = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
    state = {"phone_flagships_last_sent_date": "2026-09-06"}
    saved = []
    monkeypatch.setattr(runtime_v13.base.agent, "save_state", lambda value, path: saved.append(dict(value)))

    due = runtime_v13._phone_due_once_per_day(state, now, session=Session())

    assert due is False
    assert state["phone_flagships_last_sent_date"] == "2026-09-07"
    assert saved[-1]["phone_flagships_last_sent_date"] == "2026-09-07"
