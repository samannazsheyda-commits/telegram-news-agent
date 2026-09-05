from src import runtime_v2 as v2
from src import runtime_v5 as v5


def test_runtime_v5_keeps_configured_custom_sources_connected(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(v2, "_original_custom_fetch", lambda: [sentinel])
    monkeypatch.setattr(v5, "_fresh_x_installed", False)

    v5.install_fresh_x_policy()

    assert v2._original_custom_fetch() == [sentinel]
