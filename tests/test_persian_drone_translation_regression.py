from src import strict_translation


SOURCE = (
    "Tehran requested Russia to provide a new generation of armed drones earlier this year "
    "during the Israel-US war with Iran, the Financial Times reported Sunday."
)
BAD_FA = (
    "تهران درخواست کرد که روسیه نسل جدید هواپیماهای بدون سرنشین دار را در اوایل سال جاری "
    "در جریان جنگ اسرائیل و آمریکا با ایران، روزنامه فایننشال تایمز روز یکشنبه گزارش داد."
)


def test_guarded_copy_repairs_malformed_drone_phrase_and_request_word_order():
    repaired = strict_translation._natural_persian_copy(SOURCE, BAD_FA)

    assert repaired
    assert "هواپیماهای بدون سرنشین دار" not in repaired
    assert "تهران از روسیه خواست" in repaired
    assert "پهپادهای مسلح" in repaired


def test_guarded_copy_rejects_unrepairable_malformed_unmanned_phrase():
    source = "Tehran discussed aviation technology with Russia."
    bad = "تهران درباره هواپیماهای بدون سرنشین دار با روسیه گفت‌وگو کرد."

    assert strict_translation._natural_persian_copy(source, bad) == ""
