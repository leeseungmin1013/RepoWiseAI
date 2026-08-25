from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.embeddings import EmbeddingUnavailable, build_embedder
from app.core.config import Settings
from app.models import (
    CodeChunk,
    FileRecord,
    RepositorySnapshot,
    RetrievalCandidate,
    RetrievalRun,
    Symbol,
)
from app.retrieval.query import QueryAnalysis, analyze_query

RRF_K = 60
RETRIEVER_WEIGHTS = {
    "exact": 1.5,
    "lexical": 1.0,
    "vector": 1.0,
    "selection": 1.25,
}


@dataclass(frozen=True)
class RankedChunk:
    chunk: CodeChunk
    retriever: str
    rank: int
    raw_score: float


@dataclass(frozen=True)
class FusedHit:
    chunk: CodeChunk
    evidence_id: str
    score: float
    retrievers: list[str]


@dataclass(frozen=True)
class RetrievalResult:
    run: RetrievalRun
    analysis: QueryAnalysis
    hits: list[FusedHit]
    query_embedding: list[float] | None = None


def evidence_id_for_chunk(chunk_id: str) -> str:
    return f"ev_{chunk_id.removeprefix('chk_')}"


class HybridRetriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def retrieve(
        self,
        db: Session,
        *,
        snapshot: RepositorySnapshot,
        session_id: str,
        message_id: str,
        query: str,
        selection: dict | None = None,
        query_embedding: list[float] | None = None,
    ) -> RetrievalResult:
        started = perf_counter()
        analysis = analyze_query(query)
        candidate_limit = self.settings.retrieval_candidate_k
        ranked: dict[str, list[RankedChunk]] = {
            "exact": self._exact(db, snapshot.id, analysis.exact_terms, candidate_limit),
            "lexical": self._lexical(db, snapshot.id, analysis.lexical_query, candidate_limit),
            "selection": self._selection(db, snapshot.id, selection, candidate_limit),
        }
        vector_status = "ready"
        resolved_query_embedding = query_embedding
        try:
            ranked["vector"], resolved_query_embedding = self._vector(
                db,
                snapshot,
                f"{query}\n{analysis.lexical_query}",
                candidate_limit,
                query_vector=query_embedding,
            )
        except EmbeddingUnavailable as exc:
            ranked["vector"] = []
            vector_status = str(exc)

        fused_scores: defaultdict[str, float] = defaultdict(float)
        chunks: dict[str, CodeChunk] = {}
        retrievers_by_chunk: defaultdict[str, set[str]] = defaultdict(set)
        for retriever, candidates in ranked.items():
            weight = RETRIEVER_WEIGHTS[retriever]
            for candidate in candidates:
                chunk_id = candidate.chunk.id
                chunks[chunk_id] = candidate.chunk
                retrievers_by_chunk[chunk_id].add(retriever)
                fused_scores[chunk_id] += weight / (RRF_K + candidate.rank)

        rerank_scores = {
            chunk_id: fused_scores[chunk_id] + _structural_adjustment(chunks[chunk_id], analysis)
            for chunk_id in fused_scores
        }
        ordered_ids = sorted(
            rerank_scores,
            key=lambda chunk_id: (
                rerank_scores[chunk_id],
                _specificity(chunks[chunk_id].chunk_type),
            ),
            reverse=True,
        )
        selected_ids = set(ordered_ids[: self.settings.retrieval_top_k])
        hits = [
            FusedHit(
                chunk=chunks[chunk_id],
                evidence_id=evidence_id_for_chunk(chunk_id),
                score=rerank_scores[chunk_id],
                retrievers=sorted(retrievers_by_chunk[chunk_id]),
            )
            for chunk_id in ordered_ids
            if chunk_id in selected_ids
        ]

        plan = {
            "intent": analysis.intent,
            "candidate_limit": candidate_limit,
            "result_limit": self.settings.retrieval_top_k,
            "rrf_k": RRF_K,
            "weights": RETRIEVER_WEIGHTS,
            "retrievers": {name: len(items) for name, items in ranked.items()},
            "vector_status": vector_status,
            "embedding_model": snapshot.embedding_model,
            "hints": analysis.hints,
        }
        run = RetrievalRun(
            session_id=session_id,
            message_id=message_id,
            query_text=query,
            resolved_context=selection or {},
            intent=analysis.intent,
            retrieval_plan=plan,
            index_version=snapshot.index_version,
            latency_ms=0,
            token_usage={},
        )
        db.add(run)
        db.flush()

        for candidates in ranked.values():
            for candidate in candidates:
                chunk_id = candidate.chunk.id
                db.add(
                    RetrievalCandidate(
                        retrieval_run_id=run.id,
                        evidence_id=evidence_id_for_chunk(chunk_id),
                        source_id=chunk_id,
                        retriever=candidate.retriever,
                        rank=candidate.rank,
                        raw_score=candidate.raw_score,
                        rrf_score=fused_scores[chunk_id],
                        rerank_score=rerank_scores[chunk_id],
                        selected=chunk_id in selected_ids,
                    )
                )
        run.latency_ms = round((perf_counter() - started) * 1_000)
        return RetrievalResult(
            run=run,
            analysis=analysis,
            hits=hits,
            query_embedding=resolved_query_embedding,
        )

    @staticmethod
    def _exact(db: Session, snapshot_id: str, terms: list[str], limit: int) -> list[RankedChunk]:
        if not terms:
            return []
        conditions = []
        for term in terms:
            pattern = f"%{term}%"
            conditions.extend(
                (
                    func.lower(Symbol.display_name).like(pattern),
                    func.lower(FileRecord.path).like(pattern),
                    func.lower(CodeChunk.title).like(pattern),
                )
            )
        rows = db.execute(
            select(CodeChunk, Symbol.display_name, FileRecord.path)
            .join(FileRecord, FileRecord.id == CodeChunk.file_id)
            .outerjoin(Symbol, Symbol.id == CodeChunk.symbol_id)
            .where(CodeChunk.snapshot_id == snapshot_id, or_(*conditions))
            .limit(limit * 3)
        ).all()

        scored: list[tuple[CodeChunk, float]] = []
        for chunk, symbol_name, path in rows:
            symbol_lower = (symbol_name or "").lower()
            path_lower = path.lower()
            title_lower = chunk.title.lower()
            score = max(
                (
                    1.0 if term == symbol_lower else 0.9 if term in symbol_lower else 0.0,
                    0.85 if path_lower.endswith(term) else 0.7 if term in path_lower else 0.0,
                    0.65 if term in title_lower else 0.0,
                )
                for term in terms
            )
            scored.append((chunk, max(score)))
        scored.sort(key=lambda item: (item[1], _specificity(item[0].chunk_type)), reverse=True)
        return [
            RankedChunk(chunk=chunk, retriever="exact", rank=rank, raw_score=score)
            for rank, (chunk, score) in enumerate(scored[:limit], start=1)
        ]

    @staticmethod
    def _lexical(
        db: Session, snapshot_id: str, lexical_query: str, limit: int
    ) -> list[RankedChunk]:
        if not lexical_query:
            return []
        web_query = " OR ".join(lexical_query.split())
        query_expression = func.websearch_to_tsquery("simple", web_query)
        score_expression = func.ts_rank_cd(CodeChunk.search_vector, query_expression)
        rows = db.execute(
            select(CodeChunk, score_expression.label("score"))
            .where(
                CodeChunk.snapshot_id == snapshot_id,
                CodeChunk.search_vector.op("@@")(query_expression),
            )
            .order_by(score_expression.desc())
            .limit(limit)
        ).all()
        return [
            RankedChunk(
                chunk=chunk,
                retriever="lexical",
                rank=rank,
                raw_score=float(score),
            )
            for rank, (chunk, score) in enumerate(rows, start=1)
        ]

    def _vector(
        self,
        db: Session,
        snapshot: RepositorySnapshot,
        query: str,
        limit: int,
        *,
        query_vector: list[float] | None = None,
    ) -> tuple[list[RankedChunk], list[float]]:
        if query_vector is None:
            embedder = build_embedder(self.settings, snapshot.embedding_model)
            query_vector = embedder.embed_query(query)
        distance = CodeChunk.embedding.cosine_distance(query_vector)
        rows = db.execute(
            select(CodeChunk, distance.label("distance"))
            .where(
                CodeChunk.snapshot_id == snapshot.id,
                CodeChunk.embedding_model == snapshot.embedding_model,
                CodeChunk.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(limit)
        ).all()
        return (
            [
                RankedChunk(
                    chunk=chunk,
                    retriever="vector",
                    rank=rank,
                    raw_score=max(-1.0, 1.0 - float(vector_distance)),
                )
                for rank, (chunk, vector_distance) in enumerate(rows, start=1)
            ],
            query_vector,
        )

    @staticmethod
    def _selection(
        db: Session, snapshot_id: str, selection: dict | None, limit: int
    ) -> list[RankedChunk]:
        if not selection or not selection.get("file_id"):
            return []
        statement = select(CodeChunk).where(
            CodeChunk.snapshot_id == snapshot_id,
            CodeChunk.file_id == selection["file_id"],
        )
        start_line = selection.get("start_line")
        end_line = selection.get("end_line")
        if isinstance(start_line, int) and isinstance(end_line, int):
            statement = statement.where(
                CodeChunk.start_line <= end_line,
                CodeChunk.end_line >= start_line,
            )
        chunks = db.scalars(
            statement.order_by(CodeChunk.start_line, CodeChunk.end_line).limit(limit)
        ).all()
        return [
            RankedChunk(
                chunk=chunk,
                retriever="selection",
                rank=rank,
                raw_score=1.0 / rank,
            )
            for rank, chunk in enumerate(chunks, start=1)
        ]


def _specificity(chunk_type: str) -> int:
    return {"symbol": 3, "block": 2, "file": 1}.get(chunk_type, 0)


def _structural_adjustment(chunk: CodeChunk, analysis: QueryAnalysis) -> float:
    path = chunk.title.split("#", 1)[0].split(" lines ", 1)[0].lower()
    file_name = path.rsplit("/", 1)[-1]
    is_test = (
        path.startswith("test/")
        or path.startswith("tests/")
        or "__tests__" in path
        or ".test." in path
        or ".spec." in path
        or file_name.startswith("test-")
        or file_name.startswith("test.")
    )
    adjustment = 0.0
    if is_test and "test" not in analysis.hints:
        adjustment -= 0.015
    if "entry_point" in analysis.hints:
        entry_names = {
            "index.ts",
            "index.tsx",
            "index.js",
            "index.jsx",
            "main.ts",
            "main.tsx",
            "main.js",
            "app.ts",
            "app.tsx",
            "server.ts",
            "page.tsx",
            "package.json",
        }
        if file_name in entry_names:
            adjustment += 0.018
        if is_test:
            adjustment -= 0.012
    return adjustment
