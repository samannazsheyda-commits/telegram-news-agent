import json

from src.panel_command_file import load_command_args


def test_load_command_args_preserves_persian_and_newlines(tmp_path):
    path = tmp_path / "cmd.json"
    path.write_text(json.dumps({
        "action": "publish",
        "item_id": "abc123",
        "title": "تیتر \"نهایی\"",
        "body": "خط اول\nخط دوم",
    }, ensure_ascii=False), encoding="utf-8")

    args = load_command_args(path)

    assert args == {
        "action": "publish",
        "item_id": "abc123",
        "title": "تیتر \"نهایی\"",
        "body": "خط اول\nخط دوم",
    }
