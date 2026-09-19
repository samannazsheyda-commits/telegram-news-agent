from __future__ import annotations

import pytest

from src.newsroom_store_factory import StoreConfigurationError, create_runtime_store, selected_backend
from src.newsroom_v5_store import NewsroomV5Store


def test_missing_backend_keeps_legacy_github_default(monkeypatch):
    monkeypatch.delenv("NEWSROOM_STORE_BACKEND", raising=False)
    assert selected_backend() == "github"
    assert create_runtime_store() is None


def test_sqlite_backend_returns_v5_store_and_creates_parent(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "newsroom.db"
    monkeypatch.setenv("NEWSROOM_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("NEWSROOM_SQLITE_PATH", str(path))

    store = create_runtime_store()

    assert isinstance(store, NewsroomV5Store)
    assert path.exists()
    assert path.parent.exists()


def test_invalid_backend_fails_fast(monkeypatch):
    monkeypatch.setenv("NEWSROOM_STORE_BACKEND", "redis")
    with pytest.raises(StoreConfigurationError, match="NEWSROOM_STORE_BACKEND"):
        selected_backend()
