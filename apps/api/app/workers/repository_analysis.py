from __future__ import annotations

import json
import shutil
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.ai.embeddings import build_embedder
from app.analysis.chunking import SymbolSpan, build_file_chunks
from app.analysis.typescript import ParsedEdge, ParseResult, TypeScriptAnalyzer
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.ids import new_id
from app.guidance.path_builder import ensure_guided_path
from app.models import (
    AnalysisJob,
    CodeChunk,
    FileRecord,
    GuidedPath,
    NavigationArtifact,
    RepositorySnapshot,
    Symbol,
    SymbolEdge,
)
from app.navigation.versions import SEMANTIC_GRAPH_VERSION
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


@dataclass(frozen=True)
class _RouteHandler:
    package_root: str
    request_path: str
    http_method: str
    file_path: str
    target_symbol_id: str


@dataclass(frozen=True)
class _ResolvedEdge:
    relation: str
    source_qualified_name: str | None
    target_symbol_id: str | None
    target_path: str | None
    confidence: float
    start_line: int
    end_line: int
    metadata: dict[str, object]


def _next_route_request_path(file_path: str) -> str | None:
    parts = PurePosixPath(file_path).parts
    if not parts or parts[-1].lower() not in {
        "route.ts",
        "route.tsx",
        "route.js",
        "route.jsx",
    }:
        return None

    app_index = next(
        (
            index
            for index in range(len(parts) - 2)
            if parts[index] == "app" and parts[index + 1] == "api"
        ),
        None,
    )
    if app_index is None:
        return None

    url_segments: list[str] = []
    for segment in parts[app_index + 1 : -1]:
        if (
            "[" in segment
            or "]" in segment
            or segment.startswith("@")
            or segment.startswith("_")
        ):
            return None
        if segment.startswith("(") and segment.endswith(")"):
            continue
        url_segments.append(segment)
    if not url_segments or url_segments[0] != "api":
        return None
    return f"/{'/'.join(url_segments)}"


def _normalize_literal_request_path(request_target: str) -> str | None:
    try:
        parsed = urlsplit(request_target)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return None
    path = parsed.path
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def _find_next_package_roots(file_contents: dict[str, str]) -> set[str]:
    roots: set[str] = set()
    for path, content in file_contents.items():
        if PurePosixPath(path).name != "package.json":
            continue
        try:
            manifest = json.loads(content)
        except (TypeError, ValueError):
            continue
        if not isinstance(manifest, dict):
            continue
        dependency_names: set[str] = set()
        for field in (
            "dependencies",
            "devDependencies",
            "optionalDependencies",
            "peerDependencies",
        ):
            dependencies = manifest.get(field)
            if isinstance(dependencies, dict):
                dependency_names.update(str(name) for name in dependencies)
        if "next" not in dependency_names:
            continue
        parent = PurePosixPath(path).parent.as_posix()
        roots.add("" if parent == "." else parent)
    return roots


def _path_is_under_root(path: str, root: str) -> bool:
    return not root or path == root or path.startswith(f"{root}/")


def _longest_matching_package_root(path: str, roots: set[str]) -> str | None:
    matching = [root for root in roots if _path_is_under_root(path, root)]
    if not matching:
        return None
    return max(
        matching,
        key=lambda root: (len(PurePosixPath(root).parts), len(root)),
    )


def _build_route_handler_index(
    parse_results: dict[str, ParseResult],
    symbol_ids: dict[str, str],
    next_package_roots: set[str],
) -> dict[tuple[str, str, str], _RouteHandler]:
    candidates: dict[tuple[str, str, str], list[_RouteHandler]] = defaultdict(list)
    for file_path, result in parse_results.items():
        package_root = _longest_matching_package_root(file_path, next_package_roots)
        if package_root is None:
            continue
        request_path = _next_route_request_path(file_path)
        if request_path is None:
            continue
        for symbol in result.symbols:
            exported_methods = {
                name.upper()
                for name in symbol.exported_names
                if name.upper()
                in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
            }
            if symbol.kind != "route" or not exported_methods:
                continue
            target_symbol_id = symbol_ids.get(symbol.qualified_name)
            if target_symbol_id:
                for http_method in sorted(exported_methods):
                    candidates[(package_root, request_path, http_method)].append(
                        _RouteHandler(
                            package_root=package_root,
                            request_path=request_path,
                            http_method=http_method,
                            file_path=file_path,
                            target_symbol_id=target_symbol_id,
                        )
                    )

    return {
        key: handlers[0]
        for key, handlers in candidates.items()
        if len(handlers) == 1
    }


def _resolve_local_symbol_id(
    file_path: str,
    source_qualified_name: str | None,
    target: str,
    symbol_ids: dict[str, str],
) -> str | None:
    candidates: list[str] = []
    if source_qualified_name and source_qualified_name.startswith(f"{file_path}::"):
        current = source_qualified_name
        while True:
            candidates.append(f"{current}.{target}")
            local_name = current.split("::", 1)[1]
            if "." not in local_name:
                break
            current = f"{file_path}::{local_name.rsplit('.', 1)[0]}"
    candidates.append(f"{file_path}::{target}")
    for candidate in candidates:
        target_symbol_id = symbol_ids.get(candidate)
        if target_symbol_id:
            return target_symbol_id
    return None


def _resolve_parsed_edge(
    *,
    file_path: str,
    parsed_edge: ParsedEdge,
    known_paths: set[str],
    symbol_ids: dict[str, str],
    display_symbol_ids: dict[tuple[str, str], str],
    route_handlers: dict[tuple[str, str, str], _RouteHandler],
    next_package_roots: set[str],
) -> list[_ResolvedEdge]:
    target_path = parsed_edge.target
    target_symbol_id = None
    metadata: dict[str, object] = dict(parsed_edge.metadata)

    if parsed_edge.relation == "IMPORTS":
        target_path = _resolve_import(file_path, target_path, known_paths)
        metadata["resolved_path"] = target_path
        metadata["resolution"] = (
            "local_file" if target_path in known_paths else "module_specifier"
        )
    elif parsed_edge.relation == "CALLS":
        short_target = target_path.rsplit(".", 1)[-1]
        target_symbol_id = display_symbol_ids.get((file_path, short_target))
        metadata["resolution"] = (
            "same_file_symbol" if target_symbol_id else "syntactic_target_only"
        )
    elif parsed_edge.relation == "TRIGGERS":
        target_symbol_id = _resolve_local_symbol_id(
            file_path,
            parsed_edge.source_qualified_name,
            parsed_edge.target,
            symbol_ids,
        )
        metadata["resolution"] = (
            "local_symbol" if target_symbol_id else "unresolved_identifier"
        )
    elif parsed_edge.relation == "REQUESTS":
        metadata_request_path = str(metadata.get("request_path") or "")
        request_path = (
            _normalize_literal_request_path(metadata_request_path)
            if metadata.get("target_scope") == "local"
            else None
        )
        http_method = str(metadata.get("http_method", "GET")).upper()
        source_package_root = _longest_matching_package_root(
            file_path, next_package_roots
        )
        route_handler = (
            route_handlers.get((source_package_root, request_path, http_method))
            if source_package_root is not None and request_path
            else None
        )
        metadata["resolution"] = (
            "exact_next_app_route" if route_handler else "literal_only"
        )
        request_edge = _ResolvedEdge(
            relation=parsed_edge.relation,
            source_qualified_name=parsed_edge.source_qualified_name,
            target_symbol_id=None,
            target_path=target_path,
            confidence=parsed_edge.confidence,
            start_line=parsed_edge.start_line,
            end_line=parsed_edge.end_line,
            metadata=metadata,
        )
        if route_handler is None:
            return [request_edge]
        handled_by_metadata: dict[str, object] = {
            "client": metadata.get("client"),
            "http_method": http_method,
            "request_path": request_path,
            "route_file_path": route_handler.file_path,
            "package_root": route_handler.package_root,
            "resolution": "exact_next_app_route",
            "derived_from_relation": "REQUESTS",
            "confidence_rationale": (
                "Literal request path and HTTP method exactly match one static Next.js "
                "App Router route handler."
            ),
            "extractor": "repository_semantic_resolver",
        }
        return [
            request_edge,
            _ResolvedEdge(
                relation="HANDLED_BY",
                source_qualified_name=parsed_edge.source_qualified_name,
                target_symbol_id=route_handler.target_symbol_id,
                target_path=route_handler.file_path,
                confidence=1.0,
                start_line=parsed_edge.start_line,
                end_line=parsed_edge.end_line,
                metadata=handled_by_metadata,
            ),
        ]

    return [
        _ResolvedEdge(
            relation=parsed_edge.relation,
            source_qualified_name=parsed_edge.source_qualified_name,
            target_symbol_id=target_symbol_id,
            target_path=target_path,
            confidence=parsed_edge.confidence,
            start_line=parsed_edge.start_line,
            end_line=parsed_edge.end_line,
            metadata=metadata,
        )
    ]


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
            db.execute(
                delete(NavigationArtifact).where(
                    NavigationArtifact.snapshot_id == snapshot_id
                )
            )
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
            next_package_roots = _find_next_package_roots(
                {path: record.content for path, record in file_records.items()}
            )
            route_handlers = _build_route_handler_index(
                parse_results, symbol_ids, next_package_roots
            )
            edge_count = 0
            for path, result in parse_results.items():
                file_record = file_records[path]
                for parsed_edge in result.edges:
                    resolved_edges = _resolve_parsed_edge(
                        file_path=path,
                        parsed_edge=parsed_edge,
                        known_paths=known_paths,
                        symbol_ids=symbol_ids,
                        display_symbol_ids=display_symbol_ids,
                        route_handlers=route_handlers,
                        next_package_roots=next_package_roots,
                    )
                    for resolved_edge in resolved_edges:
                        db.add(
                            SymbolEdge(
                                snapshot_id=snapshot_id,
                                source_file_id=file_record.id,
                                source_symbol_id=symbol_ids.get(
                                    resolved_edge.source_qualified_name or ""
                                ),
                                target_symbol_id=resolved_edge.target_symbol_id,
                                target_path=resolved_edge.target_path,
                                relation=resolved_edge.relation,
                                confidence=resolved_edge.confidence,
                                analysis_method=SEMANTIC_GRAPH_VERSION,
                                source_start_line=resolved_edge.start_line,
                                source_end_line=resolved_edge.end_line,
                                metadata_json={
                                    **resolved_edge.metadata,
                                    "semantic_graph_version": SEMANTIC_GRAPH_VERSION,
                                },
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
            snapshot.parser_version = SEMANTIC_GRAPH_VERSION
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
