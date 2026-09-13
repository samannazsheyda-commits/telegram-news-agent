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
