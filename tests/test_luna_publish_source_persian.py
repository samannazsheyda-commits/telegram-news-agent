from panel.luna_publish import _machine_persian_copy


def test_machine_copy_accepts_native_persian_source_without_persisted_translation():
    row = {
        "original_title": "ایران برای آغاز هر مذاکره‌ای شرط روشن دارد",
        "original_summary": "این متن فارسی از خود منبع دریافت شده است.",
    }

    assert _machine_persian_copy(row) == (
        "ایران برای آغاز هر مذاکره‌ای شرط روشن دارد",
        "این متن فارسی از خود منبع دریافت شده است.",
    )


def test_machine_copy_never_falls_back_to_raw_english_source():
    row = {
        "original_title": "Iran sets conditions for talks",
        "original_summary": "This raw source copy has not been translated.",
    }

    assert _machine_persian_copy(row) == ("", "")
