from src.newsroom_publisher import TelegramNewsroomPublisher
from src.newsroom_models import RawNewsItem, NormalizedNewsItem


def _item():
    raw = RawNewsItem(
        source='CENTCOM / X', source_url='https://x.com/CENTCOM/status/1', source_item_id='1',
        published_at='Wed, 09 Sep 2026 12:00:00 +0000', fetched_at='2026-09-09T12:01:00+00:00',
        title='Iran missile attack reported near the Strait of Hormuz', summary='', media=[]
    )
    return NormalizedNewsItem(raw=raw, actors=['iran'], locations=['hormuz'], actions=['attack'], objects=['missile'], numeric_facts=[], topic_tags=['war'], quoted_speaker='', normalized_text=raw.title.lower())


class Resp:
    def __init__(self, payload, status=200): self._payload=payload; self.status_code=status
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError('http')
    def json(self): return self._payload


class Session:
    def __init__(self): self.calls=[]
    def post(self, url, data=None, files=None, headers=None, timeout=None):
        self.calls.append((url, dict(data or {})))
        if len(self.calls) == 1:
            return Resp({'ok': False, 'description': "Bad Request: can't parse entities"})
        return Resp({'ok': True, 'result': {'message_id': 77}})


def test_publish_retries_plain_text_when_html_parse_fails():
    session=Session()
    pub=TelegramNewsroomPublisher('token','@chan',session=session,translator=lambda x: 'حمله موشکی ایران در نزدیکی تنگه هرمز')
    result=pub(_item())
    assert result['ok'] is True
    assert result['message_id']==77
    assert len(session.calls)==2
    assert 'parse_mode' not in session.calls[1][1]
