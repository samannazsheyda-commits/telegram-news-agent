from __future__ import annotations

import hashlib
import os
from pathlib import Path

from flask import Response, abort, render_template

from panel.app import create_app as create_legacy_app, login_required
from panel.newsroom_v5_api import bp as newsroom_v5_bp
from panel.newsroom_v5_events_api import bp as newsroom_v5_events_bp
from src.newsroom_store_factory import create_runtime_store, selected_backend
from src.newsroom_v5_events import NewsroomEventBroker, SqliteEventLog


class _NullDataBackend:
    """Read-only empty legacy backend for isolated V5 tests/local boot."""

    def read_json(self, _path: str, default):
        return default, None

    def write_json(self, *_args, **_kwargs):
        raise RuntimeError("legacy_data_backend_is_read_only")

    def merge_records(self, _path: str, incoming: list[dict], _message: str) -> list[dict]:
        return list(incoming)

    def replace_records(self, _path: str, records: list[dict], _message: str) -> list[dict]:
        return list(records)

    def mark_news_seen(self, _news_key: str) -> None:
        return None


_STATIC = Path(__file__).resolve().parent / "static"


def _asset_paths() -> list[Path]:
    return sorted([_STATIC / "manifest.webmanifest", *_STATIC.glob("newsroom-v5-*")])


def compute_asset_version() -> str:
    digest = hashlib.sha256()
    for path in _asset_paths():
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(config: dict | None = None):
    config = dict(config or {})
    # V5 API tests and explicit local-store boots must not require a GitHub token.
    # Production keeps the normal legacy backend unless one is explicitly supplied.
    if config.get("TESTING") and config.get("NEWSROOM_V5_STORE") is not None and "DATA_BACKEND" not in config:
        config["DATA_BACKEND"] = _NullDataBackend()
    app = create_legacy_app(config)

    explicit_store = config.get("NEWSROOM_V5_STORE")
    backend = str(config.get("NEWSROOM_STORE_BACKEND") or os.environ.get("NEWSROOM_STORE_BACKEND", "github"))
    if explicit_store is not None:
        store = explicit_store
    elif selected_backend(backend) == "sqlite":
        db_path = config.get("NEWSROOM_SQLITE_PATH") or os.environ.get("NEWSROOM_SQLITE_PATH")
        store = create_runtime_store(backend="sqlite", path=db_path)
    else:
        store = None

    broker = config.get("NEWSROOM_V5_EVENTS")
    if broker is None:
        file_backed = store is not None and str(getattr(store, "path", ":memory:")) != ":memory:"
        broker = SqliteEventLog(store) if file_backed else NewsroomEventBroker(max_events=512)
    app.extensions["newsroom_v5_store"] = store
    app.extensions["newsroom_v5_events"] = broker
    app.config["NEWSROOM_STORE_BACKEND"] = selected_backend(backend)
    app.config["NEWSROOM_V5_UI_ENABLED"] = _enabled(
        config.get("NEWSROOM_V5_UI_ENABLED", os.environ.get("NEWSROOM_V5_UI_ENABLED", "false"))
    )
    app.config["NEWSROOM_V5_SHADOW_PIPELINE"] = _enabled(
        config.get("NEWSROOM_V5_SHADOW_PIPELINE", os.environ.get("NEWSROOM_V5_SHADOW_PIPELINE", "false"))
    )
    app.config["NEWSROOM_AUTO_PUBLISH_ENABLED"] = _enabled(
        config.get("NEWSROOM_AUTO_PUBLISH_ENABLED", os.environ.get("NEWSROOM_AUTO_PUBLISH_ENABLED", "false"))
    )

    app.register_blueprint(newsroom_v5_bp)
    app.register_blueprint(newsroom_v5_events_bp)
    app.config["V5_ASSET_VERSION"] = compute_asset_version()
    service_worker = (_STATIC / "newsroom-v5-sw.js").read_text(encoding="utf-8").replace(
        "__V5_ASSET_VERSION__", app.config["V5_ASSET_VERSION"]
    )

    @app.get("/sw.js")
    def newsroom_v5_service_worker():
        response = Response(service_worker, mimetype="application/javascript")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/v5")
    @login_required
    def newsroom_v5_shell():
        if not app.config.get("NEWSROOM_V5_UI_ENABLED"):
            abort(404)
        if app.extensions.get("newsroom_v5_store") is None:
            abort(503, description="Newsroom V5 requires NEWSROOM_STORE_BACKEND=sqlite")
        return render_template(
            "app_shell.html",
            newsroom_v5=True,
            v5_asset_version=app.config["V5_ASSET_VERSION"],
            auto_publish_enabled=app.config.get("NEWSROOM_AUTO_PUBLISH_ENABLED", False),
        )

    return app
