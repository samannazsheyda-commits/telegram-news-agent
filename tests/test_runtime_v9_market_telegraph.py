def test_free_market_usd_parser_uses_explicit_current_rate():
    from src import runtime_v9 as v9

    text = "دلار USD نرخ فعلی:: 2,272,050 2.78 ارز آزاد"
    assert v9._free_market_usd_rial_from_text(text) == 2_272_050


def test_telegraph_messages_enable_preview_but_normal_news_stays_disabled():
    from src import runtime_v9 as v9

    assert v9._disable_preview_for_text('مشاهده لیست https://telegra.ph/car-prices-test') is False
    assert v9._disable_preview_for_text('خبر عادی https://example.com/story') is True
