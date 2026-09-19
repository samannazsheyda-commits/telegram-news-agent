from __future__ import annotations

import os

from flask import abort, render_template

from panel.app import create_app as create_legacy_app, login_required
from panel.newsroom_v5_api import bp as newsroom_v5_bp
from panel.newsroom_v5_events_api import bp as newsroom_v5_events_bp
from src.newsroom_store_factory import create_runtime_store, selected_backend
from src.newsroom_v5_events import NewsroomEventBroker


def _enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(config: dict | None = None):
    config = dict(config or {})
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

    broker = config.get("NEWSROOM_V5_EVENTS") or NewsroomEventBroker(max_events=512)
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
            auto_publish_enabled=app.config.get("NEWSROOM_AUTO_PUBLISH_ENABLED", False),
        )

    return app
