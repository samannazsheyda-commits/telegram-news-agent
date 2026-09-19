from __future__ import annotations

from copy import deepcopy

from bs4 import BeautifulSoup

from panel.app import create_app


class MemoryData:
    def __init__(self, *, luna_ready: bool = False):
        story = {
            "id": "story-ux-1",
            "item_id": "story-ux-1",
            "news_key": "story-ux-1",
            "source": "ClashReport",
            "source_url": "https://example.com/story-ux-1",
            "original_title": "Original English headline",
            "persian_title": "عنوان فارسی آماده انتشار",
            "persian_body": "متن فارسی آماده انتشار است.",
            "panel_status": "new",
            "updated_at": "2026-09-19T07:00:00+00:00",
        }
        if luna_ready:
            story.update(
                final_persian_title="عنوان نهایی Luna",
                final_persian_body="متن نهایی Luna",
                luna_translation_status="passed",
            )
        self.mapping = {
            "data/panel_live_feed.json": [story],
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "data/custom_sources.json": [],
            "data/source_overrides.json": {},
            "state.json": {"daily_published": 0, "daily_limit": 35},
        }

    def read_json(self, path, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path, value, sha, message):
        del sha, message
        self.mapping[path] = deepcopy(value)
        return "memory-sha"


def render_dashboard(data: MemoryData) -> BeautifulSoup:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "WTF_CSRF_ENABLED": False,
            "PANEL_PASSWORD_HASH": "x",
            "DATA_BACKEND": data,
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    response = client.get("/")
    assert response.status_code == 200
    return BeautifulSoup(response.get_data(as_text=True), "html.parser")


def test_luna_publish_button_is_visible_but_disabled_until_luna_copy_is_ready():
    soup = render_dashboard(MemoryData(luna_ready=False))

    publish = soup.select_one('[data-v4-action="publish-luna"]')
    translate = soup.select_one('[data-v4-action="translate-luna"]')

    assert publish is not None
    assert publish.has_attr("disabled")
    assert publish.get("aria-disabled") == "true"
    assert "انتشار نسخه Luna" in publish.get_text(" ", strip=True)
    assert translate is not None
    assert translate.get_text(" ", strip=True) == "ترجمه با Luna"


def test_luna_publish_button_enables_only_when_quality_passed_copy_exists():
    soup = render_dashboard(MemoryData(luna_ready=True))

    publish = soup.select_one('[data-v4-action="publish-luna"]')
    translate = soup.select_one('[data-v4-action="translate-luna"]')

    assert publish is not None
    assert not publish.has_attr("disabled")
    assert publish.get("aria-disabled") == "false"
    assert translate is not None
    assert translate.get_text(" ", strip=True) == "ترجمه با Luna"
