from src import services
from src.newsroom_publisher import TelegramNewsroomPublisher


AP_TITLE = "Saudi airstrikes hit rebel-held Mokha airport in Yemen, Houthi broadcaster says"
BAD_TITLE_FA = (
    "یکی از شبکه‌های تلویزیونی حوثی می‌گوید که حملات هوایی عربستان سعودی "
    "به فرودگاه موخا در یمن که تحت کنترل شورشیان است، زده است."
)

AP_SUMMARY = (
    "The strikes come a day after the Iran-backed Houthis entered the key Red Sea port city, "
    "bringing them closer to the strategic Bab el-Mandeb Strait."
)
BAD_SUMMARY_FA = (
    "این حملات یک روز پس از ورود حوثی‌های تحت حمایت ایران به شهر بندری مهم در دریای سرخ "
    "صورت می‌گیرد و آنها را به تنگه استراتژیک باب المندب نزدیک‌تر می‌کند."
)


def test_source_aware_editor_repairs_airstrikes_hit_newsroom_grammar():
    repaired = services._repair_news_idioms(AP_TITLE, BAD_TITLE_FA)
    assert "زده است" not in repaired
    assert "هدف حملات هوایی" in repaired
    assert "فرودگاه المخا" in repaired
    assert "شبکه تلویزیونی" in repaired


def test_source_aware_editor_repairs_bab_el_mandeb_and_headline_tense():
    repaired = services._repair_news_idioms(AP_SUMMARY, BAD_SUMMARY_FA)
    assert "صورت می‌گیرد" not in repaired
    assert "انجام شده است" in repaired
    assert "باب‌المندب" in repaired


def test_quality_gate_rejects_unrepaired_airstrike_hit_machine_persian():
    assert services.translation_is_publishable(AP_TITLE, BAD_TITLE_FA) is False


def test_publisher_runs_editorial_repair_on_custom_or_fallback_translator_output():
    publisher = TelegramNewsroomPublisher(
        "token",
        "chat",
        translator=lambda _text: BAD_TITLE_FA,
    )
    translated = publisher._translate_resilient(AP_TITLE)
    assert translated
    assert "زده است" not in translated
    assert "هدف حملات هوایی" in translated
    assert "فرودگاه المخا" in translated
