import json
from pathlib import Path

from src.editorial_store import LocalEditorialStore, ReviewItem
from src.panel_command_file import load_command_args, process_command_file


def _store(tmp_path):
    store = LocalEditorialStore(tmp_path / "queue.json", tmp_path / "history.json")
    item = ReviewItem.for_news(
        news_key="news-1",
        source="Test",
        source_url="https://example.com/story-1",
        original_title="Original",
        original_summary="Summary",
        persian_title="تیتر",
        persian_body="متن",
    )
    store.upsert_queue(item)
    return store, item


def _command(tmp_path, *, action="publish", item_id="", title="تیتر", body="متن", command_id="cmd-1"):
    path = tmp_path / f"{command_id}.json"
    path.write_text(json.dumps({
        "command_id": command_id,
        "action": action,
        "item_id": item_id,
        "title": title,
        "body": body,
        "created_at": "2026-09-07T08:00:00+00:00",
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_command_args_preserves_persian_and_newlines(tmp_path):
    path = tmp_path / "cmd.json"
    path.write_text(json.dumps({
        "command_id": "cmd-1",
        "action": "publish",
        "item_id": "abc123",
        "title": "تیتر \"نهایی\"",
        "body": "خط اول\nخط دوم",
        "created_at": "2026-09-07T08:00:00+00:00",
    }, ensure_ascii=False), encoding="utf-8")

    args = load_command_args(path)
    assert args["command_id"] == "cmd-1"
    assert args["title"] == "تیتر \"نهایی\""
    assert args["body"] == "خط اول\nخط دوم"


def test_reject_command_is_idempotent(tmp_path):
    store, item = _store(tmp_path)
    command = _command(tmp_path, action="reject", item_id=item.id)
    result_dir = tmp_path / "results"

    first = process_command_file(str(command), store=store, token="", chat_id="", state_path=str(tmp_path / "state.json"), result_dir=str(result_dir))
    second = process_command_file(str(command), store=store, token="", chat_id="", state_path=str(tmp_path / "state.json"), result_dir=str(result_dir))

    assert first["status"] == "succeeded"
    assert second["status"] in {"succeeded", "reconciled"}
    assert len([x for x in store.history() if x.get("id") == item.id]) == 1


def test_publish_retry_never_sends_telegram_twice(tmp_path):
    store, item = _store(tmp_path)
    command = _command(tmp_path, item_id=item.id)
    sent = []
    result_dir = tmp_path / "results"

    def sender(text, token, chat_id):
        sent.append(text)

    first = process_command_file(str(command), store=store, token="bot", chat_id="@bikhabaar", state_path=str(tmp_path / "state.json"), result_dir=str(result_dir), sender=sender, channel_checker=lambda url: False)
    second = process_command_file(str(command), store=store, token="bot", chat_id="@bikhabaar", state_path=str(tmp_path / "state.json"), result_dir=str(result_dir), sender=sender, channel_checker=lambda url: False)

    assert first["status"] == "succeeded"
    assert second["status"] in {"succeeded", "reconciled"}
    assert len(sent) == 1


def test_publish_reconciles_when_source_already_in_channel(tmp_path):
    store, item = _store(tmp_path)
    command = _command(tmp_path, item_id=item.id)
    sent = []

    result = process_command_file(str(command), store=store, token="bot", chat_id="@bikhabaar", state_path=str(tmp_path / "state.json"), result_dir=str(tmp_path / "results"), sender=lambda *a, **k: sent.append(a), channel_checker=lambda url: True)

    assert result["status"] == "reconciled"
    assert sent == []
    assert store.get_pending(item.id) is None


def test_publish_failure_keeps_item_pending_and_writes_failed_result(tmp_path):
    store, item = _store(tmp_path)
    command = _command(tmp_path, item_id=item.id)

    def boom(*args, **kwargs):
        raise RuntimeError("telegram down")

    result = process_command_file(str(command), store=store, token="bot", chat_id="@bikhabaar", state_path=str(tmp_path / "state.json"), result_dir=str(tmp_path / "results"), sender=boom, channel_checker=lambda url: False)

    assert result["status"] == "failed"
    assert store.get_pending(item.id) is not None
    payload = json.loads((tmp_path / "results" / "cmd-1.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"


def test_successful_terminal_result_consumes_command(tmp_path):
    store, item = _store(tmp_path)
    command = _command(tmp_path, action="reject", item_id=item.id)
    process_command_file(str(command), store=store, token="", chat_id="", state_path=str(tmp_path / "state.json"), result_dir=str(tmp_path / "results"))
    assert not Path(command).exists()
