from __future__ import annotations

from pathlib import Path


SW = (Path(__file__).resolve().parents[1] / "panel/static/sw.js").read_text(encoding="utf-8")


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


def test_app_shell_navigation_has_network_first_cached_fallback_and_update_signal():
    assert "networkFirstShell" in SW
    assert "caches.match('/v5')" in SW
    assert "NEW_VERSION_AVAILABLE" in SW
