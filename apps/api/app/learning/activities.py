from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analysis.typescript import TypeScriptAnalyzer
from app.learning.explanations import SegmentDraft, segment_source
from app.models import (
    CodeChunk,
    FileRecord,
    LearningActivity,
    LearningStep,
    Symbol,
    SymbolEdge,
)
from app.retrieval.hybrid import evidence_id_for_chunk

GENERATOR_VERSION = "grounded-checkpoint-v2"


@dataclass(frozen=True)
class CallCandidate:
    target: str
    start_line: int
    end_line: int
    source: str
    relation: str = "CALLS"
    confidence: float = 0.65


@dataclass(frozen=True)
class ActivitySpec:
    activity_type: str
    prompt: str
    choices: list[dict]
    answer_key: str
    explanation: str
    concept_ids: list[str]
    evidence: dict


def ensure_learning_activity(
    db: Session, *, step_id: str
) -> tuple[LearningActivity, LearningStep, FileRecord]:
    step = db.scalar(
        select(LearningStep)
        .where(LearningStep.id == step_id)
        .options(
            selectinload(LearningStep.chunk),
            selectinload(LearningStep.lesson),
        )
    )
    if step is None or step.chunk is None:
        raise ValueError("Learning step has no source-code chunk")
    existing = db.scalar(
        select(LearningActivity).where(
            LearningActivity.step_id == step.id,
            LearningActivity.generator_version == GENERATOR_VERSION,
        )
    )
    file = db.get(FileRecord, step.chunk.file_id)
    if file is None or not _chunk_matches_file(step.chunk, file):
        raise ValueError("Learning activity source could not be verified")
    if existing is not None:
        return existing, step, file

    other_paths = list(
        db.scalars(
            select(FileRecord.path)
            .where(
                FileRecord.snapshot_id == step.chunk.snapshot_id,
                FileRecord.id != file.id,
            )
            .order_by(FileRecord.path)
            .limit(12)
        )
    )
    symbol_names = list(
        db.scalars(
            select(Symbol.display_name)
            .where(Symbol.snapshot_id == step.chunk.snapshot_id)
            .order_by(Symbol.display_name)
            .limit(30)
        )
    )
    resolved_calls = _resolved_edge_candidates(db, step.chunk, file, "CALLS")
    resolved_imports = _resolved_edge_candidates(db, step.chunk, file, "IMPORTS")
    spec = build_activity_spec(
        chunk=step.chunk,
        file=file,
        concepts=_concepts_for_step(step),
        other_paths=other_paths,
        symbol_names=symbol_names,
        resolved_calls=resolved_calls,
        resolved_imports=resolved_imports,
    )
    activity = LearningActivity(
        step_id=step.id,
        activity_type=spec.activity_type,
        prompt=spec.prompt,
        choices=spec.choices,
        answer_key=spec.answer_key,
        explanation=spec.explanation,
        concept_ids=spec.concept_ids,
        evidence=spec.evidence,
        source_hash=step.chunk.content_hash,
        generator_version=GENERATOR_VERSION,
        verification_status="verified",
    )
    db.add(activity)
    db.flush()
    return activity, step, file


def build_activity_spec(
    *,
    chunk: CodeChunk,
    file: FileRecord,
    concepts: list[str],
    other_paths: list[str],
    symbol_names: list[str],
    resolved_calls: list[CallCandidate] | None = None,
    resolved_imports: list[CallCandidate] | None = None,
) -> ActivitySpec:
    segments = segment_source(chunk)
    throws = [item for item in segments if item.node_type == "throw_statement"]
    if throws:
        target = throws[0]
        return _statement_activity(
            chunk=chunk,
            file=file,
            target=target,
            segments=segments,
            activity_type="select_error_path",
            prompt="다음 중 이 코드에서 실패 흐름을 직접 시작하는 실제 문장은 무엇인가요?",
            explanation="throw 문장은 정상 흐름을 중단하고 오류를 호출한 쪽으로 전달합니다.",
            concepts=[*concepts, "exception_handling"],
        )

    returns = [item for item in segments if item.node_type == "return_statement"]
    if returns:
        target = returns[-1]
        return _statement_activity(
            chunk=chunk,
            file=file,
            target=target,
            segments=segments,
            activity_type="trace_return_value",
            prompt="다음 중 이 함수가 호출자에게 결과를 돌려주는 실제 문장은 무엇인가요?",
            explanation="return 문장은 현재 함수를 끝내고 표현식의 값을 호출자에게 전달합니다.",
            concepts=[*concepts, "return", "function"],
        )

    calls = resolved_calls or _call_candidates(chunk, file)
    if calls:
        target = calls[0]
        distractors = [item.target for item in calls[1:]]
        distractors.extend(symbol_names)
        choices, answer_key = _choices(
            correct=target.target,
            distractors=distractors,
            seed=f"{chunk.id}:predict_next_call",
        )
        return ActivitySpec(
            activity_type="predict_next_call",
            prompt="이 코드에서 가장 먼저 실행을 넘기는 함수 호출 대상은 무엇인가요?",
            choices=choices,
            answer_key=answer_key,
            explanation=(
                f"L{target.start_line}의 `{target.source}` 표현식이 "
                f"`{target.target}` 호출을 시작합니다."
            ),
            concept_ids=list(dict.fromkeys([*concepts, "call", "function"])),
            evidence=_evidence(
                chunk,
                file,
                target.start_line,
                target.end_line,
                target.source,
                relation=target.relation,
                relation_confidence=target.confidence,
            ),
        )

    imports = resolved_imports or []
    if imports:
        target = imports[0]
        choices, answer_key = _choices(
            correct=target.target,
            distractors=[item.target for item in imports[1:]] + other_paths,
            seed=f"{chunk.id}:trace_dependency",
        )
        return ActivitySpec(
            activity_type="trace_dependency",
            prompt="이 코드가 가장 먼저 가져오는 실제 모듈 또는 파일은 무엇인가요?",
            choices=choices,
            answer_key=answer_key,
            explanation=(
                f"L{target.start_line}의 import 문이 `{target.target}` 의존성을 연결합니다."
            ),
            concept_ids=list(dict.fromkeys([*concepts, "module"])),
            evidence=_evidence(
                chunk,
                file,
                target.start_line,
                target.end_line,
                target.source,
                relation=target.relation,
                relation_confidence=target.confidence,
            ),
        )

    choices, answer_key = _choices(
        correct=file.path,
        distractors=other_paths,
        seed=f"{chunk.id}:locate_source_file",
    )
    return ActivitySpec(
        activity_type="locate_source_file",
        prompt="이 레슨에서 직접 확인하고 있는 실제 저장소 파일은 무엇인가요?",
        choices=choices,
        answer_key=answer_key,
        explanation=f"현재 레슨의 검증된 코드 근거는 `{file.path}`에 있습니다.",
        concept_ids=list(dict.fromkeys(concepts)),
        evidence=_evidence(
            chunk,
            file,
            chunk.start_line,
            chunk.end_line,
            _preview(chunk.content),
        ),
    )


def _statement_activity(
    *,
    chunk: CodeChunk,
    file: FileRecord,
    target: SegmentDraft,
    segments: list[SegmentDraft],
    activity_type: str,
    prompt: str,
    explanation: str,
    concepts: list[str],
) -> ActivitySpec:
    distractors = [
        item.source
        for item in segments
        if item.segment_id != target.segment_id
        and item.node_type
        in {
            "lexical_declaration",
            "expression_statement",
            "return_statement",
            "throw_statement",
            "if_statement",
        }
    ]
    choices, answer_key = _choices(
        correct=_choice_label(target.source),
        distractors=[_choice_label(item) for item in distractors],
        seed=f"{chunk.id}:{activity_type}",
    )
    return ActivitySpec(
        activity_type=activity_type,
        prompt=prompt,
        choices=choices,
        answer_key=answer_key,
        explanation=f"L{target.start_line}: {explanation}",
        concept_ids=list(dict.fromkeys(concepts)),
        evidence=_evidence(
            chunk,
            file,
            target.start_line,
            target.end_line,
            target.source,
        ),
    )


def _call_candidates(chunk: CodeChunk, file: FileRecord) -> list[CallCandidate]:
    if chunk.language not in {"typescript", "tsx", "javascript", "jsx"}:
        return []
    parsed = TypeScriptAnalyzer().parse(file.path, chunk.content, chunk.language)
    lines = chunk.content.splitlines()
    result: list[CallCandidate] = []
    seen: set[tuple[str, int]] = set()
    for edge in parsed.edges:
        if edge.relation != "CALLS":
            continue
        start_line = chunk.start_line + edge.start_line - 1
        end_line = chunk.start_line + edge.end_line - 1
        key = (edge.target, start_line)
        if key in seen:
            continue
        seen.add(key)
        local_index = max(0, edge.start_line - 1)
        source = lines[local_index].strip() if local_index < len(lines) else edge.target
        result.append(
            CallCandidate(
                target=edge.target,
                start_line=start_line,
                end_line=end_line,
                source=source,
            )
        )
    return sorted(result, key=lambda item: (item.start_line, item.target))


def _resolved_edge_candidates(
    db: Session,
    chunk: CodeChunk,
    file: FileRecord,
    relation: str,
) -> list[CallCandidate]:
    conditions = [
        SymbolEdge.snapshot_id == chunk.snapshot_id,
        SymbolEdge.source_file_id == file.id,
        SymbolEdge.relation == relation,
        SymbolEdge.source_start_line >= chunk.start_line,
        SymbolEdge.source_end_line <= chunk.end_line,
    ]
    if relation == "CALLS" and chunk.symbol_id:
        conditions.append(SymbolEdge.source_symbol_id == chunk.symbol_id)
    rows = db.execute(
        select(SymbolEdge, Symbol)
        .outerjoin(Symbol, SymbolEdge.target_symbol_id == Symbol.id)
        .where(*conditions)
        .order_by(SymbolEdge.source_start_line, SymbolEdge.id)
    ).all()
    lines = file.content.splitlines()
    result: list[CallCandidate] = []
    seen: set[tuple[str, int]] = set()
    for edge, target_symbol in rows:
        if edge.source_start_line is None or edge.source_end_line is None:
            continue
        target = target_symbol.display_name if target_symbol else edge.target_path
        if not target:
            continue
        key = (target, edge.source_start_line)
        if key in seen:
            continue
        seen.add(key)
        line_index = edge.source_start_line - 1
        source = lines[line_index].strip() if line_index < len(lines) else target
        result.append(
            CallCandidate(
                target=target,
                start_line=edge.source_start_line,
                end_line=edge.source_end_line,
                source=source,
                relation=edge.relation,
                confidence=edge.confidence,
            )
        )
    return result


def _choices(
    *, correct: str, distractors: list[str], seed: str, limit: int = 4
) -> tuple[list[dict], str]:
    labels = [correct]
    labels.extend(item for item in distractors if item and item != correct)
    labels.extend(
        item
        for item in ("호출 없이 다음 줄로 이동", "현재 파일의 첫 줄로 이동", "결과를 만들지 않음")
        if item != correct
    )
    unique = list(dict.fromkeys(_choice_label(item) for item in labels))[: max(limit * 2, 6)]
    ordered = sorted(
        unique,
        key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).hexdigest(),
    )[:limit]
    normalized_correct = _choice_label(correct)
    if normalized_correct not in ordered:
        ordered[-1] = normalized_correct
        ordered = sorted(
            ordered,
            key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).hexdigest(),
        )
    choices = [
        {"id": f"choice_{index}", "label": label} for index, label in enumerate(ordered, start=1)
    ]
    answer_key = next(item["id"] for item in choices if item["label"] == normalized_correct)
    return choices, answer_key


def _concepts_for_step(step: LearningStep) -> list[str]:
    metadata = step.metadata_json or {}
    return list(
        dict.fromkeys(
            [
                *(metadata.get("concept_ids") or []),
                *(step.lesson.required_concept_ids or []),
                *([step.concept_id] if step.concept_id else []),
            ]
        )
    )


def _evidence(
    chunk: CodeChunk,
    file: FileRecord,
    start_line: int,
    end_line: int,
    preview: str,
    *,
    relation: str | None = None,
    relation_confidence: float | None = None,
) -> dict:
    evidence = {
        "evidence_id": evidence_id_for_chunk(chunk.id),
        "snapshot_id": chunk.snapshot_id,
        "file_id": file.id,
        "path": file.path,
        "language": file.language,
        "title": chunk.title,
        "chunk_type": chunk.chunk_type,
        "start_line": start_line,
        "end_line": end_line,
        "preview": _preview(preview),
    }
    if relation:
        evidence["relation"] = relation
    if relation_confidence is not None:
        evidence["relation_confidence"] = relation_confidence
    return evidence


def _choice_label(value: str, limit: int = 240) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 3].rstrip()}..."


def _preview(value: str, limit: int = 320) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 3].rstrip()}..."


def _chunk_matches_file(chunk: CodeChunk, file: FileRecord) -> bool:
    if chunk.start_line < 1 or chunk.end_line > file.line_count:
        return False
    source = "\n".join(file.content.splitlines()[chunk.start_line - 1 : chunk.end_line])
    digest = hashlib.sha256(chunk.content.encode()).hexdigest()
    return source == chunk.content and chunk.content_hash == f"sha256:{digest}"
