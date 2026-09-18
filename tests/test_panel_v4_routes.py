from __future__ import annotations

import json
from pathlib import Path

from flask import Flask

from panel.v4 import bp as v4_bp
from panel.v4_actions import bp as v4_actions_bp
from src.local_json_repository import LocalJsonRepository


def _write(root: Path, relative: str, value) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _app(root: Path) -> Flask:
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.extensions["editorial_data"] = LocalJsonRepository(root)
    app.register_blueprint(v4_bp)
    app.register_blueprint(v4_actions_bp)
    return app


def _login(client) -> None:
    with client.session_transaction() as session:
        session["admin"] = True


def _single_command(root: Path) -> dict:
    files = list((root / "panel_commands").glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_send_to_luna_queues_preview_not_publish(tmp_path):
    _write(
        tmp_path,
        "data/panel_live_feed.json",
        [
            {
                "item_id": "story-1",
                "news_key": "key-1",
                "source": "Reuters",
                "source_url": "https://example.com/story-1",
                "original_title": "Iran announces a regional decision",
                "original_summary": "The announcement was made Friday.",
            }
        ],
    )
    client = _app(tmp_path).test_client()
    _login(client)

    response = client.post("/api/v4/items/story-1/luna", json={})

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["status"] == "queued"
    command = _single_command(tmp_path)
    assert command["action"] == "luna_preview"
    assert command["item_id"] == "story-1"
    assert command["original_title"] == "Iran announces a regional decision"


def test_publish_final_queues_approved_copy_without_luna_rerun(tmp_path):
    _write(
        tmp_path,
        "data/editorial_queue.json",
        [
            {
                "id": "story-2",
                "item_id": "story-2",
                "news_key": "key-2",
                "source": "Reuters",
                "source_url": "https://example.com/story-2",
                "original_title": "Original title",
                "original_summary": "Original body",
                "final_persian_title": "تیتر اولیه لونا",
                "final_persian_body": "متن اولیه لونا",
                "status": "pending",
                "luna_status": "ready",
            }
        ],
    )
    client = _app(tmp_path).test_client()
    _login(client)

    response = client.post(
        "/api/v4/items/story-2/publish-final",
        json={"title": "تیتر نهایی ویرایش‌شده", "body": "متن نهایی ویرایش‌شده"},
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["status"] == "queued"
    command = _single_command(tmp_path)
    assert command["action"] == "publish_final"
    assert command["title"] == "تیتر نهایی ویرایش‌شده"
    assert command["body"] == "متن نهایی ویرایش‌شده"

    queue = json.loads((tmp_path / "data/editorial_queue.json").read_text(encoding="utf-8"))
    assert queue[0]["final_persian_title"] == "تیتر نهایی ویرایش‌شده"
    assert queue[0]["final_persian_body"] == "متن نهایی ویرایش‌شده"


def test_queue_luna_preview_overrides_live_copy_in_merged_rows(tmp_path):
    _write(
        tmp_path,
        "data/panel_live_feed.json",
        [{"item_id": "story-3", "source": "Reuters", "source_url": "https://example.com/3", "original_title": "Original"}],
    )
    _write(
        tmp_path,
        "data/editorial_queue.json",
        [{"id": "story-3", "final_persian_title": "نسخه نهایی لونا", "luna_status": "ready", "status": "pending"}],
    )
    app = _app(tmp_path)
    from panel import v4

    with app.app_context():
        rows = v4._merged_editorial_rows()

    assert len(rows) == 1
    assert rows[0]["source"] == "Reuters"
    assert rows[0]["final_persian_title"] == "نسخه نهایی لونا"
    assert rows[0]["luna_status"] == "ready"
