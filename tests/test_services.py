from src.services import has_persian, send_telegram, translate_to_fa


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


class TelegramSession:
    def __init__(self):
        self.payloads = []

    def post(self, url, **kwargs):
        self.payloads.append(kwargs["json"])
        return FakeResponse(payload={"ok": True})


def test_has_persian_detects_persian_text():
    assert has_persian("خبر درباره ایران")
    assert not has_persian("Iran news")


def test_translation_uses_fallback_and_returns_persian():
    session = FallbackSession()
    assert translate_to_fa("Iran and Hormuz", session=session) == "ایران و تنگه هرمز"
    assert session.calls == 2


def test_translation_repairs_small_potatoes_idiom_in_news_context():
    class Session:
        @staticmethod
        def get(url, **kwargs):
            return FakeResponse(payload=[[['ترامپ می‌گوید درگیری ایران «سیب‌زمینی‌های کوچک» است', None, None, None]]])

    text = translate_to_fa('Trump says Iran conflict is "small potatoes"', session=Session)
    assert "سیب‌زمینی" not in text
    assert "کم‌اهمیت" in text


def test_translation_repairs_high_risk_journalistic_idioms_without_literal_nonsense():
    cases = [
        ('All options are on the table', 'همه گزینه‌ها روی میز هستند', 'همه گزینه‌ها مطرح‌اند'),
        ('The administration doubled down on its Iran policy', 'دولت روی سیاست ایران دو برابر شد', 'دولت بر سیاست خود درباره ایران پافشاری کرد'),
        ('The president walked back his earlier remarks', 'رئیس‌جمهور اظهارات قبلی خود را راه رفت', 'رئیس‌جمهور از اظهارات قبلی خود عقب‌نشینی کرد'),
        ('The ball is now in Iran\'s court', 'توپ اکنون در زمین ایران است', 'اکنون نوبت تصمیم‌گیری ایران است'),
    ]

    for source, bad_translation, expected in cases:
        class Session:
            @staticmethod
            def get(url, **kwargs):
                return FakeResponse(payload=[[[bad_translation, None, None, None]]])
        text = translate_to_fa(source, session=Session)
        assert text == expected


def test_telegram_messages_disable_link_preview():
    session = TelegramSession()
    send_telegram('📌 <a href="https://news.google.com/example">لینک خبر</a>', "token", "chat", session=session)
    assert session.payloads[0]["disable_web_page_preview"] is True
