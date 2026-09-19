from __future__ import annotations

import os
from pathlib import Path

from .newsroom_v5_store import NewsroomV5Store


class StoreConfigurationError(RuntimeError):
    pass


def selected_backend(value: str | None = None) -> str:
    backend = str(value if value is not None else os.environ.get("NEWSROOM_STORE_BACKEND", "github")).strip().lower()
    if backend not in {"github", "sqlite"}:
        raise StoreConfigurationError("NEWSROOM_STORE_BACKEND must be 'github' or 'sqlite'")
    return backend


def sqlite_path(value: str | None = None) -> Path:
    raw = value if value is not None else os.environ.get("NEWSROOM_SQLITE_PATH", "/var/lib/bikhabar/newsroom-v5.db")
    path = Path(str(raw)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def create_runtime_store(*, backend: str | None = None, path: str | Path | None = None):
    if selected_backend(backend) == "github":
        return None
    target = sqlite_path(str(path) if path is not None else None)
    return NewsroomV5Store(target)
