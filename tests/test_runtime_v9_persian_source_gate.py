from src.runtime_v9 import _format_persian_only, _persian_source_item, _visible_text
from src.sources import NewsItem


def _item(source: str) -> NewsItem:
    return NewsItem(
        "k",
        source,
        "Iran update",
        "",
        "https://x.com/example/status/123",
        "Sat, 05 Sep 2026 17:30:00 +0000",
    )


def test_al_jazeera_x_source_is_fully_persian():
    item = _persian_source_item(_item("Al Jazeera English / X"))
    assert item.source == "الجزیره انگلیسی / ایکس"


def test_mark_dubowitz_x_source_is_fully_persian():
    item = _persian_source_item(_item("Mark Dubowitz / X"))
    assert item.source == "مارک دوبوویتز / ایکس"


def test_unknown_latin_x_source_is_hidden_without_dropping_story():
    assert "x.com" not in _visible_text('<a href="https://x.com/a/status/1">لینک منبع خبر</a>')
    item = _persian_source_item(_item("Unknown Person / X"))
    assert item.source == "منبع در ایکس"
    message = _format_persian_only(_item("Unknown Person / X"), "یک خبر مهم درباره ایران", "")
    assert message
    assert "Unknown Person" not in _visible_text(message)
    assert "منبع در ایکس" in _visible_text(message)
