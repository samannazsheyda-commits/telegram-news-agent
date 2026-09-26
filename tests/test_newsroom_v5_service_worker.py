from __future__ import annotations

from pathlib import Path


SW = (Path(__file__).resolve().parents[1] / "panel/static/newsroom-v5-sw.js").read_text(encoding="utf-8")


def test_v5_service_worker_versions_shell_cache_and_claims_clients():
    assert "bikhabar-newsroom-v5" in SW
    assert "newsroom-v5-app.js" in SW
    assert "newsroom-v5-review.js" in SW
    assert "newsroom-v5-app.css" in SW
    assert "self.clients.claim()" in SW
    assert "caches.delete" in SW


def test_api_and_sse_are_network_only_and_never_cached():
    assert "url.pathname.startsWith('/api/')" in SW
    assert "networkOnly" in SW
    assert "cache: 'no-store'" in SW
    assert "event.request.method !== 'GET'" in SW


def _app(tmp_path):
    from panel.app_v5 import create_app
    from src.newsroom_v5_store import NewsroomV5Store

    return create_app({
        "TESTING": True, "SECRET_KEY": "t", "WTF_CSRF_ENABLED": False,
        "NEWSROOM_V5_STORE": NewsroomV5Store(tmp_path / "n.db"), "NEWSROOM_V5_UI_ENABLED": True,
    })


def test_service_worker_is_served_with_deploy_version_and_scope_covering_the_shell(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "javascript" in response.mimetype
    assert "no-cache" in response.headers["Cache-Control"]
    body = response.get_data(as_text=True)
    version = app.config["V5_ASSET_VERSION"]
    assert len(version) >= 8
    assert f"const VERSION = '{version}'" in body
    assert "__V5_ASSET_VERSION__" not in body

    with client.session_transaction() as session:
        session["admin"] = True
    shell = client.get("/v5").get_data(as_text=True)
    assert f"newsroom-v5-app.js?v={version}" in shell
    assert f"newsroom-v5-review.js?v={version}" in shell
    assert f"newsroom-v5-app.css?v={version}" in shell
    app_js = (Path(__file__).resolve().parents[1] / "panel/static/newsroom-v5-app.js").read_text(encoding="utf-8")
    assert "register('/sw.js', { scope: '/v5' })" in app_js


def test_asset_version_changes_when_v5_assets_change(tmp_path, monkeypatch):
    import panel.app_v5 as app_v5

    first = app_v5.compute_asset_version()
    original = app_v5._asset_paths

    def with_extra():
        extra = tmp_path / "extra.js"
        extra.write_text("changed", encoding="utf-8")
        return [*original(), extra]

    monkeypatch.setattr(app_v5, "_asset_paths", with_extra)
    assert app_v5.compute_asset_version() != first


def test_update_banner_only_on_upgrade_and_redirects_never_cached_as_shell():
    assert "hadPreviousV5" in SW
    assert "if (hadPreviousV5)" in SW
    assert "!response.redirected" in SW


def test_legacy_assets_are_not_precached_by_v5_worker():
    assert "/static/luna-assistant.js" not in SW
    assert "/static/newsroom-v4.js" not in SW
    assert "url.pathname.startsWith('/static/newsroom-v5-')" in SW


def test_app_shell_navigation_has_network_first_cached_fallback_and_update_signal():
    assert "networkFirstShell" in SW
    assert "caches.match('/v5')" in SW
    assert "NEW_VERSION_AVAILABLE" in SW
