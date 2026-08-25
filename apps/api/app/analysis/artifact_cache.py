from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.typescript import ParsedEdge, ParsedSymbol, ParseResult
from app.models import EmbeddingCache, FileParseArtifact, SourceBlob


def text_hash(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def ensure_source_blob(
    db: Session,
    *,
    content_hash: str,
    content: str,
    byte_size: int,
    line_count: int,
) -> SourceBlob:
    blob = db.get(SourceBlob, content_hash)
    if blob is None:
        blob = SourceBlob(
            content_hash=content_hash,
            content=content,
            byte_size=byte_size,
            line_count=line_count,
        )
        db.add(blob)
        db.flush()
    return blob


def _serialize_parse(result: ParseResult) -> dict:
    return {
        "symbols": [asdict(item) for item in result.symbols],
        "edges": [asdict(item) for item in result.edges],
    }


def _deserialize_parse(payload: dict) -> ParseResult:
    return ParseResult(
        symbols=[
            ParsedSymbol(
                **{
                    **item,
                    "exported_names": tuple(item.get("exported_names") or ()),
                }
            )
            for item in payload.get("symbols", [])
        ],
        edges=[ParsedEdge(**item) for item in payload.get("edges", [])],
    )


def load_or_create_parse_artifact(
    db: Session,
    *,
    content_hash: str,
    language: str,
    parser_version: str,
    parser: Callable[[], ParseResult],
) -> tuple[ParseResult, bool]:
    artifact = db.scalar(
        select(FileParseArtifact).where(
            FileParseArtifact.content_hash == content_hash,
            FileParseArtifact.language == language,
            FileParseArtifact.parser_version == parser_version,
        )
    )
    if artifact is not None:
        return _deserialize_parse(artifact.payload_json), True
    result = parser()
    db.add(
        FileParseArtifact(
            content_hash=content_hash,
            language=language,
            parser_version=parser_version,
            payload_json=_serialize_parse(result),
        )
    )
    db.flush()
    return result, False


def embed_documents_with_cache(
    db: Session,
    *,
    texts: list[str],
    embedder: object,
    provider: str,
    model: str,
    dimensions: int,
    prompt_version: str,
) -> tuple[list[list[float]], dict[str, int]]:
    hashes = [text_hash(item) for item in texts]
    cached = (
        db.scalars(
            select(EmbeddingCache).where(
                EmbeddingCache.provider == provider,
                EmbeddingCache.model == model,
                EmbeddingCache.dimensions == dimensions,
                EmbeddingCache.prompt_version == prompt_version,
                EmbeddingCache.text_hash.in_(set(hashes)),
            )
        ).all()
        if hashes
        else []
    )
    by_hash = {item.text_hash: list(item.embedding) for item in cached}
    missing_hashes: list[str] = []
    missing_texts: list[str] = []
    for item_hash, item_text in zip(hashes, texts, strict=True):
        if item_hash not in by_hash and item_hash not in missing_hashes:
            missing_hashes.append(item_hash)
            missing_texts.append(item_text)
    if missing_texts:
        generated = embedder.embed_documents(missing_texts)
        for item_hash, vector in zip(missing_hashes, generated, strict=True):
            value = list(vector)
            by_hash[item_hash] = value
            db.add(
                EmbeddingCache(
                    provider=provider,
                    model=model,
                    dimensions=dimensions,
                    prompt_version=prompt_version,
                    text_hash=item_hash,
                    embedding=value,
                    token_usage={},
                )
            )
        db.flush()
    return [by_hash[item_hash] for item_hash in hashes], {
        "embedding_reused": len(texts) - len(missing_texts),
        "embedding_created": len(missing_texts),
    }
