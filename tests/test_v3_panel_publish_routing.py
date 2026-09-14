from __future__ import annotations

import json

import panel.app as panel_app_module
import src.panel_command_router as router
from panel.app import create_app
from panel.command_center import bp as command_center_bp
from panel.newsroom_api import bp as newsroom_api_bp


class FakeData:
    def __init__(self):
        self.files = {
            "data/newsroom_settings.json": {"auto_publish": True, "emergency_lock": False},
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/panel_live_feed.json": [
                {
                    "item_id": "live-1",
                    "news_key": "key-1",
                    "source": "Reuters",
                    "source_url": "https://example.com/1",
                    "original_title": "Original",
                    "persian_title": "تیتر نهایی",
                    "persian_body": "متن نهایی",
                    "published_at_source": "2026-09-14T11:00:00+00:00",
                    "panel_status": "new",
                }
            ],
            "state.json": {"newsroom_engine": "v3"},
        }
        self.commands: list[dict] = []

    def read_json(self, path, default):
        return self.files.get(path, default), "sha"

    def write_json(self, path, value, sha, message):
        del sha, message
        self.files[path] = value
        if path.startswith("panel_commands/"):
            self.commands.append(dict(value))
        return {"sha": "next"}

    def mark_news_seen(self, key):
        return None


def _client(data: FakeData, *, newsroom: bool = True):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
            "LIVE_FEED_TRANSLATOR": lambda text: text,
        }
    )
    app.register_blueprint(command_center_bp)
    if newsroom:
        app.register_blueprint(newsroom_api_bp)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = True
    return client


def test_newsroom_live_publish_enqueues_v3_publish_not_legacy_publish():
    data = FakeData()
    response = _client(data).post("/api/newsroom/live/live-1/publish")

    assert response.status_code == 202
    assert response.get_json()["status"] == "queued"
    command = data.commands[-1]
    assert command["action"] == "v3_publish"
    assert command["item_id"] == "live-1"
    assert command["title"] == "تیتر نهایی"
    assert command["body"] == "متن نهایی"
    assert command["source"] == "Reuters"
    assert command["source_url"] == "https://example.com/1"


def test_legacy_command_center_publish_alias_is_absorbed_by_safe_v3_router():
    data = FakeData()
    response = _client(data).post("/api/command-center/live/live-1/publish")

    assert response.status_code == 202
    assert data.commands[-1]["action"] == "publish"
    assert "publish" in router.NEWSROOM_ACTIONS


def _exercise_router_publish_alias(root, monkeypatch, *, action: str):
    (root / "data").mkdir()
    (root / "panel_commands").mkdir()
    queue = [
        {
            "id": "live-1",
            "item_id": "live-1",
            "news_key": "key-1",
            "source": "Reuters",
            "source_url": "https://example.com/1",
            "persian_title": "تیتر نهایی",
            "persian_body": "متن نهایی",
            "status": "pending",
        }
    ]
    (root / "data" / "editorial_queue.json").write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    (root / "data" / "editorial_history.json").write_text("[]", encoding="utf-8")
    (root / "data" / "panel_live_feed.json").write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    command_path = root / "panel_commands" / "cmd-v3.json"
    command_path.write_text(
        json.dumps(
            {
                "command_id": "cmd-v3",
                "action": action,
                "item_id": "live-1",
                "news_key": "key-1",
                "source": "Reuters",
                "source_url": "https://example.com/1",
                "title": "تیتر نهایی",
                "body": "متن نهایی",
                "published_at": "2026-09-14T11:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    calls = []

    def fake_publish_manual_story(**kwargs):
        calls.append(kwargs)
        return {
            "status": "succeeded",
            "story_id": "panel-story-1",
            "telegram_message_id": 1777,
            "error": "",
        }

    monkeypatch.chdir(root)
    monkeypatch.setattr(router, "publish_manual_story", fake_publish_manual_story)
    monkeypatch.setattr(
        router,
        "apply_legacy_command",
        lambda _path: (_ for _ in ()).throw(AssertionError("legacy publish path used")),
    )

    result = router.apply_command(command_path)
    assert result["status"] == "succeeded"
    assert result["telegram_message_id"] == 1777
    assert len(calls) == 1
    assert not command_path.exists()
    history = json.loads((root / "data" / "editorial_history.json").read_text(encoding="utf-8"))
    assert history[0]["id"] == "live-1"
    assert history[0]["status"] == "published_manual"
    remaining = json.loads((root / "data" / "editorial_queue.json").read_text(encoding="utf-8"))
    assert remaining == []


def test_runtime_router_handles_v3_publish_without_legacy_telegram_path(tmp_path, monkeypatch):
    _exercise_router_publish_alias(tmp_path, monkeypatch, action="v3_publish")


def test_runtime_router_absorbs_old_publish_command_without_legacy_telegram_path(tmp_path, monkeypatch):
    _exercise_router_publish_alias(tmp_path, monkeypatch, action="publish")


def test_review_form_never_calls_telegram_directly_and_enqueues_v3(tmp_path, monkeypatch):
    del tmp_path
    data = FakeData()
    data.files["data/editorial_queue.json"] = [
        {
            "id": "review-1",
            "item_id": "review-1",
            "news_key": "review-key",
            "source": "Reuters",
            "source_url": "https://example.com/review",
            "original_title": "Original",
            "original_summary": "Original summary",
            "persian_title": "تیتر اولیه",
            "persian_body": "متن اولیه",
            "published_at_source": "2026-09-14T11:00:00+00:00",
            "status": "pending",
        }
    ]
    monkeypatch.setattr(
        panel_app_module,
        "send_telegram",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("direct Telegram call used")),
    )

    response = _client(data, newsroom=False).post(
        "/review/review-1",
        data={
            "title_fa": "تیتر نهایی بررسی",
            "body_fa": "متن نهایی بررسی",
            "publish": "تأیید و انتشار فوری",
        },
    )

    assert response.status_code == 302
    command = data.commands[-1]
    assert command["action"] == "v3_publish"
    assert command["item_id"] == "review-1"
    assert command["title"] == "تیتر نهایی بررسی"
    assert data.files["data/editorial_history.json"] == []
