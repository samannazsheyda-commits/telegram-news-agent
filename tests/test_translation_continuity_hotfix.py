from src import services
from src.newsroom_models import NormalizedNewsItem, RawNewsItem
from src.newsroom_publisher import TelegramNewsroomPublisher


def test_google_mobile_fallback_can_return_persian(monkeypatch):
    class Resp:
        text = '<div class="result-container">ایران یک موشک شلیک کرد</div>'
        def raise_for_status(self):
            return None
    class Session:
        def get(self, *args, **kwargs):
            return Resp()
    assert services._google_mobile_translate('Iran launched a missile', session=Session()) == 'ایران یک موشک شلیک کرد'


def test_urgent_item_falls_back_to_source_text_when_translation_unavailable():
    raw = RawNewsItem(
        source='Test / X', source_url='https://x.com/test/status/1', source_item_id='1',
        published_at='Wed, 09 Sep 2026 12:00:00 +0000', fetched_at='2026-09-09T12:00:00+00:00',
        title='Iran launched ballistic missiles toward Israel', summary='', media=[], source_priority='protected'
    )
    item = NormalizedNewsItem(raw=raw, normalized_title=raw.title, normalized_summary='', language='en')
    publisher = TelegramNewsroomPublisher('x', '@x', translator=lambda _text: '')
    message = publisher._message(item)
    assert 'Iran launched ballistic missiles toward Israel' in message
