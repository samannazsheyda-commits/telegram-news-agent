from PIL import Image, ImageDraw

from src.air_traffic_publish_guard import record_published_snapshot, snapshot_is_fresh


def _image(path, *, map_mark: str, footer_mark: str = "footer"):
    image = Image.new("RGB", (1080, 1920), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), map_mark, fill="black")
    draw.text((20, 1700), footer_mark, fill="black")
    image.save(path, "PNG")


def test_snapshot_is_fresh_until_same_successful_map_digest_is_recorded(tmp_path):
    image = tmp_path / "air.png"
    state = tmp_path / "air-traffic-last.sha256"
    _image(image, map_mark="map-a", footer_mark="00:00:01")

    assert snapshot_is_fresh(image, state_path=state) is True
    record_published_snapshot(image, state_path=state)
    assert snapshot_is_fresh(image, state_path=state) is False

    # Timestamp/footer changes alone must not make the same map look fresh.
    _image(image, map_mark="map-a", footer_mark="00:00:59")
    assert snapshot_is_fresh(image, state_path=state) is False

    _image(image, map_mark="map-b", footer_mark="00:00:59")
    assert snapshot_is_fresh(image, state_path=state) is True


def test_failed_or_unrecorded_send_does_not_consume_digest(tmp_path):
    image = tmp_path / "air.png"
    state = tmp_path / "air-traffic-last.sha256"
    _image(image, map_mark="candidate")

    assert snapshot_is_fresh(image, state_path=state) is True
    assert not state.exists()
    assert snapshot_is_fresh(image, state_path=state) is True
