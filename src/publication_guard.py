from __future__ import annotations

import json
import os
from pathlib import Path


def settings_path() -> Path:
    data_dir = str(os.environ.get("DATA_DIR") or "data").strip() or "data"
    return Path(data_dir) / "newsroom_settings.json"


def publication_paused(path: str | Path | None = None) -> bool:
    target = Path(path) if path is not None else settings_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return isinstance(value, dict) and bool(value.get("emergency_lock", False))


def require_publication_open(path: str | Path | None = None) -> None:
    if publication_paused(path):
        raise RuntimeError("publication_paused")
