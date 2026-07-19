from __future__ import annotations

import shutil
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.ai.embeddings import build_embedder
from app.analysis.chunking import SymbolSpan, build_file_chunks
from app.analysis.typescript import ParseResult, TypeScriptAnalyzer
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.ids import new_id
from app.guidance.path_builder import ensure_guided_path
from app.models import (
    AnalysisJob,
    CodeChunk,
    FileRecord,
    GuidedPath,
    RepositorySnapshot,
    Symbol,
    SymbolEdge,
)
from app.services.file_filter import collect_source_files
from app.services.github import GitHubClient


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _set_stage(
    snapshot_id: str,
    stage: str,
    *,
    current: int = 0,
    total: int = 0,
) -> None:
    with SessionLocal() as db:
        snapshot = db.get(RepositorySnapshot, snapshot_id)
        job = db.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.snapshot_id == snapshot_id)
            .order_by(AnalysisJob.created_at.desc())
        )
        if snapshot:
            snapshot.status = "analyzing"
            snapshot.error_message = None
        if job:
            job.stage = stage
            job.status = "running"
            job.progress_current = current
            job.progress_total = total
            if job.started_at is None:
                job.started_at = _utc_now()
        db.commit()


def _safe_workspace(snapshot_id: str) -> Path:
    settings = get_settings()
    root = settings.analysis_workspace.resolve()
    root.mkdir(parents=True, exist_ok=True)
    workspace = (root / snapshot_id).resolve()
    if root not in workspace.parents:
        raise RuntimeError("Analysis workspace escaped its configured root")
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    return workspace


def _extract_archive(archive_path: Path, destination: Path) -> Path:
    settings = get_settings()
    extracted_bytes = 0
    max_extracted_bytes = settings.max_repository_bytes * 4

    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk() or member.isdev():
                continue
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2:
                continue
            relative_parts = parts[1:]
            if any(part in {"", ".", ".."} for part in relative_parts):
                continue
            relative = Path(*relative_parts)
            target = (destination / relative).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise RuntimeError("Archive entry escaped the analysis workspace")

            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            extracted_bytes += member.size
            if extracted_bytes > max_extracted_bytes:
                raise RuntimeError("The extracted repository archive is too large")
            if member.size > settings.max_file_bytes * 4:
                continue

            source = archive.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    return destination


def _resolve_import(source_path: str, target: str, known_paths: set[str]) -> str:
    if not target.startswith("."):
        return target
    source_parent = PurePosixPath(source_path).parent
    base = source_parent.joinpath(target)
    normalized = PurePosixPath(*[part for part in base.parts if part not in {"."}])
    candidates = [
        normalized.as_posix(),
        *[f"{normalized.as_posix()}{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx")],
        *[f"{normalized.as_posix()}/index{suffix}" for suffix in (".ts", ".tsx", ".js", ".jsx")],
    ]
    for candidate in candidates:
        clean_parts: list[str] = []
        for part in PurePosixPath(candidate).parts:
            if part == "..":
                if clean_parts:
                    clean_parts.pop()
            else:
                clean_parts.append(part)
        clean = PurePosixPath(*clean_parts).as_posix()
        if clean in known_paths:
            return clean
    return target


def analyze_repository(snapshot_id: str) -> None:
    settings = get_settings()
    try:
        _set_stage(snapshot_id, "fetching")
        with SessionLocal() as db:
            snapshot = db.scalar(
                select(RepositorySnapshot)
                .where(RepositorySnapshot.id == snapshot_id)
                .options(selectinload(RepositorySnapshot.repository))
            )
            if snapshot is None:
                raise RuntimeError("Snapshot not found")
            owner = snapshot.repository.owner
            name = snapshot.repository.name
            requested_branch = snapshot.branch

        workspace = _safe_workspace(snapshot_id)
        archive_path = workspace / "repository.tar.gz"
        source_root = workspace / "source"
        source_root.mkdir()

        with GitHubClient(settings) as github:
            resolved = github.resolve_snapshot(owner, name, requested_branch)
            github.download_archive(resolved, archive_path)

        with SessionLocal() as db:
            snapshot = db.get(RepositorySnapshot, snapshot_id)
            if snapshot is None:
                raise RuntimeError("Snapshot disappeared during analysis")
            snapshot.branch = resolved.branch
            snapshot.commit_sha = resolved.commit_sha
            db.commit()

        _set_stage(snapshot_id, "filtering")
        _extract_archive(archive_path, source_root)
        archive_path.unlink(missing_ok=True)
        source_files = collect_source_files(source_root, settings)
        _set_stage(snapshot_id, "parsing", total=len(source_files))

        analyzer = TypeScriptAnalyzer()
        parse_results: dict[str, ParseResult] = {}

        with SessionLocal() as db:
            db.execute(delete(GuidedPath).where(GuidedPath.snapshot_id == snapshot_id))
            db.execute(delete(CodeChunk).where(CodeChunk.snapshot_id == snapshot_id))
            db.execute(delete(SymbolEdge).where(SymbolEdge.snapshot_id == snapshot_id))
            db.execute(delete(Symbol).where(Symbol.snapshot_id == snapshot_id))
            db.execute(delete(FileRecord).where(FileRecord.snapshot_id == snapshot_id))
            db.flush()

            file_records: dict[str, FileRecord] = {}
            for index, source_file in enumerate(source_files, start=1):
                record = FileRecord(
                    snapshot_id=snapshot_id,
                    path=source_file.path,
                    language=source_file.language,
                    content=source_file.content,
                    content_hash=source_file.content_hash,
                    byte_size=source_file.byte_size,
                    line_count=source_file.line_count,
                    is_documentation=source_file.is_documentation,
                )
                db.add(record)
                db.flush()
                file_records[source_file.path] = record
                if source_file.language in {"typescript", "tsx", "javascript", "jsx"}:
                    parse_results[source_file.path] = analyzer.parse(
                        source_file.path, source_file.content, source_file.language
                    )
                if index % 50 == 0:
                    job = db.scalar(
                        select(AnalysisJob)
                        .where(AnalysisJob.snapshot_id == snapshot_id)
                        .order_by(AnalysisJob.created_at.desc())
                    )
                    if job:
                        job.progress_current = index
                    db.commit()

            job = db.scalar(
                select(AnalysisJob)
                .where(AnalysisJob.snapshot_id == snapshot_id)
                .order_by(AnalysisJob.created_at.desc())
            )
            if job:
                job.stage = "graph_building"
                job.progress_current = 0
                job.progress_total = len(parse_results)
            db.commit()

            symbol_ids: dict[str, str] = {}
            display_symbol_ids: dict[tuple[str, str], str] = {}
            symbols_by_file: dict[str, list[Symbol]] = {}
            for path, result in parse_results.items():
                file_record = file_records[path]
                for parsed in result.symbols:
                    symbol = Symbol(
                        snapshot_id=snapshot_id,
                        file_id=file_record.id,
                        qualified_name=parsed.qualified_name,
                        display_name=parsed.display_name,
                        kind=parsed.kind,
                        signature=parsed.signature,
                        start_line=parsed.start_line,
                        end_line=parsed.end_line,
                        content_hash=parsed.content_hash,
                    )
                    db.add(symbol)
                    db.flush()
                    symbol_ids[parsed.qualified_name] = symbol.id
                    display_symbol_ids[(path, parsed.display_name)] = symbol.id
                    symbols_by_file.setdefault(path, []).append(symbol)

            known_paths = set(file_records)
            edge_count = 0
            for path, result in parse_results.items():
                file_record = file_records[path]
                for parsed_edge in result.edges:
                    target = parsed_edge.target
                    target_symbol_id = None
                    if parsed_edge.relation == "IMPORTS":
                        target = _resolve_import(path, target, known_paths)
                    elif parsed_edge.relation == "CALLS":
                        short_target = target.rsplit(".", 1)[-1]
                        target_symbol_id = display_symbol_ids.get((path, short_target))
                    db.add(
                        SymbolEdge(
                            snapshot_id=snapshot_id,
                            source_file_id=file_record.id,
                            source_symbol_id=symbol_ids.get(
                                parsed_edge.source_qualified_name or ""
                            ),
                            target_symbol_id=target_symbol_id,
                            target_path=target,
                            relation=parsed_edge.relation,
                            confidence=parsed_edge.confidence,
                            analysis_method="tree_sitter_v1",
                            source_start_line=parsed_edge.start_line,
                            source_end_line=parsed_edge.end_line,
                        )
                    )
                    edge_count += 1

            job = db.scalar(
                select(AnalysisJob)
                .where(AnalysisJob.snapshot_id == snapshot_id)
                .order_by(AnalysisJob.created_at.desc())
            )
            if job:
                job.stage = "chunking"
                job.progress_current = 0
                job.progress_total = len(file_records)
            db.commit()

            chunk_inputs: list[tuple[FileRecord, object]] = []
            for file_index, (path, file_record) in enumerate(file_records.items(), start=1):
                spans = [
                    SymbolSpan(
                        id=symbol.id,
                        display_name=symbol.display_name,
                        kind=symbol.kind,
                        signature=symbol.signature,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                    )
                    for symbol in symbols_by_file.get(path, [])
                ]
                drafts = build_file_chunks(
                    file_id=file_record.id,
                    path=path,
                    language=file_record.language,
                    content=file_record.content,
                    symbols=spans,
                    max_lines=settings.chunk_max_lines,
                    overlap_lines=settings.chunk_overlap_lines,
                )
                chunk_inputs.extend((file_record, draft) for draft in drafts)
                if job and file_index % 50 == 0:
                    job.progress_current = file_index
                    db.commit()

            embedder = build_embedder(settings)
            if job:
                job.stage = "embedding"
                job.progress_current = 0
                job.progress_total = len(chunk_inputs)
                db.commit()
            embeddings = embedder.embed_documents(
                [draft.embedding_text for _, draft in chunk_inputs]
            )

            chunk_records: dict[str, CodeChunk] = {}
            parent_keys: dict[str, str | None] = {}
            for (file_record, draft), embedding in zip(chunk_inputs, embeddings, strict=True):
                chunk = CodeChunk(
                    id=new_id("chk"),
                    snapshot_id=snapshot_id,
                    file_id=file_record.id,
                    symbol_id=draft.symbol_id,
                    parent_chunk_id=None,
                    chunk_type=draft.chunk_type,
                    ordinal=draft.ordinal,
                    title=draft.title,
                    language=draft.language,
                    start_line=draft.start_line,
                    end_line=draft.end_line,
                    content=draft.content,
                    search_text=draft.search_text,
                    embedding=embedding,
                    embedding_model=embedder.model_name,
                    content_hash=draft.content_hash,
                    metadata_json=draft.metadata,
                )
                db.add(chunk)
                chunk_records[draft.key] = chunk
                parent_keys[draft.key] = draft.parent_key
            db.flush()
            for key, parent_key in parent_keys.items():
                if parent_key:
                    chunk_records[key].parent_chunk_id = chunk_records[parent_key].id

            if job:
                job.stage = "guidance"
                job.progress_current = 0
                job.progress_total = 1
            db.flush()
            ensure_guided_path(db, snapshot_id)
            if job:
                job.progress_current = 1

            snapshot = db.get(RepositorySnapshot, snapshot_id)
            job = db.scalar(
                select(AnalysisJob)
                .where(AnalysisJob.snapshot_id == snapshot_id)
                .order_by(AnalysisJob.created_at.desc())
            )
            if snapshot is None or job is None:
                raise RuntimeError("Analysis state disappeared before completion")
            snapshot.status = "ready"
            snapshot.file_count = len(source_files)
            snapshot.symbol_count = len(symbol_ids)
            snapshot.edge_count = edge_count
            snapshot.chunk_count = len(chunk_inputs)
            snapshot.total_bytes = sum(file.byte_size for file in source_files)
            snapshot.index_version = "retrieval-v1"
            snapshot.embedding_model = embedder.model_name
            snapshot.error_message = None
            job.stage = "ready"
            job.status = "finished"
            job.progress_current = len(chunk_inputs)
            job.progress_total = len(chunk_inputs)
            job.finished_at = _utc_now()
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            snapshot = db.get(RepositorySnapshot, snapshot_id)
            job = db.scalar(
                select(AnalysisJob)
                .where(AnalysisJob.snapshot_id == snapshot_id)
                .order_by(AnalysisJob.created_at.desc())
            )
            detail = str(exc)[:2_000]
            if snapshot:
                snapshot.status = "failed"
                snapshot.error_message = detail
            if job:
                job.status = "failed"
                job.error_code = type(exc).__name__
                job.error_detail = detail
                job.finished_at = _utc_now()
            db.commit()
        raise
