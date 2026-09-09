from pathlib import Path

from src import vps_runtime


def test_runtime_root_defaults_to_var_lib(monkeypatch):
    monkeypatch.delenv("BIKHABAR_RUNTIME_ROOT", raising=False)
    assert vps_runtime.runtime_root() == Path("/var/lib/bikhabar/runtime")


def test_runtime_paths_can_be_overridden(monkeypatch, tmp_path):
    root = tmp_path / "runtime"
    settings = root / "data" / "settings.json"
    commands = root / "commands"
    monkeypatch.setenv("BIKHABAR_RUNTIME_ROOT", str(root))
    monkeypatch.setenv("NEWSROOM_SETTINGS_PATH", str(settings))
    monkeypatch.setenv("PANEL_COMMAND_DIR", str(commands))
    assert vps_runtime.runtime_root() == root
    assert vps_runtime.newsroom_settings_path() == settings
    assert vps_runtime.panel_command_dir() == commands


def test_install_vps_paths_creates_local_runtime_and_patches_consumers(monkeypatch, tmp_path):
    root = tmp_path / "runtime"
    monkeypatch.setenv("BIKHABAR_RUNTIME_ROOT", str(root))
    monkeypatch.delenv("NEWSROOM_SETTINGS_PATH", raising=False)
    monkeypatch.delenv("PANEL_COMMAND_DIR", raising=False)

    original_settings = vps_runtime.v13._NEWSROOM_SETTINGS_PATH
    original_processor = vps_runtime.hybrid._process_panel_commands
    try:
        vps_runtime.install_vps_paths()
        assert (root / "data").is_dir()
        assert (root / "panel_commands").is_dir()
        assert vps_runtime.v13._NEWSROOM_SETTINGS_PATH == root / "data" / "newsroom_settings.json"
        assert vps_runtime.hybrid._process_panel_commands is vps_runtime._process_panel_commands
    finally:
        vps_runtime.v13._NEWSROOM_SETTINGS_PATH = original_settings
        vps_runtime.hybrid._process_panel_commands = original_processor
