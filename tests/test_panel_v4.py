from __future__ import annotations

from copy import deepcopy

from panel.app import create_app


class MemoryData:
    def __init__(self, mapping: dict[str, object]):
        self.mapping = deepcopy(mapping)

    def read_json(self, path: str, default):
        return deepcopy(self.mapping.get(path, default)), None

    def write_json(self, path: str, value, sha, message: str):
        self.mapping[path] = deepcopy(value)
        return "memory-sha"


def _live_rows(count: int = 3) -> list[dict]:
    rows: list[dict] = []
    for index in range(count):
        rows.append(
            {
                "id": f"story-{index}",
                "news_key": f"news-{index}",
                "source": "Reuters",
                "source_url": f"https://example.com/{index}",
                "original_title": f"Original headline {index}",
                "original_summary": f"Original summary {index}",
                "machine_translation": f"ترجمه ماشینی {index}",
                "panel_status": "new",
                "updated_at": f"2026-09-18T10:{index:02d}:00+00:00",
            }
        )
    return rows


def _client(*, live_count: int = 3):
    data = MemoryData(
        {
            "data/panel_live_feed.json": _live_rows(live_count),
            "data/editorial_queue.json": [],
            "data/editorial_history.json": [],
            "state.json": {
                "daily_limit": 35,
                "special_daily_limit": 5,
                "daily_published": 12,
                "special_published": 2,
            },
        }
    )
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "WTF_CSRF_ENABLED": False,
            "DATA_BACKEND": data,
        }
    )
    client = app.test_client()
    with client.session_transaction() as session:
        session["admin"] = True
    return client


def test_dashboard_is_v4_control_center_without_air_traffic():
    response = _client().get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "Newsroom V4" in html
    assert "مرکز کنترل بی‌خبر" in html
    assert "Luna" in html
    assert "تنظیمات" in html
    assert "سلامت سیستم" in html
    assert "air-traffic" not in html
    assert "ترافیک هوایی" not in html


def test_dashboard_binds_initial_intake_to_30_cards():
    response = _client(live_count=45).get("/")
    html = response.get_data(as_text=True)

    assert html.count('data-v4-story-card="1"') == 30
    assert "Original headline 44" in html
    assert "Original headline 15" in html
    assert "Original headline 14" not in html


def test_pre_luna_story_requires_preview_before_publish():
    response = _client().get("/")
    html = response.get_data(as_text=True)

    assert "ارسال به Luna" in html
    assert "🌐 ترجمه ماشینی" in html
    assert "🧠 Luna" in html
    assert 'data-action="publish"' not in html


def test_dashboard_shows_regular_and_special_quota():
    response = _client().get("/")
    html = response.get_data(as_text=True)

    assert "12 / 35" in html
    assert "2 / 5" in html
    assert "23" in html
