from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.guidance.path_builder import ENTRY_PATHS
from app.models import (
    CodeChunk,
    FileRecord,
    LearnerProfile,
    LearningLesson,
    LearningModule,
    LearningPath,
    LearningStep,
    RepositorySnapshot,
    Symbol,
    SymbolEdge,
)
from app.retrieval.hybrid import evidence_id_for_chunk

PATH_VERSION = "adaptive-curriculum-v1"
TEST_PATH = re.compile(r"(^|/)(__tests__|tests?)(/|$)|(^|/)(test|spec)\.|\.(test|spec)\.", re.I)
DATA_TERMS = re.compile(r"(data|model|schema|store|state|database|db|prisma|service)", re.I)
FAILURE_TERMS = re.compile(r"(error|exception|validat|auth|guard|fallback)", re.I)
CONFIG_PATH = re.compile(r"(^|/)(package\.json|tsconfig|next\.config|vite\.config|readme)", re.I)


@dataclass(frozen=True)
class CurriculumCandidate:
    chunk_id: str
    file_id: str
    path: str
    chunk_type: str
    title: str
    start_line: int
    end_line: int
    symbol_id: str | None
    symbol_name: str | None
    symbol_kind: str | None
    signature: str | None
    concept_ids: tuple[str, ...]
    degree: int

    @property
    def evidence_id(self) -> str:
        return evidence_id_for_chunk(self.chunk_id)

    @property
    def is_test(self) -> bool:
        return bool(TEST_PATH.search(self.path))


def ensure_learning_path(
    db: Session,
    *,
    snapshot_id: str,
    learner_profile_id: str,
    goal: str | None = None,
) -> LearningPath:
    snapshot = db.scalar(
        select(RepositorySnapshot)
        .where(RepositorySnapshot.id == snapshot_id)
        .options(selectinload(RepositorySnapshot.repository))
        .with_for_update()
    )
    if snapshot is None:
        raise ValueError("Snapshot not found")
    if snapshot.status != "ready" or snapshot.chunk_count == 0:
        raise ValueError("Snapshot analysis is not ready")
    profile = db.get(LearnerProfile, learner_profile_id)
    if profile is None:
        raise ValueError("Learner profile not found")
    existing = db.scalar(
        select(LearningPath).where(
            LearningPath.snapshot_id == snapshot_id,
            LearningPath.learner_profile_id == learner_profile_id,
            LearningPath.path_version == PATH_VERSION,
        )
    )
    if existing is not None:
        return existing

    candidates = load_curriculum_candidates(db, snapshot_id)
    if not candidates:
        raise ValueError("Snapshot has no verified curriculum candidates")
    symbol_count = (
        db.scalar(select(func.count(Symbol.id)).where(Symbol.snapshot_id == snapshot_id)) or 0
    )
    modules = plan_curriculum(candidates, profile, symbol_count=symbol_count)
    repository_name = f"{snapshot.repository.owner}/{snapshot.repository.name}"
    resolved_goal = goal or profile.goal
    coverage = {
        key: (
            "covered" if any(module_type == key for module_type, _ in modules) else "not_applicable"
        )
        for key in (
            "orientation",
            "foundations",
            "architecture",
            "feature_flow",
            "data_failure",
            "test_apply",
        )
    }
    path = LearningPath(
        snapshot_id=snapshot_id,
        learner_profile_id=learner_profile_id,
        title=f"{repository_name} 전체 이해 경로",
        goal=resolved_goal,
        path_version=PATH_VERSION,
        generation_method="verified-structure-v1",
        coverage=coverage,
        model_metadata={
            "planner": "deterministic-candidate-planner-v1",
            "profile_assessment_version": profile.assessment_version,
            "profile_fingerprint": profile_fingerprint(profile),
            "candidate_count": len(candidates),
            "revision": 1,
        },
    )
    db.add(path)
    db.flush()

    path.estimated_minutes = append_curriculum_modules(
        db,
        path=path,
        modules=modules,
        profile=profile,
        start_ordinal=1,
    )
    db.flush()
    return path


def append_curriculum_modules(
    db: Session,
    *,
    path: LearningPath,
    modules: list[tuple[str, list[CurriculumCandidate]]],
    profile: LearnerProfile,
    start_ordinal: int,
    excluded_chunk_ids: set[str] | None = None,
) -> int:
    excluded = excluded_chunk_ids or set()
    total_minutes = 0
    module_ordinal = start_ordinal
    for module_type, selected_candidates in modules:
        selected = [
            candidate for candidate in selected_candidates if candidate.chunk_id not in excluded
        ]
        if not selected:
            continue
        module_copy = MODULE_COPY[module_type]
        module = LearningModule(
            path_id=path.id,
            ordinal=module_ordinal,
            module_type=module_type,
            title=module_copy[0],
            objective=module_copy[1],
            required=module_type != "foundations" or bool(selected),
            coverage_keys=[module_type],
        )
        db.add(module)
        db.flush()
        module_minutes = 0
        for lesson_ordinal, candidate in enumerate(selected, start=1):
            minutes = _lesson_minutes(candidate, profile)
            concepts = list(candidate.concept_ids[:4])
            lesson = LearningLesson(
                module_id=module.id,
                ordinal=lesson_ordinal,
                lesson_type=_lesson_type(module_type, candidate),
                title=_lesson_title(module_type, candidate),
                objective=_lesson_objective(module_type, candidate),
                required_concept_ids=concepts,
                evidence_ids=[candidate.evidence_id],
                checkpoint={
                    "type": "self_check",
                    "prompt": _checkpoint(module_type, candidate),
                },
                estimated_minutes=minutes,
                optional=False,
            )
            db.add(lesson)
            db.flush()
            db.add(
                LearningStep(
                    lesson_id=lesson.id,
                    ordinal=1,
                    step_type="code" if candidate.chunk_type != "file" else "orientation",
                    chunk_id=candidate.chunk_id,
                    title=candidate.symbol_name or candidate.path,
                    instruction=_instruction(candidate, profile),
                    evidence_ids=[candidate.evidence_id],
                    metadata_json={
                        "path": candidate.path,
                        "start_line": candidate.start_line,
                        "end_line": candidate.end_line,
                        "concept_ids": concepts,
                    },
                )
            )
            module_minutes += minutes
        module.estimated_minutes = module_minutes
        total_minutes += module_minutes
        module_ordinal += 1
    return total_minutes


def profile_fingerprint(profile: LearnerProfile) -> str:
    payload = {
        "goal": profile.goal,
        "preferred_explanation": profile.preferred_explanation or [],
        "pace": profile.pace,
        "concept_mastery": profile.concept_mastery or {},
        "assessment_version": profile.assessment_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def load_curriculum_candidates(db: Session, snapshot_id: str) -> list[CurriculumCandidate]:
    degree_rows = db.execute(
        select(SymbolEdge.source_symbol_id, func.count(SymbolEdge.id))
        .where(
            SymbolEdge.snapshot_id == snapshot_id,
            SymbolEdge.source_symbol_id.is_not(None),
        )
        .group_by(SymbolEdge.source_symbol_id)
    ).all()
    degrees = {symbol_id: count for symbol_id, count in degree_rows}
    rows = db.execute(
        select(CodeChunk, FileRecord, Symbol)
        .join(FileRecord, CodeChunk.file_id == FileRecord.id)
        .outerjoin(Symbol, CodeChunk.symbol_id == Symbol.id)
        .where(CodeChunk.snapshot_id == snapshot_id)
        .order_by(FileRecord.path, CodeChunk.ordinal)
    ).all()
    result: list[CurriculumCandidate] = []
    for chunk, file, symbol in rows:
        metadata = chunk.metadata_json or {}
        result.append(
            CurriculumCandidate(
                chunk_id=chunk.id,
                file_id=file.id,
                path=file.path,
                chunk_type=chunk.chunk_type,
                title=chunk.title,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                symbol_id=symbol.id if symbol else None,
                symbol_name=symbol.display_name if symbol else None,
                symbol_kind=symbol.kind if symbol else None,
                signature=symbol.signature if symbol else None,
                concept_ids=tuple(metadata.get("concept_candidates") or []),
                degree=int(degrees.get(symbol.id if symbol else None, 0)),
            )
        )
    return result


def plan_curriculum(
    candidates: list[CurriculumCandidate],
    profile: LearnerProfile,
    *,
    symbol_count: int,
) -> list[tuple[str, list[CurriculumCandidate]]]:
    target = 18 if symbol_count <= 100 else 28
    target = min(40, max(15, target))
    selected_ids: set[str] = set()

    def take(items: list[CurriculumCandidate], limit: int) -> list[CurriculumCandidate]:
        result: list[CurriculumCandidate] = []
        for item in items:
            if item.chunk_id in selected_ids:
                continue
            selected_ids.add(item.chunk_id)
            result.append(item)
            if len(result) >= limit:
                break
        return result

    entry_rank = {path: index for index, path in enumerate(ENTRY_PATHS)}
    orientation_pool = sorted(
        (
            item
            for item in candidates
            if item.chunk_type == "file"
            and (item.path in entry_rank or CONFIG_PATH.search(item.path))
        ),
        key=lambda item: (
            0 if item.path.lower().startswith("readme") else 1,
            entry_rank.get(item.path, 999),
            item.start_line,
        ),
    )
    orientation = take(orientation_pool, 4)

    weak_concepts = {
        concept_id
        for concept_id, state in (profile.concept_mastery or {}).items()
        if state.get("score", 0.5) < 0.55
    }
    foundation_pool = sorted(
        (
            item
            for item in candidates
            if weak_concepts.intersection(item.concept_ids) and item.chunk_type == "symbol"
        ),
        key=_candidate_rank,
        reverse=True,
    )
    foundations = take(foundation_pool, 3 if profile.pace != "fast" else 1)

    architecture_pool = sorted(
        (item for item in candidates if item.chunk_type == "symbol" and not item.is_test),
        key=lambda item: (_candidate_rank(item), -item.path.count("/")),
        reverse=True,
    )
    architecture = _take_distinct_files(architecture_pool, selected_ids, 4)

    feature_pool = sorted(
        (
            item
            for item in candidates
            if item.chunk_type == "symbol"
            and not item.is_test
            and not DATA_TERMS.search(item.path)
            and "exception_handling" not in item.concept_ids
        ),
        key=_candidate_rank,
        reverse=True,
    )
    feature_flow = take(feature_pool, 7)

    data_failure_pool = sorted(
        (
            item
            for item in candidates
            if item.chunk_type == "symbol"
            and (
                DATA_TERMS.search(item.path)
                or FAILURE_TERMS.search(item.title)
                or "exception_handling" in item.concept_ids
            )
        ),
        key=_candidate_rank,
        reverse=True,
    )
    data_failure = take(data_failure_pool, 5)

    test_pool = sorted(
        (item for item in candidates if item.is_test and item.chunk_type in {"symbol", "file"}),
        key=lambda item: (item.chunk_type == "symbol", _candidate_rank(item)),
        reverse=True,
    )
    test_apply = take(test_pool, 4)

    groups = [
        ("orientation", orientation),
        ("foundations", foundations),
        ("architecture", architecture),
        ("feature_flow", feature_flow),
        ("data_failure", data_failure),
        ("test_apply", test_apply),
    ]
    selected_count = sum(len(items) for _, items in groups)
    if selected_count < target:
        fallback = sorted(
            (
                item
                for item in candidates
                if item.chunk_type == "symbol" and item.chunk_id not in selected_ids
            ),
            key=_candidate_rank,
            reverse=True,
        )
        needed = target - selected_count
        extra = take(fallback, needed)
        feature_flow.extend(extra)
    return [(module_type, items) for module_type, items in groups if items]


MODULE_COPY = {
    "orientation": ("프로젝트 방향 잡기", "목적, 실행 방법, 진입점을 먼저 확인합니다."),
    "foundations": ("필요한 배경지식", "현재 코드에 실제 등장하는 선수 개념을 보충합니다."),
    "architecture": ("구조와 책임", "핵심 모듈의 역할과 경계를 파악합니다."),
    "feature_flow": ("핵심 기능 흐름", "중요한 심볼을 따라 입력과 결과의 이동을 이해합니다."),
    "data_failure": ("데이터와 실패 흐름", "상태, 저장, 검증, 오류 처리 위치를 확인합니다."),
    "test_apply": ("테스트와 적용", "기대 동작을 검증하고 변경 전 확인 범위를 정리합니다."),
}


def _candidate_rank(item: CurriculumCandidate) -> tuple[int, int, int]:
    signature = (item.signature or "").lower()
    kind_score = {
        "route": 9,
        "component": 8,
        "class": 8,
        "function": 7,
        "method": 6,
    }.get(item.symbol_kind or "", 3)
    export_score = 4 if "export default" in signature else 2 if "export" in signature else 0
    return (kind_score + export_score, item.degree, -item.start_line)


def _take_distinct_files(
    pool: list[CurriculumCandidate], selected_ids: set[str], limit: int
) -> list[CurriculumCandidate]:
    result: list[CurriculumCandidate] = []
    paths: Counter[str] = Counter()
    for item in pool:
        if item.chunk_id in selected_ids or paths[item.path] >= 1:
            continue
        selected_ids.add(item.chunk_id)
        paths[item.path] += 1
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _lesson_type(module_type: str, candidate: CurriculumCandidate) -> str:
    if module_type == "foundations":
        return "concept_bridge"
    if candidate.is_test:
        return "test_reading"
    if candidate.chunk_type == "file":
        return "orientation"
    return "code_flow"


def _lesson_title(module_type: str, candidate: CurriculumCandidate) -> str:
    subject = candidate.symbol_name or candidate.path
    suffix = {
        "orientation": "살펴보기",
        "foundations": "에 필요한 개념",
        "architecture": "의 책임과 연결",
        "feature_flow": "실행 흐름",
        "data_failure": "데이터·오류 흐름",
        "test_apply": "테스트 근거",
    }[module_type]
    return f"{subject} {suffix}"


def _lesson_objective(module_type: str, candidate: CurriculumCandidate) -> str:
    subject = candidate.symbol_name or candidate.path
    return {
        "orientation": f"{subject}에서 프로젝트의 시작점과 공개 범위를 찾습니다.",
        "foundations": f"{subject}을 읽는 데 필요한 문법과 비동기 개념을 현재 코드에 연결합니다.",
        "architecture": f"{subject}의 책임과 다른 모듈과의 경계를 설명합니다.",
        "feature_flow": f"{subject}의 입력, 주요 호출, 반환 결과를 순서대로 추적합니다.",
        "data_failure": f"{subject}에서 데이터가 바뀌거나 실패가 처리되는 지점을 찾습니다.",
        "test_apply": f"{subject}이 보장하는 기대 동작과 수정 전 확인 항목을 정리합니다.",
    }[module_type]


def _checkpoint(module_type: str, candidate: CurriculumCandidate) -> str:
    subject = candidate.symbol_name or candidate.path
    return {
        "orientation": f"{subject}이 프로젝트에서 맡는 역할을 한 문장으로 말할 수 있나요?",
        "foundations": "이 코드의 실행 순서와 기다리는 지점을 찾았나요?",
        "architecture": f"{subject}이 다른 파일과 나누어 맡은 책임을 찾았나요?",
        "feature_flow": "입력값이 어느 호출을 거쳐 결과가 되는지 설명할 수 있나요?",
        "data_failure": "정상 흐름과 실패 흐름이 갈라지는 위치를 찾았나요?",
        "test_apply": "이 테스트가 보장하는 입력과 결과를 찾았나요?",
    }[module_type]


def _instruction(candidate: CurriculumCandidate, profile: LearnerProfile) -> str:
    if "line_by_line" in (profile.preferred_explanation or []):
        return "코드를 열고 각 statement의 입력과 결과를 위에서 아래로 따라가세요."
    if "architecture" in (profile.preferred_explanation or []):
        return "세부 문법보다 이 심볼의 책임과 연결된 모듈을 먼저 확인하세요."
    return "코드 근거를 열고 핵심 분기와 데이터 이동을 확인하세요."


def _lesson_minutes(candidate: CurriculumCandidate, profile: LearnerProfile) -> int:
    base = 4 if candidate.chunk_type == "symbol" else 3
    if profile.pace == "careful":
        base += 2
    elif profile.pace == "fast":
        base = max(2, base - 1)
    return base
