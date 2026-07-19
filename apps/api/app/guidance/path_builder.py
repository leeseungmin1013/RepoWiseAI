from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CodeChunk,
    FileRecord,
    GuidedPath,
    GuidedStep,
    RepositorySnapshot,
    Symbol,
    SymbolEdge,
)

PATH_VERSION = "guided-tour-v1"
GENERATION_METHOD = "deterministic-structure-v1"
ENTRY_PATHS = (
    "src/app/page.tsx",
    "app/page.tsx",
    "src/pages/index.tsx",
    "src/main.tsx",
    "src/index.ts",
    "server.ts",
    "index.ts",
    "index.js",
    "index.d.ts",
)
CODE_LANGUAGES = {"typescript", "tsx", "javascript", "jsx"}
TEST_PATH = re.compile(
    r"(^|/)(__tests__|tests?|specs?)(/|$)|(^|/)(test|spec)\.[^/]+$|\.(test|spec)\.[^/]+$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TourCandidate:
    chunk_id: str
    file_id: str
    path: str
    language: str
    chunk_type: str
    start_line: int
    end_line: int
    title: str
    symbol_id: str | None = None
    symbol_name: str | None = None
    symbol_kind: str | None = None
    signature: str | None = None
    parent_chunk_id: str | None = None
    concept_ids: tuple[str, ...] = ()

    @property
    def is_test(self) -> bool:
        return bool(TEST_PATH.search(self.path))


@dataclass(frozen=True)
class GuidedStepDraft:
    chunk_id: str
    step_type: str
    title: str
    learning_objective: str
    summary: str
    concept_ids: tuple[str, ...]
    checkpoint: dict[str, str]
    estimated_minutes: int


def ensure_guided_path(db: Session, snapshot_id: str) -> GuidedPath:
    snapshot = db.scalar(
        select(RepositorySnapshot)
        .where(RepositorySnapshot.id == snapshot_id)
        .options(selectinload(RepositorySnapshot.repository))
        .with_for_update()
    )
    if snapshot is None:
        raise ValueError("Snapshot not found")

    existing = db.scalar(
        select(GuidedPath)
        .where(
            GuidedPath.snapshot_id == snapshot_id,
            GuidedPath.path_version == PATH_VERSION,
        )
        .options(selectinload(GuidedPath.steps))
    )
    if existing is not None:
        return existing

    candidates = _load_candidates(db, snapshot_id)
    call_targets = _load_call_targets(db, snapshot_id)
    drafts = select_guided_steps(candidates, call_targets)
    if not drafts:
        raise ValueError("Snapshot has no verified code chunks for a guided path")

    repository_name = f"{snapshot.repository.owner}/{snapshot.repository.name}"
    path = GuidedPath(
        snapshot_id=snapshot_id,
        title=f"{repository_name} 핵심 코드 Tour",
        goal="진입점에서 시작해 핵심 심볼과 검증 코드를 순서대로 읽습니다.",
        difficulty="beginner",
        path_version=PATH_VERSION,
        generation_method=GENERATION_METHOD,
    )
    db.add(path)
    db.flush()
    for ordinal, draft in enumerate(drafts, start=1):
        db.add(
            GuidedStep(
                path_id=path.id,
                chunk_id=draft.chunk_id,
                ordinal=ordinal,
                step_type=draft.step_type,
                title=draft.title,
                learning_objective=draft.learning_objective,
                summary=draft.summary,
                concept_ids=list(draft.concept_ids),
                checkpoint=draft.checkpoint,
                estimated_minutes=draft.estimated_minutes,
            )
        )
    db.flush()
    db.refresh(path)
    return path


def select_guided_steps(
    candidates: list[TourCandidate],
    call_targets: dict[str, list[str]] | None = None,
    *,
    max_steps: int = 5,
) -> list[GuidedStepDraft]:
    if not candidates or max_steps < 1:
        return []
    call_targets = call_targets or {}
    entry_path = _choose_entry_path(candidates)
    selected: list[tuple[str, TourCandidate]] = []
    selected_ids: set[str] = set()

    def add(step_type: str, candidate: TourCandidate | None) -> None:
        if candidate is None or candidate.chunk_id in selected_ids or len(selected) >= max_steps:
            return
        selected.append((step_type, candidate))
        selected_ids.add(candidate.chunk_id)

    entry_candidates = [item for item in candidates if item.path == entry_path]
    orientation = min(
        (item for item in entry_candidates if item.chunk_type == "file"),
        key=lambda item: item.start_line,
        default=None,
    )
    add("orientation", orientation)

    symbol_candidates = [item for item in entry_candidates if item.chunk_type == "symbol"]
    core = max(symbol_candidates, key=lambda item: _symbol_score(item, call_targets), default=None)
    add("core_flow", core)

    supporting = _supporting_candidate(core, symbol_candidates, call_targets, candidates)
    add("supporting_flow", supporting)

    error_candidate = max(
        (
            item
            for item in candidates
            if "exception_handling" in item.concept_ids and item.chunk_id not in selected_ids
        ),
        key=lambda item: (item.path == entry_path, item.chunk_type == "symbol", -item.start_line),
        default=None,
    )
    add("error_path", error_candidate)

    test_candidate = min(
        (
            item
            for item in candidates
            if item.is_test and item.chunk_type in {"symbol", "file"}
            and item.chunk_id not in selected_ids
        ),
        key=lambda item: (item.chunk_type != "symbol", item.path, item.start_line),
        default=None,
    )
    add("test", test_candidate)

    if len(selected) < min(3, max_steps):
        fallback = sorted(
            (item for item in candidates if item.chunk_id not in selected_ids),
            key=lambda item: (
                item.chunk_type != "symbol",
                item.path != entry_path,
                -_symbol_score(item, call_targets),
                item.path,
                item.start_line,
            ),
        )
        for item in fallback:
            add("supporting_flow", item)
            if len(selected) >= min(3, max_steps):
                break

    return [_to_step_draft(step_type, candidate) for step_type, candidate in selected]


def _load_candidates(db: Session, snapshot_id: str) -> list[TourCandidate]:
    rows = db.execute(
        select(CodeChunk, FileRecord, Symbol)
        .join(FileRecord, CodeChunk.file_id == FileRecord.id)
        .outerjoin(Symbol, CodeChunk.symbol_id == Symbol.id)
        .where(CodeChunk.snapshot_id == snapshot_id)
        .order_by(FileRecord.path, CodeChunk.ordinal)
    ).all()
    candidates: list[TourCandidate] = []
    for chunk, file, symbol in rows:
        metadata = chunk.metadata_json or {}
        candidates.append(
            TourCandidate(
                chunk_id=chunk.id,
                file_id=file.id,
                path=file.path,
                language=file.language,
                chunk_type=chunk.chunk_type,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                title=chunk.title,
                symbol_id=symbol.id if symbol else None,
                symbol_name=symbol.display_name if symbol else None,
                symbol_kind=symbol.kind if symbol else None,
                signature=symbol.signature if symbol else None,
                parent_chunk_id=chunk.parent_chunk_id,
                concept_ids=tuple(metadata.get("concept_candidates") or ()),
            )
        )
    return candidates


def _load_call_targets(db: Session, snapshot_id: str) -> dict[str, list[str]]:
    edges = db.execute(
        select(SymbolEdge.source_symbol_id, SymbolEdge.target_symbol_id).where(
            SymbolEdge.snapshot_id == snapshot_id,
            SymbolEdge.relation == "CALLS",
            SymbolEdge.source_symbol_id.is_not(None),
            SymbolEdge.target_symbol_id.is_not(None),
        )
    ).all()
    targets: defaultdict[str, list[str]] = defaultdict(list)
    for source_id, target_id in edges:
        if source_id and target_id and target_id not in targets[source_id]:
            targets[source_id].append(target_id)
    return dict(targets)


def _choose_entry_path(candidates: list[TourCandidate]) -> str:
    available = {item.path for item in candidates}
    for path in ENTRY_PATHS:
        if path in available:
            return path
    source_paths = sorted(
        {
            item.path
            for item in candidates
            if item.language in CODE_LANGUAGES and not item.is_test
        },
        key=lambda path: (path.count("/"), path),
    )
    if source_paths:
        return source_paths[0]
    return min(item.path for item in candidates)


def _symbol_score(
    candidate: TourCandidate, call_targets: dict[str, list[str]]
) -> tuple[int, int, int]:
    if candidate.chunk_type != "symbol":
        return (-100, 0, -candidate.start_line)
    signature = (candidate.signature or "").lower()
    kind_weights = {
        "function": 8,
        "class": 7,
        "component": 7,
        "route": 7,
        "method": 5,
    }
    score = kind_weights.get(candidate.symbol_kind or "", 3)
    score += 6 if "export default" in signature else 0
    score += 3 if "export" in signature else 0
    score += 2 if candidate.parent_chunk_id is None else 0
    degree = len(call_targets.get(candidate.symbol_id or "", []))
    return (score, degree, -candidate.start_line)


def _supporting_candidate(
    core: TourCandidate | None,
    entry_symbols: list[TourCandidate],
    call_targets: dict[str, list[str]],
    all_candidates: list[TourCandidate],
) -> TourCandidate | None:
    if core is None:
        return None
    by_symbol = {item.symbol_id: item for item in all_candidates if item.symbol_id}
    for target_id in call_targets.get(core.symbol_id or "", []):
        target = by_symbol.get(target_id)
        if target and target.chunk_id != core.chunk_id:
            return target
    nested = [item for item in entry_symbols if item.parent_chunk_id == core.chunk_id]
    if nested:
        return max(nested, key=lambda item: _symbol_score(item, call_targets))
    remaining = [item for item in entry_symbols if item.chunk_id != core.chunk_id]
    return max(remaining, key=lambda item: _symbol_score(item, call_targets), default=None)


def _to_step_draft(step_type: str, candidate: TourCandidate) -> GuidedStepDraft:
    subject = candidate.symbol_name or candidate.path
    copy = {
        "orientation": (
            "프로젝트 입구 확인",
            "파일의 공개 진입점과 큰 역할을 찾습니다.",
            f"{candidate.path}에서 먼저 읽을 위치와 파일의 경계를 확인합니다.",
            "이 파일에서 외부에 공개되는 항목을 찾았나요?",
            2,
        ),
        "core_flow": (
            f"{subject} 핵심 흐름",
            "입력, 주요 분기, 반환값을 순서대로 따라갑니다.",
            f"{subject} 심볼의 시작부터 반환까지 핵심 흐름을 읽습니다.",
            "입력값이 반환값으로 바뀌는 핵심 지점을 찾았나요?",
            4,
        ),
        "supporting_flow": (
            f"{subject} 연결 흐름",
            "핵심 흐름을 돕는 호출이나 보조 책임을 확인합니다.",
            f"{subject}이 앞 단계와 어떻게 연결되는지 확인합니다.",
            "앞 단계가 이 코드를 필요로 하는 이유를 설명할 수 있나요?",
            3,
        ),
        "error_path": (
            f"{subject} 예외 흐름",
            "실패와 예외가 처리되는 경로를 확인합니다.",
            f"{subject}에서 정상 흐름과 실패 흐름이 갈라지는 위치를 읽습니다.",
            "실패할 때 실행되는 분기와 결과를 찾았나요?",
            3,
        ),
        "test": (
            f"{subject} 테스트 근거",
            "코드의 기대 동작이 테스트로 어떻게 표현되는지 확인합니다.",
            f"{candidate.path}에서 앞 단계의 동작을 검증하는 근거를 찾습니다.",
            "테스트가 보장하는 입력과 결과를 한 쌍 찾았나요?",
            3,
        ),
    }[step_type]
    concept_ids = list(candidate.concept_ids)
    kind_concept = {
        "function": "function",
        "method": "function",
        "class": "class",
        "component": "react_component",
    }.get(candidate.symbol_kind or "")
    if kind_concept and kind_concept not in concept_ids:
        concept_ids.insert(0, kind_concept)
    return GuidedStepDraft(
        chunk_id=candidate.chunk_id,
        step_type=step_type,
        title=copy[0],
        learning_objective=copy[1],
        summary=copy[2],
        concept_ids=tuple(concept_ids[:4]),
        checkpoint={"type": "self_check", "prompt": copy[3]},
        estimated_minutes=copy[4],
    )
