from __future__ import annotations

import os
from pathlib import Path
from threading import Lock


DEFAULT_MODEL_DIR = Path("/var/lib/bikhabar/models/quickmt-en-fa")
_REQUIRED_FILES = (
    "config.json",
    "model.bin",
    "source_vocabulary.json",
    "target_vocabulary.json",
    "src.spm.model",
    "tgt.spm.model",
)


class OfflinePersianTranslator:
    """Lazy CPU English→Persian translator backed by QuickMT + CTranslate2."""

    def __init__(self, model_dir: str | Path | None = None):
        self.model_dir = Path(model_dir or os.environ.get("OFFLINE_TRANSLATOR_MODEL_DIR", DEFAULT_MODEL_DIR))
        self._translator = None
        self._source_sp = None
        self._target_sp = None
        self._lock = Lock()

    @property
    def available(self) -> bool:
        return all((self.model_dir / name).is_file() for name in _REQUIRED_FILES)

    def _load(self) -> bool:
        if self._translator is not None:
            return True
        if not self.available:
            return False
        with self._lock:
            if self._translator is not None:
                return True
            try:
                import ctranslate2
                import sentencepiece as spm

                self._source_sp = spm.SentencePieceProcessor(model_file=str(self.model_dir / "src.spm.model"))
                self._target_sp = spm.SentencePieceProcessor(model_file=str(self.model_dir / "tgt.spm.model"))
                self._translator = ctranslate2.Translator(
                    str(self.model_dir),
                    device="cpu",
                    compute_type="int8",
                    inter_threads=1,
                    intra_threads=1,
                )
            except Exception as exc:
                print(f"OFFLINE_TRANSLATOR_LOAD_FAILED type={type(exc).__name__} error={exc}", flush=True)
                self._translator = None
                self._source_sp = None
                self._target_sp = None
                return False
        return True

    def translate(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw or not self._load():
            return ""
        try:
            source_tokens = self._source_sp.encode(raw, out_type=str)
            if not source_tokens:
                return ""
            result = self._translator.translate_batch(
                [source_tokens],
                beam_size=5,
                max_decoding_length=384,
                repetition_penalty=1.05,
            )
            if not result or not result[0].hypotheses:
                return ""
            translated = self._target_sp.decode(result[0].hypotheses[0]).strip()
            if translated:
                print("OFFLINE_TRANSLATION_OK backend=quickmt-en-fa", flush=True)
            return translated
        except Exception as exc:
            print(f"OFFLINE_TRANSLATION_FAILED type={type(exc).__name__} error={exc}", flush=True)
            return ""


_default_translator: OfflinePersianTranslator | None = None
_default_lock = Lock()


def get_offline_translator() -> OfflinePersianTranslator:
    global _default_translator
    if _default_translator is None:
        with _default_lock:
            if _default_translator is None:
                _default_translator = OfflinePersianTranslator()
    return _default_translator


def translate_to_fa_offline(text: str) -> str:
    return get_offline_translator().translate(text)
