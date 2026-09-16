from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from . import air_traffic as base
from . import air_traffic_reference as reference
from .air_traffic_live import LiveAirTrafficSnapshot, fetch_strict_live_snapshot
from .air_traffic_luna import LunaAirTrafficReporter


STATE_FILE_NAME = "air_traffic_last_map.sha256"


def _default_state_path() -> Path:
    runtime_root = Path(os.environ.get("BIKHABAR_RUNTIME_ROOT", "data"))
    return runtime_root / "data" / STATE_FILE_NAME


def snapshot_digest(image_path: str | Path) -> str:
    """Hash only the live map area so changing timestamp text cannot fake freshness."""
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        map_height = min(reference.MAP_HEIGHT, rgb.height)
        map_region = rgb.crop((0, 0, rgb.width, map_height))
        digest = hashlib.sha256()
        digest.update(f"{map_region.width}x{map_region.height}:RGB".encode("ascii"))
        digest.update(map_region.tobytes())
        return digest.hexdigest()


def snapshot_is_fresh(image_path: str | Path, *, state_path: str | Path | None = None) -> bool:
    resolved_state = Path(state_path) if state_path is not None else _default_state_path()
    current = snapshot_digest(image_path)
    try:
        previous = resolved_state.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        previous = ""
    return current != previous


def record_published_snapshot(image_path: str | Path, *, state_path: str | Path | None = None) -> str:
    resolved_state = Path(state_path) if state_path is not None else _default_state_path()
    resolved_state.parent.mkdir(parents=True, exist_ok=True)
    digest = snapshot_digest(image_path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{resolved_state.name}.", dir=str(resolved_state.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(digest + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, resolved_state)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return digest


def _caption_with_luna_summary(captured_at: datetime, summary: str) -> str:
    base_caption = base.build_caption(captured_at)
    lines = base_caption.splitlines()
    if not lines:
        return summary
    return "\n".join([lines[0], summary, *lines[1:]])


def publish_fresh_air_traffic_snapshot(
    *,
    now: datetime | None = None,
    output_path: str | Path = "/tmp/iran-region-live-air-traffic.png",
    state_path: str | Path | None = None,
    snapshot: LiveAirTrafficSnapshot | None = None,
    reporter: LunaAirTrafficReporter | None = None,
) -> Path | None:
    live_snapshot = snapshot or fetch_strict_live_snapshot()
    visible = reference.filter_visible_aircraft(
        live_snapshot.aircraft,
        max_seen_seconds=60,
    )
    if len(visible) < reference.MIN_PUBLISH_AIRCRAFT:
        raise RuntimeError(
            f"insufficient fresh live aircraft for safe publication: {len(visible)} < {reference.MIN_PUBLISH_AIRCRAFT}"
        )

    captured_at = now or live_snapshot.captured_at
    summary = (reporter or LunaAirTrafficReporter()).build_summary(live_snapshot)
    caption = _caption_with_luna_summary(captured_at, summary)

    path = reference.render_air_traffic_map(visible, output_path, now=captured_at)
    reference._validate_rendered_image(path)

    if not snapshot_is_fresh(path, state_path=state_path):
        print("AIR_TRAFFIC_SKIP reason=duplicate_map_snapshot", flush=True)
        return None

    base.send_telegram_photo(
        path,
        caption,
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", "@bikhabaar"),
    )
    record_published_snapshot(path, state_path=state_path)
    print(
        "AIR_TRAFFIC_PUBLISHED fresh_map=1 "
        f"aircraft={len(visible)} coverage={live_snapshot.healthy_centers}/{live_snapshot.total_centers} luna=1",
        flush=True,
    )
    return path


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--output", default="/tmp/iran-region-live-air-traffic.png")
    args = parser.parse_args()
    if not args.publish:
        raise SystemExit("air_traffic_publish_guard only supports --publish")
    publish_fresh_air_traffic_snapshot(output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
