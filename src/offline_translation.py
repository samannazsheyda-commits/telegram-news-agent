from __future__ import annotations

import os
from pathlib import Path
from threading import Lock


DEFAULT_MODEL_DIR = Path("/var/lib/bikhabar/models/argos-en-fa")
_REQUIRED_FILES = (
    "model/config.json",
    "model/model.bin",
    "sentencepiece.model",
)


class OfflinePersianTranslator:
    """Lazy low-memory English→Persian translator backed by Argos + CTranslate2.

    The previous QuickMT model was too large for Bikhabar's 1 GB VPS and could
    be killed by the kernel as soon as inference started.  The Argos EN→FA
    package is substantially smaller and uses the CTranslate2 runtime already
    shipped with the agent.
    """

    def __init__(self, model_dir: str | Path | None = None):
        self.model_dir = Path(model_dir or os.environ.get("OFFLINE_TRANSLATOR_MODEL_DIR", DEFAULT_MODEL_DIR))
        self._translator = None
        self._sp = None
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

                self._sp = spm.SentencePieceProcessor(model_file=str(self.model_dir / "sentencepiece.model"))
                self._translator = ctranslate2.Translator(
                    str(self.model_dir / "model"),
                    device="cpu",
                    compute_type="int8",
                    inter_threads=1,
                    intra_threads=1,
                )
            except Exception as exc:
                print(f"OFFLINE_TRANSLATOR_LOAD_FAILED type={type(exc).__name__} error={exc}", flush=True)
                self._translator = None
                self._sp = None
                return False
        return True

    def translate(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw or not self._load():
            return ""
        try:
            source_tokens = self._sp.encode(raw, out_type=str)
            if not source_tokens:
                return ""
            result = self._translator.translate_batch(
                [source_tokens],
                beam_size=1,
                max_decoding_length=256,
                replace_unknowns=True,
            )
            if not result or not result[0].hypotheses:
                return ""
            translated = self._sp.decode(result[0].hypotheses[0]).strip()
            if translated:
                print("OFFLINE_TRANSLATION_OK backend=argos-en-fa", flush=True)
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
