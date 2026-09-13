from pathlib import Path

from src.offline_translation import OfflinePersianTranslator


def test_default_offline_model_is_compact_argos_layout(monkeypatch):
    monkeypatch.delenv("OFFLINE_TRANSLATOR_MODEL_DIR", raising=False)
    translator = OfflinePersianTranslator()
    assert translator.model_dir == Path("/var/lib/bikhabar/models/argos-en-fa")


def test_argos_layout_is_available_without_quickmt_files(tmp_path):
    model_dir = tmp_path / "argos-en-fa"
    (model_dir / "model").mkdir(parents=True)
    (model_dir / "model" / "model.bin").write_bytes(b"model")
    (model_dir / "model" / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "sentencepiece.model").write_bytes(b"spm")
    translator = OfflinePersianTranslator(model_dir)
    assert translator.available is True


def test_legacy_argos_ct2_layout_without_config_is_available(tmp_path):
    model_dir = tmp_path / "argos-en-fa"
    (model_dir / "model").mkdir(parents=True)
    (model_dir / "model" / "model.bin").write_bytes(b"legacy-ct2-model")
    (model_dir / "sentencepiece.model").write_bytes(b"spm")

    translator = OfflinePersianTranslator(model_dir)

    assert translator.available is True


def test_argos_bpe_layout_is_available(tmp_path):
    model_dir = tmp_path / "argos-en-fa"
    (model_dir / "model").mkdir(parents=True)
    (model_dir / "model" / "model.bin").write_bytes(b"model")
    (model_dir / "model" / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "bpe.model").write_text("#version: 0.2\n", encoding="utf-8")
    translator = OfflinePersianTranslator(model_dir)
    assert translator.available is True


def test_installer_downloads_compact_argos_package():
    script = Path("deploy/install-offline-translator.sh").read_text(encoding="utf-8")
    assert "translate-en_fa-1_5.argosmodel" in script
    assert "quickmt/quickmt-en-fa" not in script


def test_installer_accepts_argos_bpe_packages():
    script = Path("deploy/install-offline-translator.sh").read_text(encoding="utf-8")
    assert "bpe.model" in script


def test_installer_does_not_require_modern_ct2_config_json():
    script = Path("deploy/install-offline-translator.sh").read_text(encoding="utf-8")
    assert '[[ -f "${MODEL_DIR}/model/config.json" ]]' not in script
    assert '[[ -s "${INSTALL_DIR}/model/config.json" ]]' not in script
    assert 'if not (model_dir / "config.json").is_file()' not in script
