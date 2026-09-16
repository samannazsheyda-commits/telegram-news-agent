from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

import src.air_traffic_publish_guard as guard
from src.air_traffic_live import LiveAirTrafficSnapshot


def _snapshot() -> LiveAirTrafficSnapshot:
    rows = [
        {
            "hex": f"preview-{i}",
            "lat": 30.0 + (i * 0.02),
            "lon": 51.0,
            "track": 90,
            "seen_pos": 1,
        }
        for i in range(guard.reference.MIN_PUBLISH_AIRCRAFT)
    ]
    return LiveAirTrafficSnapshot(
        aircraft=rows,
        source_counts={"opensky": len(rows), "point_network": 0},
        healthy_centers=0,
        total_centers=21,
        captured_at=datetime(2026, 9, 16, 10, 30, tzinfo=timezone.utc),
    )


def _render(rows, output_path, *, now=None):
    assert rows
    image = Image.new("RGB", (1080, 1920), "white")
    image.save(output_path, "PNG")
    return Path(output_path)


def test_preview_renders_strict_live_snapshot_without_luna_or_telegram(monkeypatch, tmp_path):
    monkeypatch.setattr(guard.reference, "filter_visible_aircraft", lambda rows, **kwargs: rows)
    monkeypatch.setattr(guard.reference, "render_air_traffic_map", _render)
    monkeypatch.setattr(guard.reference, "_validate_rendered_image", lambda path: None)

    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not call Luna or Telegram")

    monkeypatch.setattr(guard, "LunaAirTrafficReporter", forbidden)
    monkeypatch.setattr(guard.base, "send_telegram_photo", forbidden)

    output = tmp_path / "preview.png"
    result = guard.render_strict_live_preview(output_path=output, snapshot=_snapshot())

    assert result == output
    assert output.is_file()


def test_preview_workflow_builds_artifact_without_publish_secrets():
    workflow_path = Path(".github/workflows/air-traffic-preview.yml")
    assert workflow_path.is_file()
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "python -m src.air_traffic_publish_guard --preview" in workflow
    assert "actions/upload-artifact" in workflow
    assert "TELEGRAM_BOT_TOKEN" not in workflow
    assert "OPENAI_API_KEY" not in workflow


def test_air_traffic_smoke_workflow_uses_strict_live_preview_path():
    workflow = Path(".github/workflows/air-traffic-tests.yml").read_text(encoding="utf-8")

    assert "python -m src.air_traffic_publish_guard --preview" in workflow
    assert "python -m src.air_traffic_reference --output" not in workflow
    assert '"src/air_traffic_live.py"' in workflow
    assert '"src/air_traffic_publish_guard.py"' in workflow
    assert '"tests/test_air_traffic*.py"' in workflow
