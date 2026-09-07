import json
from pathlib import Path

from src.editorial_store import LocalEditorialStore, ReviewItem
from src.panel_command_router import apply_command


def _seed_store(tmp_path: Path) -> LocalEditorialStore:
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "panel_results").mkdir(parents=True, exist_ok=True)
    return LocalEditorialStore(tmp_path / "data/editorial_queue.json", tmp_path / "data/editorial_history.json")


def _item(key: str, *, status: str = "pending") -> ReviewItem:
    return ReviewItem.for_news(
        news_key=key,
        source="Reuters",
        source_url=f"https://example.com/{key}",
        original_title=f"story {key}",
        persian_title=f"خبر {key}",
        status=status,
    )


def _write_command(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"command_id": name, **payload}, ensure_ascii=False), encoding="utf-8")
    return path


def test_clear_pending_moves_selected_items_to_superseded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = _seed_store(tmp_path)
    one = _item("one")
    two = _item("two")
    store.upsert_queue(one)
    store.upsert_queue(two)
    command = _write_command(tmp_path, "clear-pending", {"action": "clear", "scope": "pending", "ids": [one.id, two.id]})

    result = apply_command(command)

    assert result["status"] == "succeeded"
    assert store.queue() == []
    history = store.history()
    assert {row["id"] for row in history} == {one.id, two.id}
    assert {row["status"] for row in history} == {"superseded"}
    assert not command.exists()


def test_clear_published_only_removes_selected_published_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = _seed_store(tmp_path)
    published = _item("published", status="published_manual")
    rejected = _item("rejected", status="rejected_manual")
    store.upsert_history(published)
    store.upsert_history(rejected)
    command = _write_command(tmp_path, "clear-published", {"action": "clear", "scope": "published", "ids": [published.id, rejected.id]})

    result = apply_command(command)

    assert result["status"] == "succeeded"
    remaining = store.history()
    assert [row["id"] for row in remaining] == [rejected.id]


def test_settings_save_round_trip_and_validates_thresholds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_store(tmp_path)
    command = _write_command(
        tmp_path,
        "settings-save",
        {
            "action": "settings_save",
            "settings": {
                "version": 1,
                "emergency_lock": True,
                "auto_publish": False,
                "freshness_hours": 3,
                "dedup_mode": "strict",
                "earthquake_min": 2.0,
                "earthquake_breaking": 4.0,
                "notam_sensitivity": "high",
                "market": {"btc": True},
                "alerts": {},
                "ui": {"density": "compact"},
                "sources": {"رویترز": {"enabled": True, "trust": 95}},
            },
        },
    )

    result = apply_command(command)

    assert result["status"] == "succeeded"
    saved = json.loads((tmp_path / "data/newsroom_settings.json").read_text(encoding="utf-8"))
    assert saved["emergency_lock"] is True
    assert saved["auto_publish"] is False
    assert saved["earthquake_min"] == 2.0
    assert saved["earthquake_breaking"] == 4.0
    assert saved["ui"]["density"] == "compact"
    assert saved["updated_at"]


def test_clear_rejects_unknown_scope(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_store(tmp_path)
    command = _write_command(tmp_path, "clear-bad", {"action": "clear", "scope": "everything", "ids": []})

    result = apply_command(command)

    assert result["status"] == "failed"
    assert result["message"] == "invalid_clear_scope"
