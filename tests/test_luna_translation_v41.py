from __future__ import annotations

import json

from panel.luna_translation import LunaTranslationService


class FakeClient:
    fast_model = "fast"
    complex_model = "complex"

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def create_response(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        return {"id": "r", "output_text": json.dumps(payload, ensure_ascii=False), "usage": {}}

    @staticmethod
    def output_text(response):
        return response["output_text"]


def _good():
    return {
        "title_fa": "ایران از بسته اقتصادی ۲۵ میلیارد دلاری رونمایی کرد",
        "body_fa": "مقام‌ها گفتند این بسته ۲۵ میلیارد دلار ارزش دارد و اجرای آن از ۲۰۲۷ آغاز می‌شود.",
        "source_language": "en",
        "quality_notes": "",
    }


def test_good_translation_passes_without_repair():
    client = FakeClient([_good()])
    service = LunaTranslationService(client)

    result = service.translate(
        "Iran unveils $25 billion economic package",
        "Officials said the package is worth $25 billion and implementation starts in 2027.",
    )

    assert result["quality_passed"] is True
    assert result["title_fa"].startswith("ایران")
    assert len(client.calls) == 1


def test_missing_critical_number_triggers_repair():
    broken = {
        "title_fa": "ایران از بسته اقتصادی رونمایی کرد",
        "body_fa": "مقام‌ها گفتند اجرای این بسته به‌زودی آغاز می‌شود.",
        "source_language": "en",
        "quality_notes": "",
    }
    client = FakeClient([broken, _good()])
    service = LunaTranslationService(client)

    result = service.translate(
        "Iran unveils $25 billion economic package",
        "Officials said the package is worth $25 billion and implementation starts in 2027.",
    )

    assert result["quality_passed"] is True
    assert result["repaired"] is True
    assert len(client.calls) == 2
    assert client.calls[1]["model"] == "complex"


def test_failed_repair_never_becomes_publishable_copy():
    broken = {
        "title_fa": "یک بسته اقتصادی معرفی شد",
        "body_fa": "جزئیات بیشتری منتشر نشده است.",
        "source_language": "en",
        "quality_notes": "",
    }
    client = FakeClient([broken, broken])
    service = LunaTranslationService(client)

    result = service.translate(
        "Iran unveils $25 billion economic package",
        "Officials said the package is worth $25 billion and implementation starts in 2027.",
    )

    assert result["quality_passed"] is False
    assert result["title_fa"] == ""
    assert result["body_fa"] == ""
    assert result["quality_notes"]
