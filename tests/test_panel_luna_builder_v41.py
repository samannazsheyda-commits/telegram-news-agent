from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path


def test_builder_module_exists_and_classifies_panel_change_requests():
    assert importlib.util.find_spec("panel.luna_builder") is not None
    module = importlib.import_module("panel.luna_builder")

    assert module.is_builder_request("یه ماژول برای گزارش بازار اضافه کن") is True
    assert module.is_builder_request("یه پنل جدید برای منابع بساز") is True
    assert module.is_builder_request("این بخش داشبورد رو حذف کن") is True
    assert module.is_builder_request("این خبر رو فارسی کن") is False
    assert module.is_builder_request("این منبع رو خاموش کن") is False


def test_builder_source_does_not_expose_arbitrary_shell_execution():
    path = Path("panel/luna_builder.py")
    assert path.exists()
    source = path.read_text(encoding="utf-8")

    forbidden = ["subprocess", "os.system", "shell=True", "eval(", "exec("]
    for token in forbidden:
        assert token not in source


def test_builder_requires_explicit_confirmation_before_merge_or_deploy():
    assert importlib.util.find_spec("panel.luna_builder") is not None
    module = importlib.import_module("panel.luna_builder")

    policy = module.builder_policy()
    assert policy["requires_confirmation_before_merge"] is True
    assert policy["requires_green_ci"] is True
    assert policy["direct_production_edits"] is False
    assert policy["arbitrary_shell"] is False
