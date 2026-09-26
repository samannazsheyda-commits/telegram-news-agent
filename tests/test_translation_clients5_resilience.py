import requests

from src import services
from src import strict_translation


class _Resp:
    def __init__(self, payload=None, *, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


def test_clients5_parses_auto_detect_shape():
    class Session:
        def get(self, *args, **kwargs):
            return _Resp([["ایران یک موشک شلیک کرد", "en"]])

    assert (
        services._google_clients5_translate("Iran launched a missile", session=Session())
        == "ایران یک موشک شلیک کرد"
    )


def test_clients5_parses_flat_string_shape():
    class Session:
        def get(self, *args, **kwargs):
            return _Resp(["ایران یک موشک شلیک کرد"])

    assert (
        services._google_clients5_translate("Iran launched a missile", session=Session())
        == "ایران یک موشک شلیک کرد"
    )


def test_translate_to_fa_uses_clients5_when_gtx_is_rate_limited(monkeypatch):
    calls = []

    def rate_limited(text, session=requests):
        calls.append("gtx")
        raise requests.HTTPError("429")

    def clients5_ok(text, session=requests):
        calls.append("clients5")
        return "انفجار در نزدیکی نطنز گزارش شد"

    monkeypatch.setattr(services, "_google_translate", rate_limited)
    monkeypatch.setattr(services, "_google_mobile_translate", rate_limited)
    monkeypatch.setattr(services, "_google_clients5_translate", clients5_ok)

    result = services.translate_to_fa("Explosion reported near Natanz")
    assert result == "انفجار در نزدیکی نطنز گزارش شد"
    # clients5 is tried first, so the rate-limited gtx endpoints are never needed.
    assert calls[0] == "clients5"
    assert "gtx" not in calls


def test_strict_translation_uses_clients5_first(monkeypatch):
    order = []

    def clients5_ok(text, session=requests):
        order.append("clients5")
        return "ایران و اسرائیل به تبادل آتش پرداختند"

    def should_not_run(text, session=requests):
        order.append("other")
        raise AssertionError("later backend must not run when clients5 succeeds")

    monkeypatch.setattr(services, "_google_clients5_translate", clients5_ok)
    monkeypatch.setattr(services, "_google_translate", should_not_run)
    monkeypatch.setattr(services, "_google_mobile_translate", should_not_run)
    monkeypatch.setattr(services, "_mymemory_translate", should_not_run)

    result = strict_translation.translate_to_fa_strict(
        "Iran and Israel exchange fire", session=requests
    )
    assert result == "ایران و اسرائیل به تبادل آتش پرداختند"
    assert order == ["clients5"]


def test_mymemory_includes_email_when_configured(monkeypatch):
    captured = {}

    class Session:
        def get(self, url, params=None, headers=None, timeout=None):
            captured["params"] = params
            return _Resp({"responseData": {"translatedText": "متن فارسی"}})

    monkeypatch.setenv("MYMEMORY_EMAIL", "bikhabar@example.com")
    result = services._mymemory_translate("some english", session=Session())
    assert result == "متن فارسی"
    assert captured["params"].get("de") == "bikhabar@example.com"


def test_mymemory_omits_email_when_not_configured(monkeypatch):
    captured = {}

    class Session:
        def get(self, url, params=None, headers=None, timeout=None):
            captured["params"] = params
            return _Resp({"responseData": {"translatedText": "متن فارسی"}})

    monkeypatch.delenv("MYMEMORY_EMAIL", raising=False)
    services._mymemory_translate("some english", session=Session())
    assert "de" not in captured["params"]
