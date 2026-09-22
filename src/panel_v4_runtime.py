from __future__ import annotations

import json
import os
from pathlib import Path

from .newsroom_v3.production import run_once as run_v3_base


def _read_settings(data_dir: str | Path) -> dict:
    default_path = Path(data_dir) / "newsroom_settings.json"
    path = Path(os.environ.get("NEWSROOM_SETTINGS_PATH", str(default_path)))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def run_v3_with_panel_settings(*, data_dir: str | Path = "data", daily_limit: int | None = None, **kwargs):
    settings = _read_settings(data_dir)
    if daily_limit is None:
        try:
            daily_limit = int(settings.get("daily_limit", 35))
        except (TypeError, ValueError):
            daily_limit = 35
    daily_limit = max(1, min(100, int(daily_limit)))
    return run_v3_base(data_dir=data_dir, daily_limit=daily_limit, **kwargs)
