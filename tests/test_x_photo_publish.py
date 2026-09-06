from src.fresh_x import MediaNewsItem


def _item() -> MediaNewsItem:
    return MediaNewsItem(
        "x:Reuters:123",
        "Reuters / X",
        "Iran update",
        "",
        "https://x.com/Reuters/status/123",
        "Sun, 06 Sep 2026 06:00:00 +0000",
        "https://pbs.twimg.com/media/example.jpg",
    )


def test_news_with_x_photo_uses_photo_sender(monkeypatch):
    from src import runtime

    calls = []
    item = _item()
    runtime._pending_auto_key = item.key
    runtime._pending_auto_item = item
    monkeypatch.setattr(runtime, "_send_telegram_photo", lambda photo, text, token, chat, *a, **k: calls.append((photo, text)))
    monkeypatch.setattr(runtime, "_original_send_telegram", lambda *a, **k: calls.append(("text", a[0])))
    monkeypatch.setattr(runtime._store, "mark_auto_published", lambda key: None)

    runtime._send_with_tracking("خبر فارسی", "token", "chat")

    assert calls == [(item.media_url, "خبر فارسی")]


def test_photo_failure_falls_back_to_text_news(monkeypatch):
    from src import runtime

    calls = []
    item = _item()
    runtime._pending_auto_key = item.key
    runtime._pending_auto_item = item

    def fail_photo(*args, **kwargs):
        raise RuntimeError("photo failed")

    monkeypatch.setattr(runtime, "_send_telegram_photo", fail_photo)
    monkeypatch.setattr(runtime, "_original_send_telegram", lambda text, token, chat, *a, **k: calls.append(text))
    monkeypatch.setattr(runtime._store, "mark_auto_published", lambda key: None)

    runtime._send_with_tracking("خبر فارسی", "token", "chat")

    assert calls == ["خبر فارسی"]
