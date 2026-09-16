from pathlib import Path

from src.air_traffic import record_published_snapshot, snapshot_is_fresh


def test_snapshot_is_fresh_until_same_successful_digest_is_recorded(tmp_path):
    image = tmp_path / "air.png"
    image.write_bytes(b"fresh-image-bytes")
    state = tmp_path / "air-traffic-last.sha256"

    assert snapshot_is_fresh(image, state_path=state) is True
    record_published_snapshot(image, state_path=state)
    assert snapshot_is_fresh(image, state_path=state) is False

    image.write_bytes(b"different-live-image")
    assert snapshot_is_fresh(image, state_path=state) is True


def test_failed_or_unrecorded_send_does_not_consume_digest(tmp_path):
    image = tmp_path / "air.png"
    image.write_bytes(b"candidate-image")
    state = tmp_path / "air-traffic-last.sha256"

    assert snapshot_is_fresh(image, state_path=state) is True
    assert not state.exists()
    assert snapshot_is_fresh(image, state_path=state) is True
