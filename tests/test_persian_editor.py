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


def test_known_latin_acronyms_are_persianized():
    assert edit_news_text("CENTCOM says Iran launched 2 missiles.", "CENTCOM اعلام کرد ایران ۲ موشک شلیک کرده است.") == "سنتکام اعلام کرد ایران ۲ موشک شلیک کرده است."


def test_source_owned_proper_names_do_not_kill_safe_persian_fallback():
    source = (
        "An Iranian commercial vessel was struck near Hengam Island and the Shib Deraz coast of Qeshm Island, "
        "killing one person and wounding three others, said Qeshm Governor Amir Teymouri."
    )
    translated = (
        "یک شناور تجاری ایرانی نزدیک Hengam Island و ساحل Shib Deraz جزیره قشم هدف قرار گرفت؛ "
        "یک نفر کشته و سه نفر زخمی شدند، Amir Teymouri فرماندار قشم گفت."
    )
    edited = edit_news_text(source, translated)
    assert edited == translated


def test_hallucinated_latin_not_present_in_source_is_still_rejected():
    source = "Iran said the situation changed."
    translated = "ایران گفت FooBar وضعیت را تغییر داده است."
    assert has_forbidden_latin_body(translated, source)
    assert edit_news_text(source, translated) == ""
