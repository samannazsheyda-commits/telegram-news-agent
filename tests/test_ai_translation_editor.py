from types import SimpleNamespace

from src import newsroom_publisher, strict_translation
from src.ai_newsroom import AIServiceError, PersianEditDecision, TranslationDraft
from src.newsroom_models import RawNewsItem
from src.newsroom_normalize import normalize_item
from src.strict_translation import StrictTelegramNewsroomPublisher


SOURCE = "Saudi airstrikes hit Mokha airport in Yemen after the Iran-backed Houthi advance."
BAD_FA = "حملات هوایی عربستان سعودی به فرودگاه موخا در یمن زده است و پس از پیشروی حوثی‌های مورد حمایت ایران انجام شد."
GOOD_FA = "عربستان سعودی فرودگاه المخا در یمن را هدف حملات هوایی قرار داده است؛ این حملات پس از پیشروی حوثی‌های مورد حمایت ایران انجام شد."


class FakeAI:
    available = True

    def __init__(self, *, draft=BAD_FA, edited=GOOD_FA, faithful=True, natural=True, fail=False):
        self.config = SimpleNamespace(mode="required")
        self.draft = draft
        self.edited = edited
        self.faithful = faithful
        self.natural = natural
        self.fail = fail
        self.calls = []

    def translate_to_fa(self, source):
        self.calls.append(("translate", source))
        if self.fail:
            raise AIServiceError("translator_down")
        return TranslationDraft(text=self.draft, backend="madlad", faithful=True)

    def edit_persian(self, source, draft):
        self.calls.append(("edit", source, draft))
        if self.fail:
            raise AIServiceError("editor_down")
        return PersianEditDecision(
            text=self.edited,
            faithful=self.faithful,
            natural=self.natural,
            reason="",
        )


class NoNetworkSession:
    def __init__(self):
        self.posts = []

    def post(self, *args, **kwargs):
        self.posts.append((args, kwargs))
        raise AssertionError("Telegram must not be called when copy validation fails")

    def get(self, *args, **kwargs):
        raise AssertionError("network fallback must not run in required AI mode")


def _item(title=SOURCE):
    return normalize_item(
        RawNewsItem(
            source="Associated Press / X",
            source_url="https://x.com/AP/status/123",
            source_item_id="123",
            published_at="2026-09-11T09:30:00+00:00",
            fetched_at="2026-09-11T09:31:00+00:00",
            title=title,
            summary="",
            source_priority="protected",
        )
    )


def test_required_ai_translation_runs_translator_then_source_aware_editor():
    ai = FakeAI()
    publisher = StrictTelegramNewsroomPublisher("token", "@bikhabaar", ai=ai, ai_mode="required")
    translated = publisher._translate_resilient(SOURCE)
    assert translated == GOOD_FA
    assert ai.calls[0] == ("translate", SOURCE)
    assert ai.calls[1] == ("edit", SOURCE, BAD_FA)
    assert "زده است" not in translated
    assert "هدف حملات هوایی" in translated


def test_editor_output_with_mechanical_hit_translation_is_rejected():
    ai = FakeAI(edited=BAD_FA, faithful=True, natural=True)
    publisher = StrictTelegramNewsroomPublisher("token", "@bikhabaar", ai=ai, ai_mode="required")
    assert publisher._translate_resilient(SOURCE) == ""


def test_editor_must_mark_copy_faithful_and_natural():
    ai = FakeAI(faithful=False, natural=True)
    publisher = StrictTelegramNewsroomPublisher("token", "@bikhabaar", ai=ai, ai_mode="required")
    assert publisher._translate_resilient(SOURCE) == ""

    ai = FakeAI(faithful=True, natural=False)
    publisher = StrictTelegramNewsroomPublisher("token", "@bikhabaar", ai=ai, ai_mode="required")
    assert publisher._translate_resilient(SOURCE) == ""


def test_ai_editor_cannot_drop_or_change_numeric_fact():
    source = "Iran launched 12 ballistic missiles toward Israel."
    changed = "ایران ۱۰ موشک بالستیک به سمت اسرائیل شلیک کرد."
    ai = FakeAI(draft=changed, edited=changed)
    publisher = StrictTelegramNewsroomPublisher("token", "@bikhabaar", ai=ai, ai_mode="required")
    assert publisher._translate_resilient(source) == ""


def test_ai_editor_cannot_drop_core_attack_meaning():
    source = "Iran launched ballistic missiles toward Israel."
    changed = "ایران درباره تحولات منطقه بیانیه‌ای منتشر کرد."
    ai = FakeAI(draft=changed, edited=changed)
    publisher = StrictTelegramNewsroomPublisher("token", "@bikhabaar", ai=ai, ai_mode="required")
    assert publisher._translate_resilient(source) == ""


def test_ai_editor_cannot_replace_key_actor_or_country():
    changed = "آمریکا فرودگاه المخا در یمن را هدف حملات هوایی قرار داده است؛ این حملات پس از پیشروی حوثی‌های مورد حمایت ایران انجام شد."
    ai = FakeAI(draft=changed, edited=changed, faithful=True, natural=True)
    publisher = StrictTelegramNewsroomPublisher("token", "@bikhabaar", ai=ai, ai_mode="required")
    assert publisher._translate_resilient(SOURCE) == ""


def test_ai_failure_in_required_mode_never_calls_telegram():
    session = NoNetworkSession()
    ai = FakeAI(fail=True)
    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=session,
        ai=ai,
        ai_mode="required",
    )
    result = publisher(_item())
    assert result["ok"] is False
    assert session.posts == []


def test_strict_translation_falls_back_to_guarded_mymemory_when_google_is_down(monkeypatch):
    calls = []

    def fail_google(text, session=None):
        calls.append("google")
        raise RuntimeError("google_down")

    def fail_mobile(text, session=None):
        calls.append("mobile")
        raise RuntimeError("mobile_down")

    def good_mymemory(text, session=None):
        calls.append("mymemory")
        return GOOD_FA

    monkeypatch.setattr(strict_translation.services, "_google_translate", fail_google)
    monkeypatch.setattr(strict_translation.services, "_google_mobile_translate", fail_mobile)
    monkeypatch.setattr(strict_translation.services, "_mymemory_translate", good_mymemory)

    translated = strict_translation.translate_to_fa_strict(SOURCE, session=object())
    assert translated == GOOD_FA
    assert calls == ["google", "mobile", "mymemory"]


def test_optional_mode_uses_guarded_lingva_when_strict_backends_fail(monkeypatch):
    monkeypatch.setattr(newsroom_publisher, "_lingva_translate", lambda text, session=None: GOOD_FA)
    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        session=object(),
        translator=lambda text: "",
        ai=None,
        ai_mode="optional",
    )

    assert publisher._translate_resilient(SOURCE) == GOOD_FA


def test_guarded_copy_persianizes_known_residual_terms_from_clashreport_fallback():
    source = (
        "Vice President JD Vance privately sought direct assessments about the Iran war. "
        "Commanders warned that U.S. Patriot interceptors were being depleted. Source: NYT"
    )
    translated = (
        "معاون رئیس‌جمهور JD Vance به‌طور خصوصی درباره جنگ ایران ارزیابی مستقیم خواست. "
        "فرماندهان هشدار دادند که رهگیرهای Patriot آمریکا در حال کاهش است. منبع: NYT"
    )
    expected = (
        "معاون رئیس‌جمهور جی‌دی ونس به‌طور خصوصی درباره جنگ ایران ارزیابی مستقیم خواست. "
        "فرماندهان هشدار دادند که رهگیرهای پاتریوت آمریکا در حال کاهش است. منبع: نیویورک تایمز"
    )

    assert strict_translation._natural_persian_copy(source, translated) == expected
