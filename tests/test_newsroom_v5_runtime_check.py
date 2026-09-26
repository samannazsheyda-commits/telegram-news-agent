from __future__ import annotations

import importlib.util
from pathlib import Path

from src.newsroom_v5_store import NewsroomV5Store

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_runtime", ROOT / "scripts" / "check_newsroom_v5_runtime.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

FLAGS = {
    "NEWSROOM_STORE_BACKEND": "sqlite",
    "NEWSROOM_V5_SHADOW_PIPELINE": "true",
    "NEWSROOM_V5_UI_ENABLED": "false",
    "NEWSROOM_AUTO_PUBLISH_ENABLED": "false",
}


def _db(tmp_path):
    path = tmp_path / "v5.db"
    NewsroomV5Store(path).close()
    return path


def test_ready_runtime_passes_with_explicit_flags(tmp_path):
    report = check.check_runtime(_db(tmp_path), env=dict(FLAGS))
    assert report["ok"] is True, report["errors"]
    assert report["journal_mode"] == "wal"
    assert report["flags"]["NEWSROOM_AUTO_PUBLISH_ENABLED"] == "false"


def test_missing_flags_are_reported_not_assumed(tmp_path):
    env = dict(FLAGS)
    env.pop("NEWSROOM_V5_UI_ENABLED")
    report = check.check_runtime(_db(tmp_path), env=env)
    assert report["ok"] is False
    assert "flag_not_explicit:NEWSROOM_V5_UI_ENABLED" in report["errors"]


def test_invalid_flag_value_fails(tmp_path):
    report = check.check_runtime(_db(tmp_path), env={**FLAGS, "NEWSROOM_STORE_BACKEND": "postgres"})
    assert "invalid_flag:NEWSROOM_STORE_BACKEND" in report["errors"]


def test_auto_publish_on_is_surfaced_as_warning(tmp_path):
    report = check.check_runtime(_db(tmp_path), env={**FLAGS, "NEWSROOM_AUTO_PUBLISH_ENABLED": "true"})
    assert "auto_publish_enabled" in report["warnings"]


def test_http_public_url_blocks_voice_and_https_cookie_flag_checked(tmp_path):
    db = _db(tmp_path)
    http = check.check_runtime(db, env=dict(FLAGS), public_url="http://1.2.3.4")
    assert http["https_ready"] is False
    assert "public_url_is_not_https_voice_capture_may_be_limited" in http["errors"]

    https = check.check_runtime(db, env={**FLAGS, "PANEL_COOKIE_SECURE": "0"}, public_url="https://panel.example")
    assert https["https_ready"] is True
    assert "https_without_secure_session_cookie" in https["warnings"]


def test_sse_probe_requires_stream_to_open_immediately(tmp_path):
    class Response:
        def __init__(self, content_type, chunks):
            self.status_code = 200
            self.headers = {"Content-Type": content_type}
            self._chunks = chunks

        def iter_content(self, chunk_size=None):
            yield from self._chunks

        def close(self):
            pass

    class Session:
        def __init__(self, response):
            self.response = response

        def get(self, *_a, **_k):
            return self.response

    ok = check.probe_sse("https://panel.example", "cookie", session=Session(Response("text/event-stream", [b": connected\n\n"])))
    assert ok == {"ok": True, "status": 200}
    bad = check.probe_sse("https://panel.example", "cookie", session=Session(Response("text/html", [b"<html>"])))
    assert bad["ok"] is False


def test_runtime_check_is_read_only(tmp_path):
    missing = tmp_path / "absent.db"
    report = check.check_runtime(missing, env=dict(FLAGS))
    assert report["ok"] is False
    assert not missing.exists()
