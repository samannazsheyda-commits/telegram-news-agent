from __future__ import annotations

import json

import pytest

from src.editorial_store import LocalEditorialStore, ReviewItem
from src.manual_publish import publish_review_item, reject_review_item


def _pending(store):
    item = ReviewItem.for_news(
        news_key="manual-1",
        source="Reuters",
        source_url="https://example.com/story",
        original_title="Original title",
        original_summary="Original body",
        persian_title="تیتر اولیه",
        persian_body="متن اولیه",
        published_at_source="Fri, 05 Sep 2026 10:00:00 GMT",
        rejection_reason="article_or_commentary",
    )
    store.upsert_queue(item)
    return item


def test_manual_publish_saves_exact_edited_copy_after_telegram_success(tmp_path):
    store = LocalEditorialStore(tmp_path / "q.json", tmp_path / "h.json")
    item = _pending(store)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"news_seen": []}), encoding="utf-8")
    sent = []

    result = publish_review_item(
        store,
        item.id,
        "تیتر نهایی",
        "متن نهایی",
        "token",
        "chat",
        state_path=state,
        sender=lambda text, token, chat: sent.append(text),
    )

    assert result.status == "published_manual"
    assert result.final_persian_title == "تیتر نهایی"
    assert result.final_persian_body == "متن نهایی"
    assert sent and "تیتر نهایی" in sent[0]
    assert json.loads(state.read_text(encoding="utf-8"))["news_seen"][0] == "manual-1"


def test_manual_publish_exact_newsroom_layout_and_x_source_label(tmp_path):
    store = LocalEditorialStore(tmp_path / "q.json", tmp_path / "h.json")
    item = ReviewItem.for_news(
        news_key="reuters-x-uae",
        source="Reuters / X",
        source_url="https://x.com/Reuters/status/2096895020225663094",
        original_title="UAE creates alternative trade and energy routes after Iranian attacks",
        original_summary="A UAE official says alternative routes are being created after Iranian attacks.",
        persian_title="یک مقام رسمی می‌گوید امارات متحده عربی پس از حملات ایران، مسیرهای تجاری و انرژی جایگزین ایجاد می‌کند",
        persian_body="",
        published_at_source="Sun, 06 Sep 2026 09:35:00 GMT",
    )
    store.upsert_queue(item)
    sent = []

    publish_review_item(
        store,
        item.id,
        item.persian_title,
        "",
        "token",
        "chat",
        sender=lambda text, token, chat: sent.append(text),
    )

    msg = sent[0]
    assert msg.startswith("<b>رویترز / ایکس: یک مقام رسمی می‌گوید امارات متحده عربی پس از حملات ایران، مسیرهای تجاری و انرژی جایگزین ایجاد می‌کند.</b>")
    assert "🇮🇷 🇦🇪" not in msg.splitlines()[0]
    assert "Reuters / X" not in msg
    assert "A UAE official" not in msg
    assert "📌 <a href=\"https://x.com/Reuters/status/2096895020225663094\">لینک منبع خبر</a>" in msg
    assert "📡 <a href=\"https://t.me/bikhabaar\">بی‌خبر</a> ←\nمانیتور تحولات ایران" in msg
    assert msg.endswith("🛑 🇮🇷 🇦🇪 💥")


def test_telegram_failure_leaves_item_pending(tmp_path):
    store = LocalEditorialStore(tmp_path / "q.json", tmp_path / "h.json")
    item = _pending(store)

    with pytest.raises(RuntimeError):
        publish_review_item(
            store,
            item.id,
            "تیتر",
            "متن",
            "token",
            "chat",
            sender=lambda *args: (_ for _ in ()).throw(RuntimeError("telegram down")),
        )

    assert store.get_pending(item.id) is not None


def test_manual_publish_requires_source_url_and_nonempty_title(tmp_path):
    store = LocalEditorialStore(tmp_path / "q.json", tmp_path / "h.json")
    item = ReviewItem.for_news(news_key="bad", source="Reuters", source_url="", original_title="x")
    store.upsert_queue(item)
    with pytest.raises(ValueError):
        publish_review_item(store, item.id, "", "", "token", "chat", sender=lambda *args: None)


def test_already_published_item_cannot_publish_twice(tmp_path):
    store = LocalEditorialStore(tmp_path / "q.json", tmp_path / "h.json")
    item = _pending(store)
    publish_review_item(store, item.id, "تیتر", "", "token", "chat", sender=lambda *args: None)
    with pytest.raises(ValueError, match="not_pending"):
        publish_review_item(store, item.id, "تیتر", "", "token", "chat", sender=lambda *args: None)


def test_reject_moves_item_to_history(tmp_path):
    store = LocalEditorialStore(tmp_path / "q.json", tmp_path / "h.json")
    item = _pending(store)
    result = reject_review_item(store, item.id)
    assert result.status == "rejected_manual"
    assert store.get_pending(item.id) is None
