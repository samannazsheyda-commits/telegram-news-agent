from src.services import translate_to_fa


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _session_for(bad_translation):
    class Session:
        @staticmethod
        def get(url, **kwargs):
            return FakeResponse([[[bad_translation, None, None, None]]])

    return Session


def test_doubled_down_repair_preserves_the_real_subject():
    source = "Iran's foreign minister doubled down on his position"
    bad = "وزیر خارجه ایران روی موضع خود دو برابر شد"
    text = translate_to_fa(source, session=_session_for(bad))
    assert "وزیر خارجه ایران" in text
    assert "دولت" not in text
    assert "دو برابر" not in text
    assert "پافشاری" in text


def test_walked_back_repair_does_not_duplicate_the_object_phrase():
    source = "The minister walked back his earlier comments"
    bad = "وزیر اظهارات قبلی خود را راه رفت"
    text = translate_to_fa(source, session=_session_for(bad))
    assert text.count("اظهارات قبلی خود") == 1
    assert "راه رفت" not in text
    assert "عقب‌نشینی" in text
