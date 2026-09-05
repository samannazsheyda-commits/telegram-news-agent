from src.sources import NewsItem
import src.runtime as base
import src.runtime_v2 as runtime_v2


def _x(key: str, title: str) -> NewsItem:
    return NewsItem(key, "Reuters / X", title, "", f"https://x.com/Reuters/status/{key}", "Fri, 05 Sep 2026 07:00:00 GMT")


def test_all_distinct_iran_related_x_posts_survive_editorial_prefilters(monkeypatch):
    first = _x("1", "Iran sanctions update")
    second = _x("2", "Iran sanctions update with another post")

    monkeypatch.setattr(base, "_original_fetch_news_items", lambda: [first, second])
    monkeypatch.setattr(base, "fetch_custom_news_items", lambda: [])
    monkeypatch.setattr(base, "fetch_priority_news_items", lambda: [])
    monkeypatch.setattr(base, "_terminal_manual_keys", lambda: set())
    monkeypatch.setattr(base, "is_low_value_company_news", lambda item: True)
    monkeypatch.setattr(base, "_recent_published_items", lambda: [first])
    monkeypatch.setattr(base, "_is_recent_duplicate", lambda item, refs: True)

    runtime_v2._install_x_publish_all_policy()
    items = base._combined_fetch_news_items()

    assert [item.key for item in items] == ["1", "2"]
