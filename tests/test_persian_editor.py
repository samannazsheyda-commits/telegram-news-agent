from src.persian_editor import (
    edit_news_text,
    has_forbidden_latin_body,
    is_promotional_news_text,
    strip_leading_decorative_emoji,
    trim_to_complete_sentences,
)


def test_ft_event_promo_is_not_news():
    text = "Catch their FT Weekend Festival session about Iran and the US military."
    assert is_promotional_news_text(text)
    assert edit_news_text(text, "جلسه جشنواره فایننشال تایمز درباره ایران را تماشا کنید.") == ""


def test_leading_source_emojis_are_removed():
    assert strip_leading_decorative_emoji("🇺🇸 ❌ 🇮🇷 - 5 tankers near Hormuz") == "5 tankers near Hormuz"


def test_long_text_is_cut_only_on_complete_sentence():
    text = "جمله اول کامل است. جمله دوم کامل است. جمله سوم ناقص می‌ماند چون خیلی طولانی است"
    result = trim_to_complete_sentences(text, max_chars=38)
    assert result.endswith(".")
    assert "ناقص" not in result


def test_literal_hormuz_translation_is_repaired():
    source = "5 tankers above the Strait of Hormuz. 3 from Qatar, 2 from Israel."
    translated = "۵ نفتکش بالای تنگه هرمز. ۳ فروند از قطر، ۲ فروند از اسرائیل."
    edited = edit_news_text(source, translated)
    assert "بالای تنگه هرمز" not in edited
    assert "در محدوده تنگه هرمز" in edited


def test_known_latin_acronyms_are_persianized_but_unknown_latin_is_rejected():
    assert edit_news_text("CENTCOM says Iran launched 2 missiles.", "CENTCOM اعلام کرد ایران ۲ موشک شلیک کرده است.") == "سنتکام اعلام کرد ایران ۲ موشک شلیک کرده است."
    assert has_forbidden_latin_body("ایران درباره FooBar توضیح داد.")
    assert edit_news_text("Iran said FooBar changed.", "ایران گفت FooBar تغییر کرده است.") == ""
