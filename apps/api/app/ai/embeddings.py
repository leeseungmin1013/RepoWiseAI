from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from app.core.config import Settings

EMBEDDING_DIMENSIONS = 768
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class EmbeddingUnavailable(RuntimeError):
    pass


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _normalized(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def _features(text: str) -> Counter[str]:
    expanded = CAMEL_BOUNDARY.sub(" ", text)
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(expanded)]
    features: Counter[str] = Counter(tokens)
    for token in tokens:
        if len(token) < 4:
            continue
        padded = f"^{token}$"
        features.update(padded[index : index + 3] for index in range(len(padded) - 2))
    return features


class LocalHashEmbedder:
    """Deterministic offline vector baseline for development and tests."""

    model_name = "local-hash-v1"
    dimensions = EMBEDDING_DIMENSIONS

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, count in _features(text).items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(count))
        return _normalized(vector)


class OpenAIEmbedder:
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self, api_key: str, model_name: str) -> None:
        from openai import OpenAI

        self.model_name = model_name
        self._client = OpenAI(api_key=api_key)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed_many(
            [
                f"Retrieve this source-code evidence for a developer question:\n{text}"
                for text in texts
            ]
        )

    def embed_query(self, text: str) -> list[float]:
        prompt = f"Find source code that answers this developer question:\n{text}"
        return self._embed_many([prompt])[0]

    def _embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = 128
        for start in range(0, len(texts), batch_size):
            inputs = [text[:24_000] or " " for text in texts[start : start + batch_size]]
            response = self._client.embeddings.create(
                model=self.model_name,
                input=inputs,
                dimensions=self.dimensions,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(inputs):
                raise EmbeddingUnavailable("OpenAI returned an unexpected embedding batch")
            vectors.extend(_normalized(list(item.embedding)) for item in ordered)
        if any(len(vector) != self.dimensions for vector in vectors):
            raise EmbeddingUnavailable("Embedding dimensions do not match the database index")
        return vectors


def build_embedder(settings: Settings, model_name: str | None = None) -> Embedder:
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise EmbeddingUnavailable(
            f"EMBEDDING_DIMENSIONS must remain {EMBEDDING_DIMENSIONS} for this index version"
        )

    requested = model_name or settings.embedding_provider
    if requested == "local" or requested.startswith("local-hash"):
        return LocalHashEmbedder()
    if requested == "auto":
        if settings.openai_api_key:
            return OpenAIEmbedder(settings.openai_api_key, settings.embedding_model)
        return LocalHashEmbedder()
    if requested == "openai" or requested.startswith("text-embedding-"):
        if not settings.openai_api_key:
            raise EmbeddingUnavailable("OPENAI_API_KEY is required for OpenAI embeddings")
        model = settings.embedding_model if requested == "openai" else requested
        return OpenAIEmbedder(settings.openai_api_key, model)
    raise EmbeddingUnavailable(f"Unsupported embedding provider or model: {requested}")
