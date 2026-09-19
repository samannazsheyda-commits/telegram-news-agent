import json
from datetime import datetime, timezone

from flask import Flask

from panel.ready_feed import dashboard_live_feed
from src.local_json_repository import LocalJsonRepository


def _row(item_id: str, *, title: str, body: str = "Body", status: str = "new") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "item_id": item_id,
        "source": "Reuters",
        "source_url": f"https://example.com/{item_id}",
        "original_title": title,
        "original_summary": body,
        "panel_status": status,
        "published_at_source": now,
        "updated_at": now,
    }


def _app(translator):
    app = Flask(__name__)
    app.config["LIVE_FEED_TRANSLATOR"] = translator
    return app


def test_dashboard_persists_translation_before_story_becomes_visible(tmp_path):
    repo = LocalJsonRepository(tmp_path)
    repo.write_json("data/panel_live_feed.json", [_row("story-1", title="Breaking news", body="Details here")], None, "seed")
    translations = {
        "Breaking news": "خبر فوری",
        "Details here": "جزئیات خبر",
    }

    with _app(translations.get).app_context():
        items = dashboard_live_feed(repo)

    assert [item["item_id"] for item in items] == ["story-1"]
    assert items[0]["persian_title"] == "خبر فوری"
    assert items[0]["persian_body"] == "جزئیات خبر"
    persisted = json.loads((tmp_path / "data/panel_live_feed.json").read_text(encoding="utf-8"))
    assert persisted[0]["machine_translation_status"] == "passed"
    assert persisted[0]["persian_title"] == "خبر فوری"
    assert persisted[0]["persian_body"] == "جزئیات خبر"


def test_dashboard_does_not_expose_story_when_machine_translation_fails(tmp_path):
    repo = LocalJsonRepository(tmp_path)
    repo.write_json("data/panel_live_feed.json", [_row("story-2", title="English only")], None, "seed")

    with _app(lambda text: text).app_context():
        items = dashboard_live_feed(repo)

    assert items == []


def test_dashboard_hides_published_story_from_active_feed(tmp_path):
    repo = LocalJsonRepository(tmp_path)
    row = _row("story-3", title="Already published", status="published_manual")
    row.update(persian_title="خبر منتشرشده", persian_body="متن", machine_translation_status="passed")
    repo.write_json("data/panel_live_feed.json", [row], None, "seed")

    with _app(lambda text: "ترجمه").app_context():
        items = dashboard_live_feed(repo)

    assert items == []


def test_persian_source_is_marked_ready_without_network_translation(tmp_path):
    repo = LocalJsonRepository(tmp_path)
    repo.write_json(
        "data/panel_live_feed.json",
        [_row("story-4", title="تیتر فارسی", body="متن فارسی")],
        None,
        "seed",
    )

    def should_not_run(_text):
        raise AssertionError("translator must not run for Persian source copy")

    with _app(should_not_run).app_context():
        items = dashboard_live_feed(repo)

    assert len(items) == 1
    assert items[0]["persian_title"] == "تیتر فارسی"
    assert items[0]["persian_body"] == "متن فارسی"
    assert items[0]["machine_translation_status"] == "passed"
