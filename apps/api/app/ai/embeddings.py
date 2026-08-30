from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from typing import Protocol

from app.ai.gateway import MeteredOpenAIClient, extract_usage
from app.core.config import Settings

EMBEDDING_DIMENSIONS = 768
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class EmbeddingUnavailable(RuntimeError):
    pass


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(
        self,
        texts: Sequence[str],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]: ...

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

    def embed_documents(
        self,
        texts: Sequence[str],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        vectors = [self._embed(text) for text in texts]
        if on_progress:
            on_progress(len(texts), len(texts))
        return vectors

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

    def __init__(self, api_key: str, model_name: str, settings: Settings) -> None:
        self.model_name = model_name
        self.usage: dict[str, int] = {}
        self._batch_max_inputs = settings.embedding_batch_max_inputs
        self._batch_max_characters = settings.embedding_batch_max_characters
        self._client = MeteredOpenAIClient(
            api_key,
            recorder=self._record_usage,
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )

    def _record_usage(self, response: object, **_: object) -> None:
        current = extract_usage(response, embedding=True).as_dict()
        for key, value in current.items():
            self.usage[key] = self.usage.get(key, 0) + value

    def embed_documents(
        self,
        texts: Sequence[str],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        return self._embed_many(
            [
                f"Retrieve this source-code evidence for a developer question:\n{text}"
                for text in texts
            ],
            on_progress=on_progress,
        )

    def embed_query(self, text: str) -> list[float]:
        prompt = f"Find source code that answers this developer question:\n{text}"
        return self._embed_many([prompt])[0]

    def _batches(self, texts: Sequence[str]) -> Iterator[list[str]]:
        batch: list[str] = []
        characters = 0
        for text in texts:
            value = text[:24_000] or " "
            if batch and (
                len(batch) >= self._batch_max_inputs
                or characters + len(value) > self._batch_max_characters
            ):
                yield batch
                batch = []
                characters = 0
            batch.append(value)
            characters += len(value)
        if batch:
            yield batch

    def _embed_many(
        self,
        texts: Sequence[str],
        *,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        total = len(texts)
        for inputs in self._batches(texts):
            response = self._client.embeddings_create(
                model=self.model_name,
                input=inputs,
                dimensions=self.dimensions,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(inputs):
                raise EmbeddingUnavailable("OpenAI returned an unexpected embedding batch")
            vectors.extend(_normalized(list(item.embedding)) for item in ordered)
            if on_progress:
                on_progress(len(vectors), total)
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
            return OpenAIEmbedder(settings.openai_api_key, settings.embedding_model, settings)
        return LocalHashEmbedder()
    if requested == "openai" or requested.startswith("text-embedding-"):
        if not settings.openai_api_key:
            raise EmbeddingUnavailable("OPENAI_API_KEY is required for OpenAI embeddings")
        model = settings.embedding_model if requested == "openai" else requested
        return OpenAIEmbedder(settings.openai_api_key, model, settings)
    raise EmbeddingUnavailable(f"Unsupported embedding provider or model: {requested}")
