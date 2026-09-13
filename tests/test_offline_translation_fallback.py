from src import strict_translation as strict_translation_module
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item
from src.strict_translation import StrictTelegramNewsroomPublisher


SOURCE = "An Iranian commercial vessel was struck off Qeshm Island, leaving one killed and three wounded."
GOOD_FA = "یک شناور تجاری ایرانی در نزدیکی جزیره قشم هدف قرار گرفت؛ یک نفر کشته و سه نفر زخمی شدند."
BAD_ARGOS_FA = "یک کشتی تجاری ایرانی در نزدیکی جزیره قشم به قتل رسید و یک نفر را کشت و سه نفر دیگر را زخمی کرد."
REPAIRED_ARGOS_FA = "یک کشتی تجاری ایرانی در نزدیکی جزیره قشم هدف قرار گرفت؛ یک نفر کشته و سه نفر دیگر زخمی شدند."


class ExplodingAI:
    available = True

    def translate_to_fa(self, source):
        raise AssertionError("optional translation must not depend on the remote AI when offline MT is available")

    def edit_persian(self, source, draft):
        raise AssertionError("optional translation must not depend on the remote AI when offline MT is available")


def test_optional_mode_prefers_offline_translator_before_remote_ai_or_network_when_explicitly_enabled():
    calls = []

    def offline(text):
        calls.append(("offline", text))
        return GOOD_FA

    def network(text):
        raise AssertionError("network translator must not run when explicitly enabled offline MT succeeds")

    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        ai=ExplodingAI(),
        ai_mode="optional",
        translator=network,
        offline_translator=offline,
        offline_translation_enabled=True,
    )

    assert publisher._translate_resilient(SOURCE) == GOOD_FA
    assert calls == [("offline", SOURCE)]


def test_optional_mode_falls_back_when_explicit_offline_translator_is_unavailable():
    calls = []

    def offline(text):
        calls.append("offline")
        return ""

    def network(text):
        calls.append("network")
        return GOOD_FA

    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        ai=None,
        ai_mode="optional",
        translator=network,
        offline_translator=offline,
        offline_translation_enabled=True,
    )

    assert publisher._translate_resilient(SOURCE) == GOOD_FA
    assert calls == ["offline", "network"]


def test_optional_mode_repairs_real_argos_role_reversal_when_offline_is_explicitly_enabled():
    calls = []

    def offline(text):
        calls.append("offline")
        return BAD_ARGOS_FA

    def network(text):
        raise AssertionError("network translator must not run when the source-anchored repair is safe")

    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        ai=None,
        ai_mode="optional",
        translator=network,
        offline_translator=offline,
        offline_translation_enabled=True,
    )

    assert publisher._translate_resilient(SOURCE) == REPAIRED_ARGOS_FA
    assert calls == ["offline"]


def test_default_optional_path_does_not_enter_offline_translator_before_network():
    offline_calls = []

    def blocking_offline(text):
        offline_calls.append(text)
        raise RuntimeError("simulated_blocking_local_model")

    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        ai=None,
        ai_mode="optional",
        translator=lambda text: GOOD_FA,
        offline_translator=blocking_offline,
    )

    assert publisher._translate_resilient(SOURCE) == GOOD_FA
    assert offline_calls == []


def test_optional_mode_keeps_vetted_headline_when_summary_translation_is_unavailable(monkeypatch):
    summary = "Officials said more details would be released later."

    def offline(text):
        return GOOD_FA if text == SOURCE else ""

    monkeypatch.setattr(strict_translation_module.newsroom_publisher_module, "_lingva_translate", lambda *a, **k: "")
    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        ai=None,
        ai_mode="optional",
        translator=lambda text: "",
        offline_translator=offline,
        offline_translation_enabled=True,
    )
    item = normalize_item(RawNewsItem(
        source="Al Jazeera English / X",
        source_url="https://x.com/AJEnglish/status/1",
        source_item_id="1",
        published_at="2026-09-13T05:00:00+00:00",
        fetched_at="2026-09-13T05:01:00+00:00",
        title=SOURCE,
        summary=summary,
        media=[],
        source_priority="protected",
    ))

    message = publisher._message(item)

    assert GOOD_FA in message
    assert summary not in message


def test_optional_offline_translation_normalizes_dotted_us_abbreviation_before_entity_guard():
    source = "Iranian officials say a peace agreement with the U.S. was sabotaged."
    offline_fa = "مقام‌های ایرانی می‌گویند توافق صلح با U.S. خرابکاری شد."

    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        ai=None,
        ai_mode="optional",
        translator=lambda text: "",
        offline_translator=lambda text: offline_fa,
        offline_translation_enabled=True,
    )

    result = publisher._translate_resilient(source)

    assert "آمریکا" in result
    assert "U.S." not in result
