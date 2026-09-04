from src.services import has_persian, translate_to_fa


class FakeResponse:
    def __init__(self, payload=None, text="", ok=True):
        self._payload = payload
        self.text = text
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


class FallbackSession:
    def __init__(self):
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        if "googleapis" in url:
            raise RuntimeError("google down")
        return FakeResponse(payload={"responseData": {"translatedText": "ایران و تنگه هرمز"}})


def test_has_persian_detects_persian_text():
    assert has_persian("خبر درباره ایران")
    assert not has_persian("Iran news")


def test_translation_uses_fallback_and_returns_persian():
    session = FallbackSession()
    assert translate_to_fa("Iran and Hormuz", session=session) == "ایران و تنگه هرمز"
    assert session.calls == 2
