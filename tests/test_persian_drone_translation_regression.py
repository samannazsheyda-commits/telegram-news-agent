from src import services


SOURCE = (
    "Tehran requested Russia to provide a new generation of armed drones earlier this year "
    "during the Israel-US war with Iran, the Financial Times reported Sunday."
)
BAD_FA = (
    "تهران درخواست کرد که روسیه نسل جدید هواپیماهای بدون سرنشین دار را در اوایل سال جاری "
    "در جریان جنگ اسرائیل و آمریکا با ایران، روزنامه فایننشال تایمز روز یکشنبه گزارش داد."
)


def test_repairs_malformed_drone_phrase_and_request_word_order():
    repaired = services._repair_news_idioms(SOURCE, BAD_FA)

    assert "هواپیماهای بدون سرنشین دار" not in repaired
    assert "تهران از روسیه خواست" in repaired
    assert "پهپادهای مسلح" in repaired
    assert services.translation_is_publishable(SOURCE, repaired) is True


def test_unrepaired_malformed_drone_phrase_is_not_publishable():
    assert services.translation_is_publishable(SOURCE, BAD_FA) is False
