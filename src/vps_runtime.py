from __future__ import annotations

import json
import os
from pathlib import Path

from . import newsroom_hybrid_runtime as hybrid
from . import runtime_v13 as v13


DEFAULT_RUNTIME_ROOT = Path("/var/lib/bikhabar/runtime")


def runtime_root() -> Path:
    return Path(os.environ.get("BIKHABAR_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT)))


def newsroom_settings_path() -> Path:
    return Path(
        os.environ.get(
            "NEWSROOM_SETTINGS_PATH",
            str(runtime_root() / "data" / "newsroom_settings.json"),
        )
    )


def panel_command_dir() -> Path:
    return Path(
        os.environ.get(
            "PANEL_COMMAND_DIR",
            str(runtime_root() / "panel_commands"),
        )
    )


def _process_panel_commands() -> int:
    command_dir = panel_command_dir()
    if not command_dir.exists():
        return 0
    processed = 0
    for path in sorted(command_dir.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            hybrid.apply_panel_command(path)
            processed += 1
        except Exception as exc:
            print(
                f"PANEL_COMMAND_FAILED file={path.name} error={type(exc).__name__}:{exc}",
                flush=True,
            )
    return processed


def install_vps_paths() -> None:
    root = runtime_root()
    (root / "data").mkdir(parents=True, exist_ok=True)
    panel_command_dir().mkdir(parents=True, exist_ok=True)
    v13._NEWSROOM_SETTINGS_PATH = newsroom_settings_path()
    hybrid._process_panel_commands = _process_panel_commands


def main() -> int:
    install_vps_paths()
    poll_seconds = max(1, int(os.environ.get("POLL_SECONDS", "5")))
    session_seconds = int(os.environ.get("SESSION_SECONDS", "0"))
    print(
        json.dumps(
            {
                "mode": "vps-first",
                "runtime_root": str(runtime_root()),
                "poll_seconds": poll_seconds,
                "continuous": session_seconds <= 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return hybrid.monitor(
        shadow=False,
        poll_seconds=poll_seconds,
        session_seconds=session_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
