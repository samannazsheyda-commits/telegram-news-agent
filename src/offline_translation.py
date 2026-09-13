from __future__ import annotations

import os
from pathlib import Path
from threading import Lock


DEFAULT_MODEL_DIR = Path("/var/lib/bikhabar/models/argos-en-fa")
_REQUIRED_MODEL_FILES = (
    "model/model.bin",
)


class OfflinePersianTranslator:
    """Lazy low-memory English→Persian translator backed by Argos + CTranslate2.

    Argos packages can use either SentencePiece or the older BPE tokenizer
    layout. Older Argos 1.5 packages also predate CTranslate2's config.json,
    so model.bin plus a supported tokenizer is the portable readiness check.
    CTranslate2 itself remains the final validator when the model is loaded.
    """

    def __init__(self, model_dir: str | Path | None = None):
        self.model_dir = Path(model_dir or os.environ.get("OFFLINE_TRANSLATOR_MODEL_DIR", DEFAULT_MODEL_DIR))
        self._translator = None
        self._mode = ""
        self._sp = None
        self._bpe = None
        self._normalizer = None
        self._source_tokenizer = None
        self._target_detokenizer = None
        self._lock = Lock()

    @property
    def available(self) -> bool:
        model_ready = all((self.model_dir / name).is_file() for name in _REQUIRED_MODEL_FILES)
        tokenizer_ready = (
            (self.model_dir / "sentencepiece.model").is_file()
            or (self.model_dir / "bpe.model").is_file()
        )
        return model_ready and tokenizer_ready

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

                if (self.model_dir / "sentencepiece.model").is_file():
                    import sentencepiece as spm

                    self._sp = spm.SentencePieceProcessor(model_file=str(self.model_dir / "sentencepiece.model"))
                    self._mode = "sentencepiece"
                else:
                    from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
                    from subword_nmt.apply_bpe import BPE

                    self._normalizer = MosesPunctNormalizer(lang="en")
                    self._source_tokenizer = MosesTokenizer(lang="en")
                    self._target_detokenizer = MosesDetokenizer(lang="fa")
                    with (self.model_dir / "bpe.model").open("r", encoding="utf-8") as codes:
                        self._bpe = BPE(codes)
                    self._mode = "bpe"

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
                self._mode = ""
                self._sp = None
                self._bpe = None
                self._normalizer = None
                self._source_tokenizer = None
                self._target_detokenizer = None
                return False
        return True

    def _encode(self, raw: str) -> list[str]:
        if self._mode == "sentencepiece":
            return list(self._sp.encode(raw, out_type=str))
        if self._mode == "bpe":
            normalized = self._normalizer.normalize(raw)
            tokens = self._source_tokenizer.tokenize(normalized, return_str=False, escape=False)
            segmented = self._bpe.process_line(" ".join(tokens)).strip()
            return segmented.split() if segmented else []
        return []

    def _decode(self, tokens: list[str]) -> str:
        if self._mode == "sentencepiece":
            return str(self._sp.decode(tokens) or "").strip()
        if self._mode == "bpe":
            joined = " ".join(str(token) for token in tokens)
            merged = joined.replace("@@ ", "").replace("@@", "").strip()
            if not merged:
                return ""
            return str(self._target_detokenizer.detokenize(merged.split()) or "").strip()
        return ""

    def translate(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw or not self._load():
            return ""
        try:
            source_tokens = self._encode(raw)
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
            translated = self._decode(list(result[0].hypotheses[0]))
            if translated:
                print(f"OFFLINE_TRANSLATION_OK backend=argos-en-fa tokenizer={self._mode}", flush=True)
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
