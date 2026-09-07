from datetime import datetime, timezone


HTML = '''
<div class="tgme_widget_message" data-post="bikhabaar/123">
  <div class="tgme_widget_message_text">🚗 قیمت روز خودرو | ۱۶ شهریور ۱۴۰۵</div>
  <time datetime="2026-09-07T08:14:00+00:00"></time>
</div>
'''


def test_channel_car_post_blocks_second_post_same_tehran_day():
    from src import runtime_v13 as v13

    now = datetime(2026, 9, 7, 8, 20, tzinfo=timezone.utc)
    assert v13.channel_has_car_post_today(HTML, now) is True


def test_channel_car_post_does_not_block_next_tehran_day():
    from src import runtime_v13 as v13

    now = datetime(2026, 9, 8, 8, 20, tzinfo=timezone.utc)
    assert v13.channel_has_car_post_today(HTML, now) is False
