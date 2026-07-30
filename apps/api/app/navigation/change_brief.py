from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ChatSession,
    DeepTask,
    FileRecord,
    RepositorySnapshot,
    Symbol,
    SymbolEdge,
)
from app.navigation.artifacts import (
    ArtifactWrite,
    load_navigation_artifact,
    write_navigation_artifacts,
)
from app.navigation.code_focus import SEMANTIC_FOCUS_RELATIONS
from app.navigation.versions import CHANGE_BRIEF_VERSION
from app.schemas import (
    ChangeBriefCandidateLocation,
    ChangeBriefImpact,
    ChangeBriefResponse,
    CodeExplanationEvidence,
    CodeSelection,
)

DIRECT_EFFECT_RELATIONS = frozenset(
    {
        "REQUESTS",
        "HANDLED_BY",
        "WRITES",
        "NAVIGATES_TO",
        "USES_EXTERNAL",
        "RAISES",
    }
)
RELATION_TITLE = {
    "TRIGGERS": "사용자 동작 진입점",
    "REQUESTS": "서버 요청 계약",
    "HANDLED_BY": "서버 요청 처리",
    "READS": "데이터 읽기",
    "WRITES": "상태·데이터 변경",
    "NAVIGATES_TO": "화면 이동",
    "USES_EXTERNAL": "외부 서비스 호출",
    "CALLS": "호출 관계",
    "RAISES": "실패·예외 경로",
}


def generate_change_brief(db: Session, task: DeepTask) -> ChangeBriefResponse:
    session = db.get(ChatSession, task.chat_session_id)
    if session is None:
        raise RuntimeError("Navigation deep task has no chat session")
    snapshot = db.get(RepositorySnapshot, session.snapshot_id)
    if snapshot is None or snapshot.status != "ready":
        raise RuntimeError("Navigation snapshot is not ready")
    selection = CodeSelection.model_validate(task.selection)
    context = task.context_json.get("navigation_context", {})
    artifact_key = _artifact_key(task.prompt, selection, context)
    cached = load_navigation_artifact(
        db,
        snapshot_id=snapshot.id,
        artifact_type="change_brief",
        artifact_key=artifact_key,
        artifact_version=CHANGE_BRIEF_VERSION,
        payload_model=ChangeBriefResponse,
        commit_sha=snapshot.commit_sha or "",
    )
    if cached is not None and cached.selection == selection:
        return cached

    files = db.scalars(
        select(FileRecord).where(FileRecord.snapshot_id == snapshot.id)
    ).all()
    selected_file = next((file for file in files if file.id == selection.file_id), None)
    if selected_file is None or selection.end_line > max(1, selected_file.line_count):
        raise RuntimeError("Change Brief selection is not in the snapshot")
    symbols = db.scalars(
        select(Symbol).where(Symbol.snapshot_id == snapshot.id)
    ).all()
    edges = db.scalars(
        select(SymbolEdge).where(
            SymbolEdge.snapshot_id == snapshot.id,
            SymbolEdge.relation.in_(SEMANTIC_FOCUS_RELATIONS),
        )
    ).all()
    brief = build_change_brief(
        snapshot=snapshot,
        prompt=task.prompt,
        selection=selection,
        selected_file=selected_file,
        files=files,
        symbols=symbols,
        edges=edges,
    )
    write_navigation_artifacts(
        db,
        snapshot_id=snapshot.id,
        commit_sha=snapshot.commit_sha or "",
        artifacts=[
            ArtifactWrite(
                artifact_type="change_brief",
                artifact_key=artifact_key,
                artifact_version=CHANGE_BRIEF_VERSION,
                payload=brief,
                generation_metadata={
                    "semantic_graph_version": snapshot.parser_version,
                    "feature_key": context.get("feature_key"),
                    "flow_step_id": context.get("flow_step_id"),
                    "explanation_depth": context.get("explanation_depth"),
                },
            )
        ],
    )
    return brief


def build_change_brief(
    *,
    snapshot: RepositorySnapshot,
    prompt: str,
    selection: CodeSelection,
    selected_file: FileRecord,
    files: Sequence[FileRecord],
    symbols: Sequence[Symbol],
    edges: Sequence[SymbolEdge],
) -> ChangeBriefResponse:
    files_by_id = {file.id: file for file in files}
    files_by_path = {file.path: file for file in files}
    symbols_by_id = {symbol.id: symbol for symbol in symbols}
    selected_symbol = _enclosing_symbol(symbols, selection)
    outgoing = [
        edge
        for edge in edges
        if edge.source_file_id == selected_file.id
        and (
            _overlaps(edge, selection)
            or (selected_symbol is not None and edge.source_symbol_id == selected_symbol.id)
        )
    ]
    incoming = (
        [edge for edge in edges if edge.target_symbol_id == selected_symbol.id]
        if selected_symbol
        else []
    )
    relevant_edges = sorted(
        {edge.id: edge for edge in [*outgoing, *incoming]}.values(),
        key=lambda edge: (
            0 if edge in outgoing else 1,
            edge.source_start_line or 0,
            edge.relation,
            edge.id,
        ),
    )
    selection_evidence = _evidence(
        selected_file,
        selection.start_line,
        selection.end_line,
        "변경 대상으로 선택한 코드 범위입니다.",
    )
    candidates = [
        ChangeBriefCandidateLocation(
            title=(
                selected_symbol.display_name
                if selected_symbol
                else PurePosixPath(selected_file.path).name
            ),
            reason="사용자가 변경 대상으로 선택한 출발점입니다.",
            confidence="verified",
            evidence=selection_evidence,
        )
    ]
    confirmed: list[ChangeBriefImpact] = []
    possible: list[ChangeBriefImpact] = []

    for edge in relevant_edges:
        edge_evidence = _edge_evidence(
            edge,
            selected_file=selected_file,
            files_by_id=files_by_id,
            symbols_by_id=symbols_by_id,
            incoming=edge in incoming,
        )
        target_label = _target_label(edge, symbols_by_id)
        impact = ChangeBriefImpact(
            title=RELATION_TITLE.get(edge.relation, "연결된 코드 경계"),
            description=_impact_description(edge, target_label, edge in incoming),
            relation_type=edge.relation,
            confidence="verified" if edge.confidence >= 0.8 else "inferred",
            evidence=[edge_evidence],
        )
        resolved = _candidate_for_edge(
            edge,
            files_by_id=files_by_id,
            files_by_path=files_by_path,
            symbols_by_id=symbols_by_id,
            incoming=edge in incoming,
        )
        if resolved and not any(
            item.evidence.file_id == resolved.evidence.file_id
            and item.evidence.start_line == resolved.evidence.start_line
            for item in candidates
        ):
            candidates.append(resolved)
        if edge.confidence >= 0.8 and (
            edge.relation in DIRECT_EFFECT_RELATIONS or edge in incoming
        ):
            confirmed.append(impact)
        else:
            possible.append(impact)

    if not confirmed:
        possible.insert(
            0,
            ChangeBriefImpact(
                title="직접 연결 경계 확인",
                description=(
                    "선택 범위에서 확정할 수 있는 직접 영향 관계가 부족합니다. "
                    "호출자와 소비자를 검색해 변경 계약을 추가로 확인해야 합니다."
                ),
                relation_type="REQUIRES_VERIFICATION",
                confidence="unknown",
                evidence=[selection_evidence],
            ),
        )

    risk_level, risk_rationale = _risk(relevant_edges, candidates)
    verification_steps = _verification_steps(relevant_edges, selected_file.path)
    unknown_boundaries = _unknown_boundaries(relevant_edges)
    all_evidence = _dedupe_evidence(
        [
            selection_evidence,
            *(candidate.evidence for candidate in candidates),
            *(evidence for impact in [*confirmed, *possible] for evidence in impact.evidence),
        ]
    )
    semantic_key = "|".join(
        (
            snapshot.id,
            snapshot.commit_sha or "",
            selected_file.id,
            str(selection.start_line),
            str(selection.end_line),
            prompt.strip(),
        )
    )
    return ChangeBriefResponse(
        id=_stable_id("change", semantic_key),
        snapshot_id=snapshot.id,
        analysis_version=CHANGE_BRIEF_VERSION,
        request_summary=prompt.strip()[:500],
        selection=selection,
        candidate_locations=candidates[:8],
        confirmed_direct_impacts=confirmed[:8],
        possible_impacts_to_verify=possible[:8],
        unknown_boundaries=unknown_boundaries,
        risk_level=risk_level,
        risk_rationale=risk_rationale,
        verification_steps=verification_steps,
        rollback_guidance=[
            "변경 전 현재 동작을 재현하는 테스트 또는 검증 절차를 먼저 남깁니다.",
            "변경은 독립된 커밋으로 분리하고 확인된 직접 영향 위치를 함께 수정합니다.",
            "검증 실패 시 해당 커밋을 되돌리고 미확인 경계를 다시 조사합니다.",
        ],
        evidence=all_evidence[:12],
        limitations=[
            "정적 코드와 semantic-ts-v2 관계만 분석했으며 실제 패치는 적용하지 않았습니다.",
            "동적 호출, 런타임 설정, 배포 인프라와 저장소 밖 소비자는 별도 확인이 필요합니다.",
        ],
    )


def _enclosing_symbol(symbols: Sequence[Symbol], selection: CodeSelection) -> Symbol | None:
    candidates = [
        symbol
        for symbol in symbols
        if symbol.file_id == selection.file_id
        and symbol.start_line <= selection.start_line
        and symbol.end_line >= selection.end_line
    ]
    return min(
        candidates,
        key=lambda item: (item.end_line - item.start_line, item.start_line, item.id),
        default=None,
    )


def _overlaps(edge: SymbolEdge, selection: CodeSelection) -> bool:
    return (
        isinstance(edge.source_start_line, int)
        and isinstance(edge.source_end_line, int)
        and edge.source_start_line <= selection.end_line
        and edge.source_end_line >= selection.start_line
    )


def _edge_evidence(
    edge: SymbolEdge,
    *,
    selected_file: FileRecord,
    files_by_id: dict[str, FileRecord],
    symbols_by_id: dict[str, Symbol],
    incoming: bool,
) -> CodeExplanationEvidence:
    if incoming:
        source_file = files_by_id.get(edge.source_file_id, selected_file)
        source_symbol = symbols_by_id.get(edge.source_symbol_id or "")
        return _evidence(
            source_file,
            source_symbol.start_line if source_symbol else edge.source_start_line or 1,
            source_symbol.end_line if source_symbol else edge.source_end_line or 1,
            "선택한 심볼을 참조하는 코드 근거입니다.",
        )
    return _evidence(
        selected_file,
        edge.source_start_line or 1,
        edge.source_end_line or edge.source_start_line or 1,
        f"{edge.relation} 관계가 발견된 코드 근거입니다.",
    )


def _candidate_for_edge(
    edge: SymbolEdge,
    *,
    files_by_id: dict[str, FileRecord],
    files_by_path: dict[str, FileRecord],
    symbols_by_id: dict[str, Symbol],
    incoming: bool,
) -> ChangeBriefCandidateLocation | None:
    symbol_id = edge.source_symbol_id if incoming else edge.target_symbol_id
    symbol = symbols_by_id.get(symbol_id or "")
    file = files_by_id.get(symbol.file_id) if symbol else None
    if incoming and file is None:
        file = files_by_id.get(edge.source_file_id)
    if file is None and edge.target_path:
        file = files_by_path.get(edge.target_path)
    if file is None:
        return None
    start_line = symbol.start_line if symbol else 1
    end_line = symbol.end_line if symbol else min(max(1, file.line_count), start_line)
    return ChangeBriefCandidateLocation(
        title=symbol.display_name if symbol else PurePosixPath(file.path).name,
        reason="호출자·소비자 관계로 연결된 변경 후보 위치입니다.",
        confidence="verified" if edge.confidence >= 0.8 else "inferred",
        evidence=_evidence(
            file,
            start_line,
            end_line,
            f"{edge.relation} 관계의 반대편 코드입니다.",
        ),
    )


def _target_label(edge: SymbolEdge, symbols_by_id: dict[str, Symbol]) -> str:
    symbol = symbols_by_id.get(edge.target_symbol_id or "")
    return symbol.display_name if symbol else edge.target_path or "연결된 대상"


def _impact_description(edge: SymbolEdge, target: str, incoming: bool) -> str:
    if incoming:
        return (
            "이 코드는 선택 범위를 사용하는 호출자이므로 변경된 입력·출력 "
            f"계약의 영향을 받을 수 있습니다: {target}"
        )
    copy = {
        "TRIGGERS": "사용자 진입 동작과 다음 처리 순서가 연결되어 있습니다.",
        "REQUESTS": "요청 경로·메서드·payload 계약이 연결되어 있습니다.",
        "HANDLED_BY": "서버 handler의 입력과 응답 계약이 연결되어 있습니다.",
        "READS": "읽는 데이터의 형태와 부재 처리에 영향을 줄 수 있습니다.",
        "WRITES": "저장 또는 상태 변경 결과와 소비자에 영향을 줄 수 있습니다.",
        "NAVIGATES_TO": "이동 대상과 이동 조건에 영향을 줄 수 있습니다.",
        "USES_EXTERNAL": "외부 서비스 계약·오류 처리·재시도 경계를 확인해야 합니다.",
        "CALLS": "호출 대상의 입력·출력 계약과 호출 순서를 함께 확인해야 합니다.",
        "RAISES": "실패 조건, 예외 유형, 호출자의 복구 동작에 영향을 줄 수 있습니다.",
    }.get(edge.relation, "연결된 코드 계약을 함께 확인해야 합니다.")
    return f"{target}: {copy}"


def _risk(
    edges: Sequence[SymbolEdge],
    candidates: Sequence[ChangeBriefCandidateLocation],
) -> tuple[str, str]:
    relations = {edge.relation for edge in edges if edge.confidence >= 0.8}
    file_count = len({item.evidence.file_id for item in candidates})
    if relations & {"WRITES", "USES_EXTERNAL"}:
        return "high", "저장 상태 또는 외부 서비스 경계를 건드리는 검증된 관계가 있습니다."
    if file_count > 1 or relations & {
        "REQUESTS",
        "HANDLED_BY",
        "NAVIGATES_TO",
        "RAISES",
    }:
        return "medium", "둘 이상의 코드 경계 또는 요청·이동 계약을 함께 확인해야 합니다."
    if edges:
        return "low", "현재 정적 근거에서는 영향이 선택 범위 주변에 집중되어 있습니다."
    return "unknown", "직접 관계 근거가 부족해 영향 범위를 낮다고 단정할 수 없습니다."


def _unknown_boundaries(edges: Sequence[SymbolEdge]) -> list[str]:
    items = ["동적 호출과 런타임 조건에 의해 추가되는 실행 경로"]
    relations = {edge.relation for edge in edges}
    if "USES_EXTERNAL" in relations:
        items.append("저장소 밖 외부 서비스의 실제 응답·장애·호환성")
    if "WRITES" in relations or "READS" in relations:
        items.append("기존 데이터와 마이그레이션이 필요한 저장소 계약")
    if "REQUESTS" in relations or "HANDLED_BY" in relations:
        items.append("정적 분석으로 찾지 못한 API 소비자와 배포 중인 이전 클라이언트")
    if "RAISES" in relations:
        items.append("호출자가 예외를 변환·재시도·복구하는 런타임 실패 경계")
    items.append("환경 변수, 배포 설정, feature flag에 따른 동작 차이")
    return items


def _verification_steps(edges: Sequence[SymbolEdge], path: str) -> list[str]:
    relations = {edge.relation for edge in edges}
    steps = [f"{path}의 선택 범위를 실행하는 기존 테스트 또는 재현 절차를 확인합니다."]
    if relations & {"REQUESTS", "HANDLED_BY"}:
        steps.append("요청 method·path·payload와 handler 응답 계약 테스트를 실행합니다.")
    if relations & {"READS", "WRITES"}:
        steps.append("정상 데이터, 빈 데이터, 실패 시나리오의 읽기·쓰기 결과를 검증합니다.")
    if "NAVIGATES_TO" in relations:
        steps.append("이동 조건과 목적 화면을 포함한 사용자 흐름을 확인합니다.")
    if "USES_EXTERNAL" in relations:
        steps.append("외부 서비스 성공·오류·timeout 응답에 대한 통합 경계를 확인합니다.")
    if "RAISES" in relations:
        steps.append("각 예외 조건과 호출자의 catch·복구·재시도 동작을 검증합니다.")
    steps.append("후보 위치별 관련 테스트를 실행하고 미확인 경계를 수동 점검합니다.")
    return steps


def _evidence(file: FileRecord, start: int, end: int, reason: str) -> CodeExplanationEvidence:
    safe_start = max(1, start)
    safe_end = max(safe_start, min(max(1, file.line_count), end))
    return CodeExplanationEvidence(
        file_id=file.id,
        path=file.path,
        start_line=safe_start,
        end_line=safe_end,
        reason=reason,
    )


def _dedupe_evidence(items: Sequence[CodeExplanationEvidence]) -> list[CodeExplanationEvidence]:
    return list(
        {
            (item.file_id, item.start_line, item.end_line): item
            for item in items
        }.values()
    )


def _artifact_key(prompt: str, selection: CodeSelection, context: dict) -> str:
    raw = "|".join(
        (
            selection.file_id,
            str(selection.start_line),
            str(selection.end_line),
            str(context.get("feature_key") or ""),
            str(context.get("flow_step_id") or ""),
            prompt.strip(),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"
