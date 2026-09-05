import json

from src.newsroom_x import (
    fetch_builtin_x_news_items,
    parse_fxtwitter_timeline,
    parse_x_syndication_html,
)
from src.sources import NewsItem


def _syndication_html(entries):
    payload = {"props": {"pageProps": {"timeline": {"entries": entries}}}}
    return '<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script></html>'


def test_parse_x_syndication_html_returns_fresh_direct_status_posts():
    html = _syndication_html([
        {
            "type": "tweet",
            "content": {
                "tweet": {
                    "id_str": "1964321000000000001",
                    "full_text": "Reuters: Iran says talks on Hormuz will continue today.",
                    "created_at": "Sat Sep 05 08:35:00 +0000 2026",
                }
            },
        },
        {
            "type": "tweet",
            "content": {
                "tweet": {
                    "id_str": "1964321000000000002",
                    "full_text": "Unrelated sports update",
                    "created_at": "Sat Sep 05 08:36:00 +0000 2026",
                }
            },
        },
    ])

    items = parse_x_syndication_html(html, "Reuters", "@Reuters")

    assert len(items) == 1
    item = items[0]
    assert item.key == "x:Reuters:1964321000000000001"
    assert item.source == "Reuters / X"
    assert item.link == "https://x.com/Reuters/status/1964321000000000001"
    assert "Iran" in item.title
    assert item.published == "Sat, 05 Sep 2026 08:35:00 +0000"


def test_parse_fxtwitter_timeline_keeps_every_iran_related_status_with_direct_x_link():
    payload = {
        "code": 200,
        "results": [
            {
                "type": "status",
                "id": "2096158936885874844",
                "url": "https://x.com/Reuters/status/2096158936885874844",
                "text": "Blasts heard near Iran's Kharg Island in Gulf, amid reports tanker hit https://reut.rs/a",
                "created_at": "Sat Sep 05 08:50:09 +0000 2026",
            },
            {
                "type": "status",
                "id": "2096157673938952432",
                "url": "https://x.com/Reuters/status/2096157673938952432",
                "text": "Unrelated technology story",
                "created_at": "Sat Sep 05 08:45:08 +0000 2026",
            },
        ],
    }

    items = parse_fxtwitter_timeline(payload, "Reuters", "@Reuters")

    assert len(items) == 1
    assert items[0].key == "x:Reuters:2096158936885874844"
    assert items[0].source == "Reuters / X"
    assert items[0].link == "https://x.com/Reuters/status/2096158936885874844"
    assert items[0].published == "Sat, 05 Sep 2026 08:50:09 +0000"


def test_builtin_fetch_prefers_fxtwitter_timeline_over_google(monkeypatch):
    source = {"name": "Reuters", "handle": "@Reuters"}
    monkeypatch.setattr("src.newsroom_x.builtin_x_news_sources", lambda: (source,))
    google_called = []
    payload = {
        "code": 200,
        "results": [{
            "type": "status",
            "id": "2096158936885874844",
            "url": "https://x.com/Reuters/status/2096158936885874844",
            "text": "Iran tanker incident near Kharg Island",
            "created_at": "Sat Sep 05 08:50:09 +0000 2026",
        }],
    }

    def searcher(_source):
        google_called.append(True)
        return []

    items = fetch_builtin_x_news_items(searcher=searcher, timeline_fetcher=lambda _source: payload)

    assert [item.key for item in items] == ["x:Reuters:2096158936885874844"]
    assert google_called == []


def test_builtin_fetch_prefers_explicit_syndication_and_does_not_require_google_indexing(monkeypatch):
    source = {"name": "Reuters", "handle": "@Reuters"}
    html = _syndication_html([
        {
            "type": "tweet",
            "content": {
                "tweet": {
                    "id_str": "1964321000000000010",
                    "text": "Iran and the United States discuss nuclear sanctions today.",
                    "created_at": "Sat Sep 05 08:40:00 +0000 2026",
                }
            },
        }
    ])

    monkeypatch.setattr("src.newsroom_x.builtin_x_news_sources", lambda: (source,))
    google_called = []

    def syndication_fetcher(_source):
        return html

    def searcher(_source):
        google_called.append(True)
        return [NewsItem("g", "Reuters / X", "old", "", "https://news.google.com/old", "Fri, 04 Sep 2026 08:00:00 GMT")]

    items = fetch_builtin_x_news_items(searcher=searcher, syndication_fetcher=syndication_fetcher)

    assert [item.key for item in items] == ["x:Reuters:1964321000000000010"]
    assert google_called == []


def test_builtin_fetch_falls_back_to_google_when_direct_sources_fail(monkeypatch):
    source = {"name": "Reuters", "handle": "@Reuters"}
    monkeypatch.setattr("src.newsroom_x.builtin_x_news_sources", lambda: (source,))

    def timeline_fetcher(_source):
        raise RuntimeError("fx unavailable")

    direct = NewsItem(
        "g1", "Reuters / X", "Iran sanctions update", "",
        "https://x.com/Reuters/status/1964321000000000020", "Sat, 05 Sep 2026 08:45:00 GMT",
    )

    items = fetch_builtin_x_news_items(searcher=lambda _source: [direct], timeline_fetcher=timeline_fetcher)

    assert len(items) == 1
    assert items[0].link.endswith("/1964321000000000020")
