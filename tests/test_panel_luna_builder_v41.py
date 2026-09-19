from __future__ import annotations

import importlib
import importlib.util
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from panel.app import create_app
from panel.luna_operator_api import bp as luna_operator_bp


class MemoryData:
    def __init__(self):
        self.mapping = {
            "data/panel_pending_actions.json": [],
            "data/panel_audit_log.json": [],
            "data/panel_live_feed.json": [],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [],
            "data/source_overrides.json": {},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return "sha"


def _client(data: MemoryData):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test",
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
        }
    )
    app.register_blueprint(luna_operator_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_builder_module_exists_and_classifies_panel_change_requests():
    assert importlib.util.find_spec("panel.luna_builder") is not None
    module = importlib.import_module("panel.luna_builder")

    assert module.is_builder_request("یه ماژول برای گزارش بازار اضافه کن") is True
    assert module.is_builder_request("یه پنل جدید برای منابع بساز") is True
    assert module.is_builder_request("این بخش داشبورد رو حذف کن") is True
    assert module.is_builder_request("این خبر رو فارسی کن") is False
    assert module.is_builder_request("این منبع رو خاموش کن") is False


def test_builder_source_does_not_expose_arbitrary_shell_execution():
    for path in (Path("panel/luna_builder.py"), Path("panel/github_builder.py"), Path("panel/github_builder_release.py")):
        assert path.exists()
        source = path.read_text(encoding="utf-8")
        forbidden = ["subprocess", "os.system", "shell=True", "eval(", "exec("]
        for token in forbidden:
            assert token not in source


def test_builder_requires_explicit_confirmation_before_merge_or_deploy():
    assert importlib.util.find_spec("panel.luna_builder") is not None
    module = importlib.import_module("panel.luna_builder")

    policy = module.builder_policy()
    assert policy["requires_confirmation_before_merge"] is True
    assert policy["requires_green_ci"] is True
    assert policy["direct_production_edits"] is False
    assert policy["arbitrary_shell"] is False


def test_builder_request_from_chat_creates_pending_confirmation_without_mutating_code():
    data = MemoryData()
    client = _client(data)

    response = client.post(
        "/api/panel/luna/operator-chat",
        data={"message": "یه ماژول جدید برای گزارش انرژی اضافه کن"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "builder"
    assert payload["confirmation_required"] is True
    assert payload["action_id"]
    pending = data.mapping["data/panel_pending_actions.json"]
    assert len(pending) == 1
    assert pending[0]["action"] == "builder_prepare"
    assert pending[0]["status"] == "pending"
    assert pending[0]["expires_at"]


def test_confirmed_builder_request_invokes_real_builder_boundary_and_returns_draft_pr():
    data = MemoryData()
    client = _client(data)
    proposal = client.post(
        "/api/panel/luna/operator-chat",
        data={"message": "یه پنل جدید برای وضعیت منابع بساز"},
    ).get_json()

    class FakeBuilder:
        def start_change(self, request_text):
            assert "پنل جدید" in request_text
            return {
                "ok": True,
                "message": "Builder تغییر را روی branch جدا ساخت و Draft PR ایجاد کرد.",
                "summary_fa": "پنل وضعیت منابع ساخته شد.",
                "branch": "luna/change-test-source-health",
                "base_sha": "base-sha",
                "changed_files": ["tests/test_source_health.py", "panel/templates/source_health.html"],
                "test_commands": ["pytest -q tests/test_source_health.py"],
                "pull_request": {"number": 999, "url": "https://github.com/example/repo/pull/999", "draft": True},
            }

    with patch("panel.luna_operator_api.configured_builder", return_value=FakeBuilder()) as factory:
        response = client.post(f"/api/panel/luna/operator-confirm/{proposal['action_id']}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["pull_request"]["draft"] is True
    assert payload["pull_request"]["number"] == 999
    assert payload["branch"].startswith("luna/change-")
    factory.assert_called_once_with()
    assert data.mapping["data/panel_pending_actions.json"][0]["status"] == "completed"
    assert data.mapping["data/panel_audit_log.json"][0]["action"] == "builder_prepare"
