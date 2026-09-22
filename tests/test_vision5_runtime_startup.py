from __future__ import annotations

from types import SimpleNamespace


class TrackingStore:
    def __init__(self) -> None:
        self.initialize_calls = 0

    def initialize(self) -> None:
        self.initialize_calls += 1


def _parts(store: TrackingStore) -> dict:
    return {
        "store": store,
        "queue": object(),
        "google": object(),
        "model": object(),
        "telegram": object(),
    }


def test_runtime_service_startup_does_not_run_schema_migrations(monkeypatch):
    from bikhabar_v5 import runtime

    store = TrackingStore()
    monkeypatch.setattr(runtime, "_components", lambda _values: (object(), _parts(store)))
    monkeypatch.setattr(runtime, "_monitor", lambda _parts: {"ok": True})

    assert runtime.main(["monitor"], environ={}) == 0
    assert store.initialize_calls == 0


def test_init_db_command_runs_schema_migrations_once(monkeypatch):
    from bikhabar_v5 import runtime

    store = TrackingStore()
    monkeypatch.setattr(runtime, "_components", lambda _values: (object(), _parts(store)))

    assert runtime.main(["init-db"], environ={}) == 0
    assert store.initialize_calls == 1


def test_panel_worker_startup_does_not_run_schema_migrations(monkeypatch):
    from bikhabar_v5 import runtime

    store = TrackingStore()
    environment = SimpleNamespace(
        openai_api_key="secret",
        secret_key="s" * 32,
        admin_username="admin",
        admin_password_hash="hash",
    )
    monkeypatch.setattr(runtime, "_components", lambda _values: (environment, _parts(store)))
    monkeypatch.setattr(runtime, "LunaOperator", lambda **_kwargs: object())
    monkeypatch.setattr(runtime, "OpenAIAudioTranscriber", lambda **_kwargs: object())
    monkeypatch.setattr(runtime, "_builder", lambda _values, _environment: None)
    monkeypatch.setattr(runtime, "create_app", lambda **_kwargs: object())

    assert runtime.create_production_panel({}) is not None
    assert store.initialize_calls == 0
