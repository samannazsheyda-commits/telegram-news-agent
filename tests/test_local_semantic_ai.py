from src.ai_newsroom import AIConfig, cosine_similarity
from src.local_semantic_ai import LocalFirstNewsAI


class NoHttpSession:
    def post(self, *args, **kwargs):
        raise AssertionError("embedding candidate selection must not call remote HTTP")


def test_local_first_embeddings_need_no_hf_feature_endpoint():
    ai = LocalFirstNewsAI(AIConfig(token="hf_test", mode="required"), session=NoHttpSession())
    vectors = ai.embed_texts([
        "Iran-backed Houthi forces reached Dhubab in Yemen",
        "Forces aligned with Ansar Allah arrive at the Red Sea town of Dhubab",
    ])
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1])
    assert cosine_similarity(vectors[0], vectors[1]) >= ai.config.duplicate_threshold


def test_local_first_keeps_remote_chat_editor_available_without_remote_embeddings():
    ai = LocalFirstNewsAI(AIConfig(token="hf_test", mode="required"), session=NoHttpSession())
    assert ai.available is True
    assert ai.config.duplicate_threshold <= 0.20
