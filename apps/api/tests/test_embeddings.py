import pytest

from app.ai import embeddings
from app.ai.embeddings import EmbeddingUnavailable, LocalHashEmbedder, build_embedder
from app.core.config import Settings


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_local_embedding_is_deterministic_and_prefers_shared_code_terms() -> None:
    embedder = LocalHashEmbedder()
    query = embedder.embed_query("loginUser authentication token")
    related, unrelated = embedder.embed_documents(
        [
            "function loginUser stores an authentication token",
            "render a chart with width and height",
        ]
    )

    assert len(query) == 768
    assert query == embedder.embed_query("loginUser authentication token")
    assert _dot(query, related) > _dot(query, unrelated)


def test_auto_provider_prefers_openai_when_a_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeOpenAIEmbedder:
        model_name = "text-embedding-3-small"
        dimensions = 768

        def __init__(self, api_key: str, model_name: str) -> None:
            self.api_key = api_key
            self.model_name = model_name

    monkeypatch.setattr(embeddings, "OpenAIEmbedder", FakeOpenAIEmbedder)

    embedder = build_embedder(Settings(openai_api_key="test-key"))

    assert isinstance(embedder, FakeOpenAIEmbedder)
    assert embedder.api_key == "test-key"


def test_explicit_openai_provider_requires_an_api_key() -> None:
    with pytest.raises(EmbeddingUnavailable, match="OPENAI_API_KEY"):
        build_embedder(Settings(embedding_provider="openai", openai_api_key=""))
