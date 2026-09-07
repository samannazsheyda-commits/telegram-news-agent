from src import runtime_v11, runtime_v12
from src.sources import NewsItem


def _news(key, source, title, link=None):
    return NewsItem(key, source, title, "", link or f"https://example.com/{key}", "Sun, 06 Sep 2026 16:03:00 GMT")


def test_manual_published_history_is_a_dedup_reference(monkeypatch):
    manual_title = (
        "Netanyahu on Iran: they are not attacking us because if they make that mistake "
        "they will be hit with a blow they cannot imagine"
    )
    candidate = _news(
        "new-key",
        "Another Source",
        "Netanyahu says Iran is not attacking Israel because it knows it would be hit with a blow it cannot imagine",
    )
    monkeypatch.setattr(
        runtime_v11.base._store,
        "history",
        lambda: [
            {
                "news_key": "manual-key",
                "source": "Tabz Live / Telegram",
                "source_url": "https://t.me/tabzlive/102008",
                "original_title": manual_title,
                "original_summary": "",
                "published_at_source": "Sun, 06 Sep 2026 16:03:00 GMT",
                "status": "published_manual",
            }
        ],
    )

    selected, skipped = runtime_v11._select_top_stories_with_published_history([candidate], [])

    assert selected == []
    assert skipped == [candidate]


def test_rejected_history_is_not_a_dedup_reference(monkeypatch):
    candidate = _news("new-key", "Another Source", "Netanyahu says Iran will be hit with a blow it cannot imagine")
    monkeypatch.setattr(
        runtime_v11.base._store,
        "history",
        lambda: [
            {
                "news_key": "rejected-key",
                "source": "Tabz Live / Telegram",
                "source_url": "https://t.me/tabzlive/102008",
                "original_title": "Netanyahu says Iran will be hit with a blow it cannot imagine",
                "original_summary": "",
                "published_at_source": "Sun, 06 Sep 2026 16:03:00 GMT",
                "status": "rejected_manual",
            }
        ],
    )

    selected, skipped = runtime_v11._select_top_stories_with_published_history([candidate], [])

    assert selected == [candidate]
    assert skipped == []


def test_direct_channel_publish_blocks_exact_source_and_seeds_authoritative_history(monkeypatch):
    candidate = _news(
        "tabz-102008",
        "تبز لایو / Telegram",
        "Netanyahu on Iran: more work remains to be done and the regime's end is near",
        "https://t.me/tabzlive/102008",
    )
    written = []
    monkeypatch.setattr(runtime_v12, "_fetch_own_channel_source_links", lambda: {"https://t.me/tabzlive/102008"})
    monkeypatch.setattr(runtime_v12.base._store, "upsert_history", lambda item: written.append(item) or item)
    monkeypatch.setattr(runtime_v12, "_previous_selector", lambda fresh, references: (fresh, []))

    selected, skipped = runtime_v12._select_top_stories_with_own_channel([candidate], [])

    assert selected == []
    assert skipped == [candidate]
    assert len(written) == 1
    assert written[0].status == "published_manual"
    assert written[0].source_url == "https://t.me/tabzlive/102008"
