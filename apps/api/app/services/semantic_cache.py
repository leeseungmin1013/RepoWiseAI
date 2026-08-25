from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.answers import GeneratedAnswer
from app.ai.embeddings import EmbeddingUnavailable, build_embedder
from app.core.config import Settings
from app.models import CodeChunk, FileRecord, RepositorySnapshot, SemanticCacheEntry
from app.retrieval.hybrid import FusedHit, evidence_id_for_chunk
from app.retrieval.query import analyze_query

PROMPT_VERSION = "grounded-answer-v1"


@dataclass(frozen=True)
class CacheLookup:
    entry: SemanticCacheEntry
    status: str
    similarity: float | None
    hits: list[FusedHit]


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def canonical_fingerprint(payload: dict[str, Any]) -> str:
    value = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


class SemanticCacheService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def context_fingerprint(
        self,
        db: Session,
        *,
        snapshot: RepositorySnapshot,
        selection: dict,
        learning_context: dict,
        preferred_style: str,
        modality: str,
        task_kind: str | None,
        model: str | None,
        reasoning_effort: str | None,
        locale: str = "ko",
    ) -> str:
        selection_context: dict[str, Any] = {}
        if selection.get("file_id"):
            file = db.get(FileRecord, selection["file_id"])
            if file is not None and file.snapshot_id == snapshot.id:
                lines = file.content.splitlines()[
                    int(selection.get("start_line", 1)) - 1 : int(selection.get("end_line", 1))
                ]
                selection_context = {
                    "path": file.path,
                    "file_content_hash": file.content_hash,
                    "start_line": selection.get("start_line"),
                    "end_line": selection.get("end_line"),
                    "range_hash": canonical_fingerprint({"lines": lines}),
                }
        return canonical_fingerprint(
            {
                "selection": selection_context,
                "learning": learning_context,
                "style": preferred_style,
                "modality": modality,
                "task_kind": task_kind,
                "retriever": snapshot.index_version,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "prompt": PROMPT_VERSION,
                "locale": locale,
            }
        )

    def exact_key(
        self,
        *,
        kind: str,
        snapshot: RepositorySnapshot,
        query: str,
        intent: str,
        context_fingerprint: str,
        model: str | None,
    ) -> str:
        return canonical_fingerprint(
            {
                "kind": kind,
                "repository_id": snapshot.repository_id,
                "analysis_fingerprint": snapshot.analysis_fingerprint,
                "query": normalize_query(query),
                "intent": intent,
                "context": context_fingerprint,
                "index": snapshot.index_version,
                "model": model,
                "prompt": PROMPT_VERSION,
            }
        )

    def embed_query(self, snapshot: RepositorySnapshot, query: str) -> list[float] | None:
        try:
            analysis = analyze_query(query)
            embedder = build_embedder(self.settings, snapshot.embedding_model)
            return embedder.embed_query(f"{query}\n{analysis.lexical_query}")
        except EmbeddingUnavailable:
            return None

    def lookup(
        self,
        db: Session,
        *,
        kind: str,
        scope: str,
        scope_id: str,
        snapshot: RepositorySnapshot,
        query: str,
        intent: str,
        context_fingerprint: str,
        model: str | None,
        query_embedding: list[float] | None = None,
    ) -> CacheLookup | None:
        if not self.settings.semantic_cache_read_enabled:
            return None
        now = datetime.now(UTC)
        key = self.exact_key(
            kind=kind,
            snapshot=snapshot,
            query=query,
            intent=intent,
            context_fingerprint=context_fingerprint,
            model=model,
        )
        base = [
            SemanticCacheEntry.cache_kind == kind,
            SemanticCacheEntry.scope == scope,
            SemanticCacheEntry.scope_id == scope_id,
            SemanticCacheEntry.intent == intent,
            SemanticCacheEntry.context_fingerprint == context_fingerprint,
            SemanticCacheEntry.quality_status == "active",
            SemanticCacheEntry.invalidated_at.is_(None),
            or_(SemanticCacheEntry.expires_at.is_(None), SemanticCacheEntry.expires_at > now),
        ]
        entry = db.scalar(
            select(SemanticCacheEntry)
            .where(*base, SemanticCacheEntry.exact_key == key)
            .order_by(SemanticCacheEntry.created_at.desc())
        )
        status = "exact_hit"
        similarity: float | None = None
        if entry is None and query_embedding is not None:
            threshold = (
                self.settings.retrieval_cache_similarity_threshold
                if kind == "retrieval"
                else self.settings.generation_cache_similarity_threshold
            )
            distance = SemanticCacheEntry.query_embedding.cosine_distance(query_embedding)
            row = db.execute(
                select(SemanticCacheEntry, distance.label("distance"))
                .where(
                    *base,
                    SemanticCacheEntry.query_embedding.is_not(None),
                    distance <= 1.0 - threshold,
                )
                .order_by(distance)
                .limit(1)
            ).first()
            if row:
                entry, raw_distance = row
                similarity = max(-1.0, 1.0 - float(raw_distance))
                status = "semantic_hit"
        if entry is None:
            return None
        hits = self._validated_hits(db, snapshot, entry.evidence_manifest)
        if len(hits) != len(entry.evidence_manifest):
            entry.quality_status = "quarantined"
            entry.invalidated_at = now
            db.flush()
            return None
        entry.hit_count += 1
        entry.last_hit_at = now
        db.flush()
        return CacheLookup(entry=entry, status=status, similarity=similarity, hits=hits)

    def store(
        self,
        db: Session,
        *,
        kind: str,
        scope: str,
        scope_id: str,
        snapshot: RepositorySnapshot,
        query: str,
        intent: str,
        context_fingerprint: str,
        model: str | None,
        query_embedding: list[float] | None,
        hits: list[FusedHit],
        payload: dict,
        source_run_id: str | None,
        source_message_id: str | None,
    ) -> SemanticCacheEntry | None:
        if not self.settings.semantic_cache_write_enabled or not hits:
            return None
        evidence_manifest = self._evidence_manifest(db, hits)
        if len(evidence_manifest) != len(hits):
            return None
        ttl_days = (
            self.settings.retrieval_cache_ttl_days
            if kind == "retrieval"
            else self.settings.generation_cache_ttl_days
        )
        entry = SemanticCacheEntry(
            cache_kind=kind,
            scope=scope,
            scope_id=scope_id,
            snapshot_id=snapshot.id,
            compatible_evidence_fingerprint=canonical_fingerprint({"evidence": evidence_manifest}),
            exact_key=self.exact_key(
                kind=kind,
                snapshot=snapshot,
                query=query,
                intent=intent,
                context_fingerprint=context_fingerprint,
                model=model,
            ),
            normalized_query=normalize_query(query),
            query_embedding=query_embedding,
            intent=intent,
            context_fingerprint=context_fingerprint,
            payload_json=payload,
            evidence_manifest=evidence_manifest,
            model=model,
            prompt_version=PROMPT_VERSION if kind == "generation" else None,
            index_version=snapshot.index_version,
            source_run_id=source_run_id,
            source_message_id=source_message_id,
            expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
        )
        try:
            with db.begin_nested():
                db.add(entry)
                db.flush()
        except IntegrityError:
            return db.scalar(
                select(SemanticCacheEntry).where(
                    SemanticCacheEntry.cache_kind == kind,
                    SemanticCacheEntry.scope == scope,
                    SemanticCacheEntry.scope_id == scope_id,
                    SemanticCacheEntry.exact_key == entry.exact_key,
                )
            )
        return entry

    def generated_answer(self, lookup: CacheLookup) -> GeneratedAnswer:
        payload = lookup.entry.payload_json
        return GeneratedAnswer(
            answer=str(payload["answer"]),
            evidence_ids=[item.evidence_id for item in lookup.hits],
            follow_up=payload.get("follow_up"),
            status=str(payload.get("status", "grounded")),
            mode="cache",
            model_name=payload.get("model_name"),
            voice_summary=payload.get("voice_summary"),
        )

    @staticmethod
    def _evidence_manifest(db: Session, hits: list[FusedHit]) -> list[dict]:
        if not hits:
            return []
        files = db.scalars(
            select(FileRecord).where(FileRecord.id.in_({hit.chunk.file_id for hit in hits}))
        ).all()
        file_by_id = {item.id: item for item in files}
        output = []
        for hit in hits:
            file = file_by_id.get(hit.chunk.file_id)
            if file is None:
                continue
            output.append(
                {
                    "path": file.path,
                    "file_content_hash": file.content_hash,
                    "chunk_content_hash": hit.chunk.content_hash,
                    "start_line": hit.chunk.start_line,
                    "end_line": hit.chunk.end_line,
                    "score": hit.score,
                    "retrievers": hit.retrievers,
                }
            )
        return output

    @staticmethod
    def _validated_hits(
        db: Session,
        snapshot: RepositorySnapshot,
        manifest: list[dict],
    ) -> list[FusedHit]:
        output: list[FusedHit] = []
        for item in manifest:
            file = db.scalar(
                select(FileRecord).where(
                    FileRecord.snapshot_id == snapshot.id,
                    FileRecord.path == item.get("path"),
                    FileRecord.content_hash == item.get("file_content_hash"),
                )
            )
            if file is None:
                continue
            chunk = db.scalar(
                select(CodeChunk).where(
                    CodeChunk.snapshot_id == snapshot.id,
                    CodeChunk.file_id == file.id,
                    CodeChunk.content_hash == item.get("chunk_content_hash"),
                    CodeChunk.start_line == item.get("start_line"),
                    CodeChunk.end_line == item.get("end_line"),
                )
            )
            if chunk is None:
                continue
            source = "\n".join(file.content.splitlines()[chunk.start_line - 1 : chunk.end_line])
            expected = f"sha256:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"
            if source != chunk.content or expected != chunk.content_hash:
                continue
            output.append(
                FusedHit(
                    chunk=chunk,
                    evidence_id=evidence_id_for_chunk(chunk.id),
                    score=float(item.get("score", 0.0)),
                    retrievers=list(item.get("retrievers") or ["cache"]),
                )
            )
        return output
