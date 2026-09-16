from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import src.air_traffic_publish_guard as guard


def _rows():
    return [
        {"hex": f"a{i}", "lat": 30.0 + i * 0.01, "lon": 51.0, "track": 90, "seen_pos": 1}
        for i in range(guard.reference.MIN_PUBLISH_AIRCRAFT)
    ]


def _render(_rows, output_path, *, now=None):
    image = Image.new("RGB", (1080, 1920), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), "stable-live-map", fill="black")
    draw.text((20, 1700), str(now), fill="black")
    image.save(output_path, "PNG")
    return Path(output_path)


def test_fresh_snapshot_sends_once_and_duplicate_map_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(guard.reference, "fetch_live_aircraft", _rows)
    monkeypatch.setattr(guard.reference, "filter_visible_aircraft", lambda rows: rows)
    monkeypatch.setattr(guard.reference, "render_air_traffic_map", _render)
    monkeypatch.setattr(guard.reference, "_validate_rendered_image", lambda path: None)
    sent = []
    monkeypatch.setattr(guard.base, "send_telegram_photo", lambda *args, **kwargs: sent.append(args))

    state = tmp_path / "last.sha256"
    output = tmp_path / "air.png"
    first = guard.publish_fresh_air_traffic_snapshot(output_path=output, state_path=state)
    second = guard.publish_fresh_air_traffic_snapshot(output_path=output, state_path=state)

    assert first == output
    assert second is None
    assert len(sent) == 1
    assert state.is_file()


def test_failed_telegram_send_does_not_record_digest(monkeypatch, tmp_path):
    monkeypatch.setattr(guard.reference, "fetch_live_aircraft", _rows)
    monkeypatch.setattr(guard.reference, "filter_visible_aircraft", lambda rows: rows)
    monkeypatch.setattr(guard.reference, "render_air_traffic_map", _render)
    monkeypatch.setattr(guard.reference, "_validate_rendered_image", lambda path: None)

    def fail_send(*args, **kwargs):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(guard.base, "send_telegram_photo", fail_send)
    state = tmp_path / "last.sha256"

    with pytest.raises(RuntimeError, match="telegram down"):
        guard.publish_fresh_air_traffic_snapshot(output_path=tmp_path / "air.png", state_path=state)
    assert not state.exists()
