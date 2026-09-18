from pathlib import Path


def test_luna_page_is_full_chat_with_voice_and_image_controls():
    html = Path("panel/templates/luna.html").read_text(encoding="utf-8")

    assert "فرمان‌های نمونه" not in html
    assert "نسخه‌های Luna" not in html
    assert 'id="v4LunaMic"' in html
    assert 'id="v4LunaImage"' in html
    assert 'id="v4LunaComposer"' in html
    assert 'id="v4LunaMessages"' in html


def test_service_worker_uses_v41_cache_and_no_legacy_shell_assets():
    sw = Path("panel/static/sw.js").read_text(encoding="utf-8")

    assert "bikhabar-newsroom-v4-1" in sw
    assert "newsroom-nav-v2.css" not in sw
    assert "newsroom-compact.css" not in sw
    assert "live.js" not in sw
    assert "air-traffic" not in sw.lower()


def test_v41_panel_ui_has_no_air_traffic_surface():
    paths = [
        Path("panel/templates/base.html"),
        Path("panel/templates/dashboard.html"),
        Path("panel/templates/system_health.html"),
        Path("panel/templates/settings_v4.html"),
        Path("panel/templates/luna.html"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "ترافیک هوایی" not in combined
    assert "air-traffic" not in combined.lower()
