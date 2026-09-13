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


def test_optional_mode_prefers_offline_translator_before_remote_ai_or_network():
    calls = []

    def offline(text):
        calls.append(("offline", text))
        return GOOD_FA

    def network(text):
        raise AssertionError("network translator must not run when offline MT succeeds")

    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        ai=ExplodingAI(),
        ai_mode="optional",
        translator=network,
        offline_translator=offline,
    )

    assert publisher._translate_resilient(SOURCE) == GOOD_FA
    assert calls == [("offline", SOURCE)]


def test_optional_mode_falls_back_when_offline_translator_is_unavailable():
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
    )

    assert publisher._translate_resilient(SOURCE) == GOOD_FA
    assert calls == ["offline", "network"]


def test_optional_mode_repairs_real_argos_role_reversal_without_network():
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
    )

    assert publisher._translate_resilient(SOURCE) == REPAIRED_ARGOS_FA
    assert calls == ["offline"]
