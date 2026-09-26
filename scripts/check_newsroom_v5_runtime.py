from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


REQUIRED_TABLES = {
    "stories", "translations", "editorial_decisions", "publications",
    "story_tombstones", "sources", "jobs", "luna_conversations", "audit_log", "events",
}

REQUIRED_FLAGS = {
    "NEWSROOM_STORE_BACKEND": {"github", "sqlite"},
    "NEWSROOM_V5_SHADOW_PIPELINE": {"true", "false"},
    "NEWSROOM_V5_UI_ENABLED": {"true", "false"},
    "NEWSROOM_AUTO_PUBLISH_ENABLED": {"true", "false"},
}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def read_env_file(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def probe_sse(public_url: str, session_cookie: str, *, session=None, timeout: float = 5.0) -> dict:
    """Open the authenticated SSE stream through the public proxy and read the preamble."""
    if session is None:
        import requests as session
    url = public_url.rstrip("/") + "/api/v5/events"
    try:
        response = session.get(
            url,
            headers={"Accept": "text/event-stream", "Cookie": f"session={session_cookie}"},
            stream=True,
            timeout=(timeout, timeout),
            allow_redirects=False,
        )
    except Exception as exc:
        return {"ok": False, "error": f"sse_request_failed:{type(exc).__name__}"}
    try:
        content_type = str(response.headers.get("Content-Type") or "")
        if response.status_code != 200 or not content_type.startswith("text/event-stream"):
            return {"ok": False, "status": response.status_code, "error": "sse_not_event_stream"}
        try:
            first = next(iter(response.iter_content(chunk_size=None)), b"")
        except Exception as exc:
            return {"ok": False, "status": response.status_code, "error": f"sse_stream_stalled:{type(exc).__name__}"}
        if not first:
            return {"ok": False, "status": response.status_code, "error": "sse_stream_buffered_or_closed"}
        return {"ok": True, "status": response.status_code}
    finally:
        response.close()


def check_runtime(
    db_path: str | Path,
    *,
    public_url: str = "",
    env: Mapping[str, str] | None = None,
    session_cookie: str = "",
) -> dict:
    env = dict(os.environ if env is None else env)
    path = Path(db_path).expanduser()
    report = {
        "ok": True,
        "db_path": str(path),
        "db_exists": path.is_file(),
        "parent_writable": os.access(path.parent if path.parent.exists() else path.parent.parent, os.W_OK),
        "journal_mode": None,
        "foreign_keys": None,
        "missing_tables": [],
        "https_ready": None,
        "flags": {},
        "sse": None,
        "errors": [],
        "warnings": [],
    }

    for name, allowed in REQUIRED_FLAGS.items():
        raw = env.get(name)
        if raw is None or not str(raw).strip():
            report["errors"].append(f"flag_not_explicit:{name}")
            continue
        value = str(raw).strip().lower()
        report["flags"][name] = value
        if value not in allowed:
            report["errors"].append(f"invalid_flag:{name}")
    if report["flags"].get("NEWSROOM_AUTO_PUBLISH_ENABLED") == "true":
        report["warnings"].append("auto_publish_enabled")
    if report["flags"].get("NEWSROOM_V5_UI_ENABLED") == "true" and report["flags"].get("NEWSROOM_STORE_BACKEND") != "sqlite":
        report["errors"].append("v5_ui_requires_sqlite_backend")

    if public_url:
        report["https_ready"] = urlparse(public_url).scheme.lower() == "https"
        if not report["https_ready"]:
            report["errors"].append("public_url_is_not_https_voice_capture_may_be_limited")
        elif not _truthy(env.get("PANEL_COOKIE_SECURE")):
            report["warnings"].append("https_without_secure_session_cookie")
        if session_cookie:
            report["sse"] = probe_sse(public_url, session_cookie)
            if not report["sse"]["ok"]:
                report["errors"].append("sse_through_proxy_failed")
        else:
            report["warnings"].append("sse_proxy_probe_skipped_no_session_cookie")

    if not path.is_file():
        report["errors"].append("sqlite_database_missing")
        report["ok"] = False
        return report

    try:
        uri = f"file:{path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            report["journal_mode"] = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            # foreign_keys is connection-local and defaults off for this read-only
            # inspection connection; report schema integrity separately.
            report["foreign_keys"] = [
                dict(zip(("id", "seq", "table", "from", "to", "on_update", "on_delete", "match"), row))
                for row in conn.execute("PRAGMA foreign_key_list(translations)").fetchall()
            ]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            report["missing_tables"] = sorted(REQUIRED_TABLES - tables)
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
            report["quick_check"] = integrity
        finally:
            conn.close()
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"sqlite_read_failed:{type(exc).__name__}:{exc}")
        return report

    if report["journal_mode"] != "wal":
        report["errors"].append("journal_mode_is_not_wal")
    if report["missing_tables"]:
        report["errors"].append("required_tables_missing")
    if report.get("quick_check") != "ok":
        report["errors"].append("sqlite_quick_check_failed")
    report["ok"] = not report["errors"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Newsroom V5 runtime preflight")
    parser.add_argument("--db", default=os.environ.get("NEWSROOM_SQLITE_PATH", "/var/lib/bikhabar/newsroom-v5.db"))
    parser.add_argument("--public-url", default=os.environ.get("PANEL_PUBLIC_URL", ""))
    parser.add_argument("--env-file", default="", help="Check flags from this env file instead of the process env")
    parser.add_argument("--session-cookie", default=os.environ.get("PANEL_SESSION_COOKIE", ""),
                        help="Authenticated panel session cookie used to probe SSE through the proxy")
    args = parser.parse_args()
    env = read_env_file(args.env_file) if args.env_file else None
    report = check_runtime(args.db, public_url=args.public_url, env=env, session_cookie=args.session_cookie)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
