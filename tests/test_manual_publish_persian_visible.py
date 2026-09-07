import re

from src.editorial_store import ReviewItem
from src.manual_publish import _clean_source, _message_for


def _item(source: str, url: str = "https://example.com/story") -> ReviewItem:
    return ReviewItem.for_news(
        news_key="story-key",
        source=source,
        source_url=url,
        original_title="English original title",
        original_summary="English original summary",
        persian_title="تیتر فارسی",
        published_at_source="Mon, 07 Sep 2026 09:42:00 GMT",
    )


def _visible_text(html: str) -> str:
    without_href = re.sub(r'href="[^"]+"', 'href=""', html)
    return re.sub(r"<[^>]+>", "", without_href)


def test_times_of_israel_is_localized():
    assert _clean_source("Times of Israel") == "تایمز اسرائیل"


def test_unknown_latin_source_never_leaks_into_visible_source_label():
    assert _clean_source("Some Unknown Outlet") == "منبع خبری"


def test_manual_message_hides_raw_source_url_behind_persian_label():
    url = "https://news.example.com/abc?q=1"
    message = _message_for(_item("Times of Israel", url), "ایران به کره جنوبی هشدار داد", "")

    visible = _visible_text(message)
    assert "تایمز اسرائیل:" in visible
    assert "Times of Israel" not in visible
    assert "https://" not in visible
    assert "لینک منبع خبر" in visible
    assert f'href="{url}"' in message
