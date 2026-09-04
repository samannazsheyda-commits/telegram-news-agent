import importlib
import sys

from werkzeug.security import generate_password_hash


def test_vercel_entrypoint_exposes_flask_app(monkeypatch):
    monkeypatch.setenv("PANEL_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PANEL_PASSWORD_HASH", generate_password_hash("test-pass"))
    monkeypatch.setenv("GITHUB_REPOSITORY", "samannazsheyda-commits/telegram-news-agent")
    monkeypatch.setenv("GITHUB_DATA_TOKEN", "test-token")
    sys.modules.pop("api.index", None)

    module = importlib.import_module("api.index")

    assert module.app.name == "panel.app"
    assert any(rule.rule == "/login" for rule in module.app.url_map.iter_rules())
