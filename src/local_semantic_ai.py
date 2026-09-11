from __future__ import annotations

import hashlib
import re
from dataclasses import replace

from .ai_newsroom import AIConfig, HuggingFaceNewsAI


_LOCAL_VECTOR_SIZE = 512
_LOCAL_DUPLICATE_THRESHOLD = 0.20
_STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "at", "on", "with", "and", "for", "from", "after", "by", "as",
    "its", "their", "says", "said", "forces", "aligned", "town",
    "از", "به", "در", "با", "و", "برای", "که", "را", "یک", "این", "آن", "گفت", "اعلام", "کرد",
}
_ALIAS_RULES = (
    (r"\bansar[\s-]?allah\b|\bhouthis?\b", "houthi"),
    (r"\biran[\s-]?backed\b", "iran backed"),
    (r"\bsaudi arabia\b|\bsaudi\b", "saudi"),
    (r"\bdonald trump\b|\bpresident trump\b", "trump"),
    (r"\bstrait of hormuz\b", "hormuz"),
    (r"\bred sea\b", "redsea"),
    (r"\breached\b|\barrived?\b|\bentered\b|\benters\b|\badvance(?:d|s)?\b", "arrive"),
    (r"\bair[\s-]?strikes?\b|\bstruck\b|\bhit\b|\battacks?\b|\bstrikes?\b", "attack"),
    (r"انصار\s*الله|حوثی(?:‌|\s|-)*ها|حوثی", "houthi"),
    (r"تنگه\s+هرمز", "hormuz"),
    (r"دریای\s+سرخ", "redsea"),
)


def _canonical_tokens(text: str) -> list[str]:
    value = str(text or "").lower()
    for pattern, replacement in _ALIAS_RULES:
        value = re.sub(pattern, replacement, value)
    tokens = re.findall(r"[a-z0-9\u0600-\u06ff]+", value)
    return [token for token in tokens if len(token) > 1 and token not in _STOPWORDS]


def _local_vector(text: str) -> list[float]:
    tokens = _canonical_tokens(text)
    vector = [0.0] * _LOCAL_VECTOR_SIZE
    if not tokens:
        return vector
    features = [(token, 1.0) for token in tokens]
    features.extend((f"{left}_{right}", 0.5) for left, right in zip(tokens, tokens[1:]))
    for feature, weight in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % _LOCAL_VECTOR_SIZE
        vector[index] += weight
    return vector


class LocalFirstNewsAI(HuggingFaceNewsAI):
    """Use local candidate vectors; reserve Hugging Face for editorial judgement and language work.

    This deliberately removes the serverless feature-extraction endpoint from the
    production dependency chain. The local vectors only shortlist likely prior
    events. Qwen's judge_relation remains the authority on duplicate vs material
    update vs different event.
    """

    def __init__(self, config: AIConfig | None = None, *, session=None):
        resolved = config or AIConfig.from_env()
        # Local lexical/alias vectors use a lower candidate threshold than dense
        # embeddings. This threshold only decides whether Qwen should compare the
        # pair; it never makes the duplicate decision by itself.
        resolved = replace(
            resolved,
            duplicate_threshold=min(float(resolved.duplicate_threshold), _LOCAL_DUPLICATE_THRESHOLD),
        )
        if session is None:
            super().__init__(resolved)
        else:
            super().__init__(resolved, session=session)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        cleaned = [str(text or "").strip() for text in texts]
        if not cleaned or any(not text for text in cleaned):
            # Keep the same validation contract as the parent implementation.
            from .ai_newsroom import AIServiceError
            raise AIServiceError("empty_embedding_input")
        return [_local_vector(text) for text in cleaned]
