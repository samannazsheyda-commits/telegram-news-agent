from src.strict_translation import StrictTelegramNewsroomPublisher


def test_offline_translation_repairs_irgc_navy_actor_before_entity_guard():
    source = "Iran's IRGC Navy launched an anti-ship cruise missile from Sirik towards the Strait of Hormuz."
    lossy_offline = "نیروی دریایی ایران یک موشک کروز ضد کشتی از سیریک به سمت تنگه هرمز پرتاب کرد."

    publisher = StrictTelegramNewsroomPublisher(
        "token",
        "@bikhabaar",
        offline_translator=lambda text: lossy_offline,
        offline_translation_enabled=True,
        ai=None,
        ai_mode="optional",
        translator=lambda text: "",
    )

    translated = publisher._translate_resilient(source)

    assert "سپاه" in translated
    assert "نیروی دریایی" in translated
    assert "تنگه هرمز" in translated
