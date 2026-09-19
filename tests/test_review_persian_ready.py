from __future__ import annotations

import re

from werkzeug.security import generate_password_hash

from panel.app import create_app


class FakeData:
    def __init__(self, queue=None):
        self.files = {
            "data/editorial_queue.json": list(queue or []),
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [],
            "data/custom_sources.json": [],
            "data/newsroom_settings.json": {"auto_publish": True, "emergency_lock": False},
            "state.json": {"news_seen": []},
        }

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        self.files[path] = value
        return {"content": {"sha": "next"}}

    def mark_news_seen(self, key):
        seen = [x for x in self.files["state.json"].get("news_seen", []) if x != key]
        seen.insert(0, key)
        self.files["state.json"]["news_seen"] = seen


def _story(**overrides):
    item = {
        "id": "story-1",
        "status": "pending",
        "source": "Reuters",
        "source_url": "https://example.com/story-1",
        "original_title": "Iran announces new negotiating conditions",
        "original_summary": "Officials described seven conditions for renewed negotiations.",
        "persian_title": "",
        "persian_body": "",
    }
    item.update(overrides)
    return item


def _app(data: FakeData, translator):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "PANEL_PASSWORD_HASH": generate_password_hash("panel-pass"),
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": translator,
            "REVIEW_TRANSLATION_BATCH": 4,
        }
    )


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match
    return match.group(1)


def _login(client):
    page = client.get("/login")
    token = _csrf(page.get_data(as_text=True))
    return client.post(
        "/login",
        data={"password": "panel-pass", "csrf_token": token},
        follow_redirects=True,
    )


def test_review_hides_story_when_machine_translation_is_not_persian():
    data = FakeData([_story()])
    app = _app(data, translator=lambda text: text)
    client = app.test_client()
    _login(client)

    response = client.get("/review")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Iran announces new negotiating conditions" not in text
    assert "ترجمه فارسی در حال آماده‌سازی" not in text
    assert "0 مورد" in text
    stored = data.files["data/editorial_queue.json"][0]
    assert stored.get("persian_title") in {None, ""}
    assert stored.get("persian_body") in {None, ""}


def test_review_machine_translates_persists_and_only_then_shows_story():
    data = FakeData([_story()])
    translations = {
        "Iran announces new negotiating conditions": "ایران شرایط تازه‌ای برای مذاکره اعلام کرد",
        "Officials described seven conditions for renewed negotiations.": "مقام‌ها هفت شرط را برای ازسرگیری مذاکرات تشریح کردند.",
    }
    app = _app(data, translator=lambda text: translations.get(text, text))
    client = app.test_client()
    _login(client)

    response = client.get("/review")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "ایران شرایط تازه‌ای برای مذاکره اعلام کرد" in text
    assert "مقام‌ها هفت شرط را برای ازسرگیری مذاکرات تشریح کردند." in text
    assert "Iran announces new negotiating conditions" not in text
    assert "1 مورد" in text
    stored = data.files["data/editorial_queue.json"][0]
    assert stored["persian_title"] == "ایران شرایط تازه‌ای برای مذاکره اعلام کرد"
    assert stored["persian_body"] == "مقام‌ها هفت شرط را برای ازسرگیری مذاکرات تشریح کردند."


def test_review_detail_is_persian_first_and_source_is_collapsed_reference():
    data = FakeData(
        [
            _story(
                persian_title="ایران شرایط تازه‌ای برای مذاکره اعلام کرد",
                persian_body="مقام‌ها هفت شرط را برای ازسرگیری مذاکرات تشریح کردند.",
            )
        ]
    )
    app = _app(data, translator=lambda text: text)
    client = app.test_client()
    _login(client)

    response = client.get("/review/story-1")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert text.index("نسخه فارسی نهایی") < text.index("اصل خبر")
    assert "<details" in text
    assert "<summary" in text
    assert "Iran announces new negotiating conditions" in text


def test_direct_review_url_does_not_render_untranslated_english_story():
    data = FakeData([_story()])
    app = _app(data, translator=lambda text: text)
    client = app.test_client()
    _login(client)

    response = client.get("/review/story-1", follow_redirects=True)
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Iran announces new negotiating conditions" not in text
    assert "ترجمه ماشینی فارسی این خبر هنوز آماده نشده" in text
