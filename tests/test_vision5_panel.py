from __future__ import annotations

import io
import re

from werkzeug.security import generate_password_hash


class PanelStore:
    def __init__(self):
        self.stories = {
            "story-1": {
                "id": "story-1",
                "source": "Reuters",
                "source_url": "https://example.com/1",
                "original_title": "Original headline",
                "original_text": "Original body",
                "google_title": "تیتر فارسی خبر",
                "google_body": "متن کامل فارسی خبر",
                "luna_title": "تیتر لونا",
                "luna_body": "متن لونا",
                "final_title": None,
                "final_body": None,
                "status": "READY_FOR_REVIEW",
                "published_at_source": "2026-09-22T09:00:00+00:00",
                "updated_at": "2026-09-22T09:01:00+00:00",
            }
        }
        self.list_calls = []
        self.review_calls = []
        self.reject_calls = []
        self.sources = [
            {"id": "source-1", "kind": "rss", "identity": "https://example.com/feed", "display_name": "Example", "enabled": True, "last_error": None}
        ]
        self.rules = {}

    def list_stories(self, *, statuses, query, source, page, page_size):
        self.list_calls.append(
            {
                "statuses": statuses,
                "query": query,
                "source": source,
                "page": page,
                "page_size": page_size,
            }
        )
        rows = list(self.stories.values())
        if statuses:
            rows = [row for row in rows if row["status"] in statuses]
        if query:
            rows = [row for row in rows if query in row["google_title"]]
        return {"items": rows, "total": len(rows), "page": page, "page_size": page_size}

    def get_story(self, story_id):
        return self.stories.get(story_id)

    def save_review(self, story_id, *, title, body, copy_mode, actor, approve):
        self.review_calls.append(
            {
                "story_id": story_id,
                "title": title,
                "body": body,
                "copy_mode": copy_mode,
                "actor": actor,
                "approve": approve,
            }
        )

    def reject_story(self, story_id, *, reason, actor):
        self.reject_calls.append(
            {"story_id": story_id, "reason": reason, "actor": actor}
        )

    def dashboard_metrics(self):
        return {"sources_total": len(self.sources), "review_ready": 1, "approved": 0, "publish_failed": 0, "published_today": 0}

    def list_sources(self):
        return self.sources

    def upsert_source(self, source):
        row = {"id": "source-2", **source, "enabled": True, "last_error": None}
        self.sources.append(row)
        return row

    def set_source_enabled(self, source_id, *, enabled, actor):
        row = next(source for source in self.sources if source["id"] == source_id)
        row["enabled"] = enabled
        return row

    def get_newsroom_rule(self, key):
        value = self.rules.get(key)
        return {"rule_json": value} if value else None

    def upsert_newsroom_rule(self, key, value, *, actor):
        self.rules[key] = value
        return {"rule_key": key, "rule_json": value}

    def list_service_health(self):
        return [{"service_name": "collector", "status": "healthy", "detail_json": {}, "checked_at": "now"}]

    def list_audit(self, *, limit):
        return [{"actor": "editor", "action": "story_ingested", "status": "succeeded", "created_at": "now"}]


def _app(store, **services):
    from bikhabar_v5.web import create_app

    return create_app(
        store=store,
        **services,
        config={
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "ADMIN_USERNAME": "editor",
            "ADMIN_PASSWORD_HASH": generate_password_hash("strong-password"),
        },
    )


def _csrf(html):
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, html
    return match.group(1)


def _login(client):
    token = _csrf(client.get("/login").get_data(as_text=True))
    response = client.post(
        "/login",
        data={"username": "editor", "password": "strong-password", "csrf_token": token},
    )
    assert response.status_code == 302


def test_panel_requires_authentication_and_csrf():
    client = _app(PanelStore()).test_client()

    assert client.get("/").status_code == 302
    assert client.post("/login", data={"username": "editor", "password": "strong-password"}).status_code == 400


def test_login_renders_mobile_rtl_inbox_from_standalone_store():
    store = PanelStore()
    client = _app(store).test_client()
    _login(client)

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<html lang="fa" dir="rtl">' in html
    assert "تیتر فارسی خبر" in html
    assert "viewport" in html
    assert store.list_calls[-1]["statuses"] == ("READY_FOR_REVIEW", "LUNA_TRANSLATED")


def test_inbox_search_filter_pagination_and_authenticated_json_api():
    store = PanelStore()
    client = _app(store).test_client()

    assert client.get("/api/stories").status_code == 401
    _login(client)
    response = client.get("/api/stories?q=فارسی&source=Reuters&page=2&status=READY_FOR_REVIEW")

    assert response.status_code == 200
    assert response.json["items"][0]["id"] == "story-1"
    assert store.list_calls[-1] == {
        "statuses": ("READY_FOR_REVIEW",),
        "query": "فارسی",
        "source": "Reuters",
        "page": 2,
        "page_size": 25,
    }


def test_editor_saves_explicit_final_copy_and_approves():
    store = PanelStore()
    client = _app(store).test_client()
    _login(client)
    token = _csrf(client.get("/stories/story-1").get_data(as_text=True))

    response = client.post(
        "/stories/story-1/review",
        data={
            "csrf_token": token,
            "title": "تیتر نهایی",
            "body": "متن نهایی",
            "copy_mode": "edited",
            "action": "approve",
        },
    )

    assert response.status_code == 302
    assert store.review_calls == [
        {
            "story_id": "story-1",
            "title": "تیتر نهایی",
            "body": "متن نهایی",
            "copy_mode": "edited",
            "actor": "editor",
            "approve": True,
        }
    ]


class PublishQueue:
    def __init__(self):
        self.jobs = []

    def enqueue(self, kind, payload):
        self.jobs.append((kind, payload))
        return "job-1"


def test_approved_story_is_enqueued_for_real_publisher():
    store = PanelStore()
    queue = PublishQueue()
    client = _app(store, job_queue=queue).test_client()
    _login(client)
    token = _csrf(client.get("/stories/story-1").get_data(as_text=True))

    response = client.post(
        "/stories/story-1/review",
        data={
            "csrf_token": token,
            "title": "تیتر نهایی",
            "body": "متن نهایی",
            "copy_mode": "edited",
            "action": "approve",
        },
    )

    assert response.status_code == 302
    assert queue.jobs == [("publish", {"story_id": "story-1", "allow_retry": False})]


def test_reject_is_permanent_and_requires_a_reason():
    store = PanelStore()
    client = _app(store).test_client()
    _login(client)
    token = _csrf(client.get("/stories/story-1").get_data(as_text=True))

    missing = client.post(
        "/stories/story-1/review",
        data={"csrf_token": token, "action": "reject", "reject_reason": ""},
    )
    accepted = client.post(
        "/stories/story-1/review",
        data={"csrf_token": token, "action": "reject", "reject_reason": "تکراری"},
    )

    assert missing.status_code == 400
    assert accepted.status_code == 302
    assert store.reject_calls == [
        {"story_id": "story-1", "reason": "تکراری", "actor": "editor"}
    ]


class Luna:
    def __init__(self):
        self.calls = []

    def chat(self, *, user_id, message, story_id=None):
        self.calls.append(("chat", user_id, message, story_id))
        return {"text": "پاسخ واقعی لونا", "response_id": "resp-1"}

    def alternate_translation(self, *, story_id, actor):
        self.calls.append(("translate", story_id, actor))
        return {"id": story_id, "status": "LUNA_TRANSLATED"}


class Transcriber:
    def transcribe(self, *, audio, filename, content_type):
        assert audio == b"voice"
        return "متن پیام صوتی"


def test_luna_panel_chat_voice_and_alternate_translation_are_real_routes():
    luna = Luna()
    client = _app(PanelStore(), luna=luna, transcriber=Transcriber()).test_client()
    _login(client)
    token = _csrf(client.get("/").get_data(as_text=True))

    page = client.get("/luna")
    chat = client.post(
        "/api/luna/chat",
        json={"message": "این خبر را بررسی کن", "story_id": "story-1"},
        headers={"X-CSRFToken": token},
    )
    voice = client.post(
        "/api/luna/voice",
        data={"voice": (io.BytesIO(b"voice"), "voice.ogg")},
        headers={"X-CSRFToken": token},
        content_type="multipart/form-data",
    )
    translated = client.post(
        "/stories/story-1/luna",
        data={"csrf_token": token},
    )

    assert page.status_code == 200
    assert chat.json["text"] == "پاسخ واقعی لونا"
    assert voice.json["transcript"] == "متن پیام صوتی"
    assert translated.status_code == 302
    assert ("translate", "story-1", "editor") in luna.calls


def test_control_sources_settings_and_system_routes_mutate_postgres_contract():
    store = PanelStore()
    client = _app(store).test_client()
    _login(client)
    token = _csrf(client.get("/").get_data(as_text=True))

    assert client.get("/control").status_code == 200
    assert client.get("/sources").status_code == 200
    added = client.post(
        "/sources",
        data={
            "csrf_token": token,
            "kind": "telegram",
            "identity": "@bikhabaar",
            "display_name": "Bikhabar",
        },
    )
    toggled = client.post(
        "/sources/source-1/toggle",
        data={"csrf_token": token, "enabled": "false"},
    )
    settings = client.post(
        "/settings",
        data={
            "csrf_token": token,
            "freshness_hours": "5",
            "daily_limit": "60",
            "auto_publish": "false",
        },
    )

    assert added.status_code == 302
    assert toggled.status_code == 302
    assert store.sources[0]["enabled"] is False
    assert settings.status_code == 302
    assert store.rules["runtime_settings"]["daily_limit"] == 60
    assert client.get("/system").status_code == 200
