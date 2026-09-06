import src.runtime_v2 as v2
from src.sources import NewsItem


def _item(key, source):
    return NewsItem(
        key,
        source,
        f"Iran security update {key}",
        "",
        f"https://example.com/{key}",
        "Sun, 06 Sep 2026 11:00:00 GMT",
    )


def test_x_failure_keeps_mainstream_web_fallback(monkeypatch):
    web = _item("reuters-web", "Reuters")
    monkeypatch.setattr(v2, "fetch_builtin_x_news_items", lambda: (_ for _ in ()).throw(RuntimeError("x outage")))
    monkeypatch.setattr(v2, "_original_generic_fetch", lambda: [web])

    items = v2._x_first_fetch_news_items()

    assert [item.key for item in items] == [web.key]


def test_x_primary_and_web_fallback_are_merged(monkeypatch):
    x = _item("x-post", "Reuters / X")
    web = _item("web-post", "Associated Press")
    monkeypatch.setattr(v2, "fetch_builtin_x_news_items", lambda: [x])
    monkeypatch.setattr(v2, "_original_generic_fetch", lambda: [web])

    items = v2._x_first_fetch_news_items()

    assert {item.key for item in items} == {x.key, web.key}


def test_google_indexed_x_rows_are_not_reintroduced_by_web_fallback(monkeypatch):
    fresh = _item("fresh-x", "Reuters / X")
    stale_google_x = _item("google-x", "Barak Ravid / X")
    web = _item("bbc-web", "BBC News")
    monkeypatch.setattr(v2, "fetch_builtin_x_news_items", lambda: [fresh])
    monkeypatch.setattr(v2, "_original_generic_fetch", lambda: [stale_google_x, web])

    items = v2._x_first_fetch_news_items()

    assert {item.key for item in items} == {fresh.key, web.key}
