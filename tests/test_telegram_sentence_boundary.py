from src.custom_sources import parse_public_telegram_channel


def test_long_telegram_post_never_ends_with_cut_off_sentence():
    html = '''
    <div class="tgme_widget_message" data-post="ClashReport/9001">
      <div class="tgme_widget_message_text">John Bolton on Iran: I think, and have thought for decades, that the only way to achieve real lasting peace and security in the Middle East is to get rid of the regime in Tehran. I think the US and Israeli attacks are going to create a much longer sentence that should never be chopped in the middle when the Telegram card headline is shortened for publication.</div>
      <time datetime="2026-09-05T17:31:00+00:00"></time>
    </div>
    '''
    items = parse_public_telegram_channel(html, "ClashReport", "کلش ریپورت")
    assert len(items) == 1
    assert items[0].title.endswith("Tehran.")
    assert "I think the US and Israeli attacks" not in items[0].title
    assert not items[0].title.endswith("...")
