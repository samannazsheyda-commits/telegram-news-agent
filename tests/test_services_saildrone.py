from src import services


def test_saildrone_explorer_is_never_translated_as_aircraft(monkeypatch):
    source = "IRGC Navy says it attacked a U.S. Saildrone Explorer maritime reconnaissance unmanned surface vessel at the entrance to the Strait of Hormuz"

    def bad_google(text, session=None):
        return "نیروی دریایی سپاه از حمله به یک فروند هواپیمای شناسایی دریایی Saildrone Explorer آمریکایی در ورودی تنگه هرمز خبر داد"

    monkeypatch.setattr(services, "_google_translate", bad_google)
    result = services.translate_to_fa(source)

    assert "هواپیما" not in result
    assert "شناور سطحی بدون سرنشین" in result
    assert "سیل‌درون اکسپلورر" in result
