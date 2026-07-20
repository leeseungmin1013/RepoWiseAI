from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.models import FileRecord, RepositorySnapshot, Symbol, SymbolEdge
from app.navigation.versions import FEATURE_FLOW_VERSION, SEMANTIC_GRAPH_VERSION
from app.schemas import (
    FeatureFlowDetail,
    FeatureFlowEvidence,
    FeatureFlowListResponse,
    FeatureFlowStep,
    FeatureFlowSummary,
)

Confidence = Literal["verified", "inferred", "unknown"]
EFFECT_RELATIONS = frozenset(
    {"READS", "WRITES", "NAVIGATES_TO", "USES_EXTERNAL"}
)
SEMANTIC_RELATIONS = frozenset(
    {"TRIGGERS", "REQUESTS", "HANDLED_BY", *EFFECT_RELATIONS}
)
MAX_REPRESENTATIVE_FLOWS = 3
MAX_FLOW_STEPS = 7
NON_REPRESENTATIVE_DIRECTORIES = frozenset(
    {
        "__mocks__",
        "__tests__",
        "fixture",
        "fixtures",
        "mock",
        "mocks",
        "spec",
        "specs",
        "stories",
        "story",
        "test",
        "tests",
    }
)


@dataclass(frozen=True)
class _FlowCandidate:
    summary: FeatureFlowSummary
    detail: FeatureFlowDetail
    rank: tuple[int, float, str]


def build_feature_flows(
    snapshot: RepositorySnapshot,
    files: Sequence[FileRecord],
    symbols: Sequence[Symbol],
    semantic_edges: Sequence[SymbolEdge],
) -> FeatureFlowListResponse:
    """Build a bounded, deterministic feature catalog from verified semantic edges."""

    candidates, skipped_seed_count, excluded_test_seed_count = _build_candidates(
        snapshot, files, symbols, semantic_edges
    )
    selected = candidates[:MAX_REPRESENTATIVE_FLOWS]
    limitations = [
        "대표 기능 흐름은 정적 분석 근거가 강한 순서로 최대 3개만 제공합니다.",
        "동적으로 결정되는 이벤트 대상과 요청 경로는 연결하지 않습니다.",
    ]
    if not candidates:
        limitations.append(
            "유효한 TRIGGERS 관계를 찾지 못해 대표 기능 흐름을 구성하지 못했습니다."
        )
    if skipped_seed_count:
        limitations.append(
            f"코드 위치를 검증할 수 없는 trigger {skipped_seed_count}개는 노출하지 않았습니다."
        )
    if excluded_test_seed_count:
        limitations.append(
            "테스트·스토리·fixture 파일의 trigger "
            f"{excluded_test_seed_count}개는 대표 기능 후보에서 제외했습니다."
        )
    if snapshot.parser_version != SEMANTIC_GRAPH_VERSION:
        current_version = snapshot.parser_version or "미기록 버전"
        limitations.append(
            f"이 snapshot은 {current_version} 분석 결과입니다. "
            f"{SEMANTIC_GRAPH_VERSION} 의미 관계를 얻으려면 저장소를 다시 분석해야 합니다."
        )
    if len(candidates) > MAX_REPRESENTATIVE_FLOWS:
        limitations.append(
            f"나머지 {len(candidates) - MAX_REPRESENTATIVE_FLOWS}개 흐름은 "
            "대표 목록에서 생략했습니다."
        )

    repository = snapshot.repository
    return FeatureFlowListResponse(
        repository_name=f"{repository.owner}/{repository.name}",
        snapshot_id=snapshot.id,
        commit_sha=snapshot.commit_sha or "",
        analysis_version=FEATURE_FLOW_VERSION,
        flows=[candidate.summary for candidate in selected],
        limitations=limitations,
    )


def build_feature_flow(
    snapshot: RepositorySnapshot,
    files: Sequence[FileRecord],
    symbols: Sequence[Symbol],
    semantic_edges: Sequence[SymbolEdge],
    flow_id: str,
) -> FeatureFlowDetail | None:
    """Return one representative flow using the same selection rules as the catalog."""

    candidates, _, _ = _build_candidates(snapshot, files, symbols, semantic_edges)
    return next(
        (
            candidate.detail
            for candidate in candidates[:MAX_REPRESENTATIVE_FLOWS]
            if candidate.detail.id == flow_id
        ),
        None,
    )


def _build_candidates(
    snapshot: RepositorySnapshot,
    files: Sequence[FileRecord],
    symbols: Sequence[Symbol],
    semantic_edges: Sequence[SymbolEdge],
) -> tuple[list[_FlowCandidate], int, int]:
    ordered_files = sorted(files, key=lambda item: (item.path.casefold(), item.id))
    ordered_symbols = sorted(
        symbols,
        key=lambda item: (item.file_id, item.start_line, item.qualified_name, item.id),
    )
    ordered_edges = sorted(
        (edge for edge in semantic_edges if edge.relation in SEMANTIC_RELATIONS),
        key=_edge_sort_key,
    )
    file_by_id = {file.id: file for file in ordered_files}
    symbol_by_id = {symbol.id: symbol for symbol in ordered_symbols}
    request_edges_by_source = _index_request_edges(
        [edge for edge in ordered_edges if edge.relation == "REQUESTS"]
    )
    handled_edges_by_request = _index_handled_edges(
        [edge for edge in ordered_edges if edge.relation == "HANDLED_BY"]
    )
    effect_edges_by_source = _index_effect_edges(
        [edge for edge in ordered_edges if edge.relation in EFFECT_RELATIONS]
    )
    trigger_edges = [edge for edge in ordered_edges if edge.relation == "TRIGGERS"]
    representative_triggers = [
        edge
        for edge in trigger_edges
        if not _is_non_representative_file(file_by_id.get(edge.source_file_id))
    ]
    excluded_test_seed_count = len(trigger_edges) - len(representative_triggers)
    seeds = _deduplicate_trigger_seeds(
        representative_triggers,
        file_by_id,
        symbol_by_id,
    )
    candidates: list[_FlowCandidate] = []
    skipped_seed_count = 0
    for trigger_edge in seeds:
        entry_evidence = _source_evidence(
            trigger_edge,
            file_by_id,
            symbol_by_id,
            "사용자 이벤트가 핸들러를 가리키는 코드 위치입니다.",
        )
        if entry_evidence is None:
            skipped_seed_count += 1
            continue
        candidates.append(
            _build_candidate(
                snapshot=snapshot,
                trigger_edge=trigger_edge,
                entry_evidence=entry_evidence,
                file_by_id=file_by_id,
                symbol_by_id=symbol_by_id,
                request_edges_by_source=request_edges_by_source,
                handled_edges_by_request=handled_edges_by_request,
                effect_edges_by_source=effect_edges_by_source,
            )
        )

    candidates.sort(key=lambda item: (-item.rank[0], -item.rank[1], item.rank[2]))
    return candidates, skipped_seed_count, excluded_test_seed_count


def _deduplicate_trigger_seeds(
    edges: Sequence[SymbolEdge],
    file_by_id: dict[str, FileRecord],
    symbol_by_id: dict[str, Symbol],
) -> list[SymbolEdge]:
    best_by_target: dict[str, SymbolEdge] = {}
    for edge in edges:
        metadata = _metadata(edge)
        target_symbol = symbol_by_id.get(edge.target_symbol_id or "")
        target_file = file_by_id.get(target_symbol.file_id) if target_symbol else None
        source_file = file_by_id.get(edge.source_file_id)
        key = (
            "|".join(
                (
                    target_file.path if target_file else "missing-target-file",
                    target_symbol.qualified_name,
                )
            )
            if target_symbol
            else "|".join(
                (
                    source_file.path if source_file else "missing-source-file",
                    str(edge.source_start_line or 0),
                    str(metadata.get("event_name") or ""),
                    str(
                        metadata.get("handler_identifier")
                        or edge.target_path
                        or "unresolved"
                    ),
                )
            )
        )
        current = best_by_target.get(key)
        if current is None or _trigger_seed_preference(
            edge, file_by_id, symbol_by_id
        ) < _trigger_seed_preference(current, file_by_id, symbol_by_id):
            best_by_target[key] = edge
    return sorted(best_by_target.values(), key=_edge_sort_key)


def _trigger_seed_preference(
    edge: SymbolEdge,
    file_by_id: dict[str, FileRecord],
    symbol_by_id: dict[str, Symbol],
) -> tuple[Any, ...]:
    metadata = _metadata(edge)
    source_file = file_by_id.get(edge.source_file_id)
    source_symbol = symbol_by_id.get(edge.source_symbol_id or "")
    target_symbol = symbol_by_id.get(edge.target_symbol_id or "")
    return (
        -float(edge.confidence),
        source_file.path if source_file else "missing-source-file",
        edge.source_start_line or 0,
        edge.source_end_line or 0,
        source_symbol.qualified_name if source_symbol else "file-scope",
        target_symbol.qualified_name if target_symbol else "unresolved",
        str(metadata.get("event_name") or ""),
        str(metadata.get("handler_identifier") or edge.target_path or ""),
    )


def _build_candidate(
    *,
    snapshot: RepositorySnapshot,
    trigger_edge: SymbolEdge,
    entry_evidence: FeatureFlowEvidence,
    file_by_id: dict[str, FileRecord],
    symbol_by_id: dict[str, Symbol],
    request_edges_by_source: dict[str, list[SymbolEdge]],
    handled_edges_by_request: dict[tuple[str, str, str], list[SymbolEdge]],
    effect_edges_by_source: dict[str, list[SymbolEdge]],
) -> _FlowCandidate:
    metadata = _metadata(trigger_edge)
    event_name = str(metadata.get("event_name") or "이벤트")
    event_label = _event_label(event_name)
    source_symbol = symbol_by_id.get(trigger_edge.source_symbol_id or "")
    handler = symbol_by_id.get(trigger_edge.target_symbol_id or "")
    handler_file = file_by_id.get(handler.file_id) if handler else None
    source_name = source_symbol.display_name if source_symbol else _file_stem(entry_evidence.path)
    handler_name = handler.display_name if handler else str(
        metadata.get("handler_identifier") or trigger_edge.target_path or "대상 핸들러"
    )

    matching_requests = _deduplicate_request_edges(
        request_edges_by_source.get(handler.id, []) if handler else []
    )
    request_edge, handled_edge = _select_request_and_handler(
        matching_requests,
        handled_edges_by_request,
    )
    handler_effects = effect_edges_by_source.get(handler.id, []) if handler else []
    request_metadata = _metadata(request_edge) if request_edge else {}
    method = str(request_metadata.get("http_method") or "").upper()
    request_path = _safe_request_path(
        request_metadata.get("request_path")
        or (request_edge.target_path if request_edge else "")
        or ""
    )
    method_label = "메서드 미확인" if method == "UNKNOWN" else method
    request_label = (
        " ".join(part for part in (method_label, request_path) if part) or "리터럴 요청"
    )
    route_handler = (
        symbol_by_id.get(handled_edge.target_symbol_id or "") if handled_edge else None
    )
    route_effects = (
        effect_edges_by_source.get(route_handler.id, []) if route_handler else []
    )
    route_evidence = (
        _symbol_evidence(
            route_handler,
            file_by_id,
            f"{request_label}을 처리하는 서버 라우트 핸들러입니다.",
        )
        if route_handler
        else None
    )

    semantic_key = "|".join(
        (
            snapshot.commit_sha
            or (
                f"{snapshot.repository.owner}/{snapshot.repository.name}:"
                f"{snapshot.branch or 'default'}"
            ),
            entry_evidence.path,
            str(entry_evidence.start_line),
            str(entry_evidence.end_line),
            event_name,
            handler_file.path if handler_file else "missing-handler-file",
            handler.qualified_name if handler else handler_name,
            str(handler.start_line) if handler else "0",
            str(handler.end_line) if handler else "0",
            method if request_edge else "",
            request_path,
        )
    )
    flow_id = _stable_id("flow", semantic_key)
    steps: list[FeatureFlowStep] = []
    limitations: list[str] = []
    handler_step_added = False
    request_step_added = False
    route_step_added = False

    trigger_confidence = _confidence_for_edge(trigger_edge)
    steps.append(
        _step(
            flow_id=flow_id,
            ordinal=1,
            identity=_step_identity(
                relation="TRIGGERS",
                symbol=source_symbol,
                evidence=entry_evidence,
                request_path=event_name,
            ),
            title=f"{source_name}에서 {event_label} 감지",
            role="user_trigger",
            executes_when=f"사용자가 {event_label} 동작을 실행할 때",
            input=f"{event_name} 이벤트",
            output=(
                f"{handler_name} 핸들러 호출"
                if handler
                else "대상 핸들러 연결을 정적으로 확인하지 못함"
            ),
            relation_type="TRIGGERS",
            confidence=trigger_confidence,
            evidence=entry_evidence,
        )
    )

    if handler:
        handler_evidence = _symbol_evidence(
            handler,
            file_by_id,
            "이벤트가 호출하는 핸들러 심볼의 선언입니다.",
        )
        if handler_evidence:
            steps.append(
                _step(
                    flow_id=flow_id,
                    ordinal=len(steps) + 1,
                    identity=_step_identity(
                        relation="TRIGGERS",
                        symbol=handler,
                        evidence=handler_evidence,
                    ),
                    title=f"{handler_name} 핸들러 실행",
                    role="client_handler",
                    executes_when="이벤트 연결이 핸들러를 호출할 때",
                    input=f"{event_name} 이벤트",
                    output=(
                        f"{request_label} 준비"
                        if request_edge
                        else "핸들러 내부 로직 실행"
                    ),
                    relation_type="TRIGGERS",
                    confidence=trigger_confidence,
                    evidence=handler_evidence,
                )
            )
            handler_step_added = True
        else:
            limitations.append(
                "대상 핸들러 심볼의 코드 범위를 검증할 수 없어 핸들러 단계를 노출하지 않았습니다."
            )
    else:
        limitations.append(
            "TRIGGERS 근거는 있지만 대상 핸들러 심볼이 해석되지 않아 여기서 분석이 멈췄습니다."
        )

    pre_request_effects = [
        edge
        for edge in handler_effects
        if edge.relation == "READS"
        and (
            request_edge is None
            or (edge.source_start_line or 0) < (request_edge.source_start_line or 0)
        )
    ]
    added_effect_edges: list[SymbolEdge] = []
    omitted_effect_count = 0
    if request_edge:
        added, omitted = _append_effect_steps(
            flow_id=flow_id,
            steps=steps,
            effect_edges=pre_request_effects,
            owner_symbol=handler,
            file_by_id=file_by_id,
            symbol_by_id=symbol_by_id,
        )
        added_effect_edges.extend(added)
        omitted_effect_count += omitted

    if request_edge:
        request_evidence = _source_evidence(
            request_edge,
            file_by_id,
            symbol_by_id,
            f"{request_label}을 보내는 코드 위치입니다.",
        )
        if request_evidence:
            steps.append(
                _step(
                    flow_id=flow_id,
                    ordinal=len(steps) + 1,
                    identity=_step_identity(
                        relation="REQUESTS",
                        symbol=handler,
                        evidence=request_evidence,
                        method=method,
                        request_path=request_path,
                    ),
                    title=f"{request_label} 전송",
                    role="request",
                    executes_when=f"{handler_name} 핸들러가 요청 코드를 실행할 때",
                    input=request_label,
                    output=(
                        "일치하는 서버 라우트 핸들러로 전달"
                        if route_evidence
                        else "요청 전송 이후의 처리 연결은 확인되지 않음"
                    ),
                    relation_type="REQUESTS",
                    confidence=_confidence_for_edge(request_edge),
                    evidence=request_evidence,
                )
            )
            request_step_added = True
        else:
            limitations.append(
                "REQUESTS 관계의 코드 범위를 검증할 수 없어 요청 단계를 노출하지 않았습니다."
            )

        if route_handler and handled_edge and request_step_added:
            if route_evidence:
                steps.append(
                    _step(
                        flow_id=flow_id,
                        ordinal=len(steps) + 1,
                        identity=_step_identity(
                            relation="HANDLED_BY",
                            symbol=route_handler,
                            evidence=route_evidence,
                            method=method,
                            request_path=request_path,
                        ),
                        title=f"{request_label} 라우트 처리",
                        role="server_handler",
                        executes_when=f"{request_label}이 들어올 때",
                        input=request_label,
                        output=f"{route_handler.display_name} 서버 핸들러 로직 실행",
                        relation_type="HANDLED_BY",
                        confidence=_confidence_for_edge(handled_edge),
                        evidence=route_evidence,
                    )
                )
                route_step_added = True
            else:
                limitations.append(
                    "연결된 서버 라우트 심볼의 코드 범위를 검증할 수 없어 여기서 분석이 멈췄습니다."
                )
        elif route_handler and handled_edge:
            limitations.append(
                "요청 단계를 코드 근거로 검증하지 못해 서버 라우트 연결을 노출하지 않았습니다."
            )
        else:
            if method == "UNKNOWN":
                limitations.append(
                    "요청 HTTP 메서드가 동적으로 결정되어 서버 라우트와 연결하지 않았습니다."
                )
            else:
                limitations.append(
                    f"{request_label} 이후 일치하는 서버 라우트 핸들러를 "
                    "확인하지 못해 여기서 분석이 멈췄습니다."
                )
    elif handler:
        limitations.append(
            "핸들러 이후의 리터럴 REQUESTS 관계가 확인되지 않아 여기서 분석이 멈췄습니다."
        )

    if route_step_added:
        added, omitted = _append_effect_steps(
            flow_id=flow_id,
            steps=steps,
            effect_edges=route_effects,
            owner_symbol=route_handler,
            file_by_id=file_by_id,
            symbol_by_id=symbol_by_id,
        )
        added_effect_edges.extend(added)
        omitted_effect_count += omitted

    if handler:
        already_considered = {edge.id for edge in pre_request_effects}
        remaining_handler_effects = [
            edge for edge in handler_effects if edge.id not in already_considered
        ]
        if request_edge:
            if request_step_added and bool(request_metadata.get("awaited")):
                remaining_handler_effects = [
                    edge
                    for edge in remaining_handler_effects
                    if (edge.source_start_line or 0) > (request_edge.source_end_line or 0)
                    and edge.relation in {"WRITES", "NAVIGATES_TO", "USES_EXTERNAL"}
                ]
            else:
                if remaining_handler_effects:
                    limitations.append(
                        "요청 완료를 기다린다는 근거가 없어 요청 이후의 화면 상태·이동은 "
                        "직선 흐름에 연결하지 않았습니다."
                    )
                remaining_handler_effects = []
        added, omitted = _append_effect_steps(
            flow_id=flow_id,
            steps=steps,
            effect_edges=remaining_handler_effects,
            owner_symbol=handler,
            file_by_id=file_by_id,
            symbol_by_id=symbol_by_id,
        )
        added_effect_edges.extend(added)
        omitted_effect_count += omitted

    if omitted_effect_count:
        limitations.append(
            f"대표 흐름을 {MAX_FLOW_STEPS}단계로 제한해 추가 효과 "
            f"{omitted_effect_count}개를 생략했습니다."
        )

    if len(matching_requests) > 1:
        limitations.append(
            f"같은 핸들러의 추가 요청 {len(matching_requests) - 1}개는 "
            "대표 직선 흐름에서 생략했습니다."
        )
    limitations.append(
        "실패 경로는 v2 정적 분석에서 확정하지 않으므로 failure_steps를 비워 두었습니다."
    )

    linked_steps = _link_steps(steps)
    involved_areas = _involved_areas(linked_steps)
    confidence = _flow_confidence(
        trigger_edge=trigger_edge,
        request_edge=request_edge if request_step_added else None,
        handled_edge=handled_edge if route_step_added else None,
        has_handler=handler_step_added,
        has_route=route_step_added,
    )
    title = (
        f"{source_name}: {request_path} 요청 흐름"
        if request_path
        else f"{source_name}: {handler_name} 실행 흐름"
    )
    user_goal = (
        f"사용자 {event_label} 동작이 {request_label} 서버 처리로 이어지는 "
        "경로를 확인합니다."
        if route_step_added
        else f"사용자 {event_label} 동작 뒤 정적으로 확인 가능한 실행 경로를 확인합니다."
    )
    trigger = f"사용자가 {source_name}에서 {event_label} 동작을 실행합니다."
    if route_step_added and route_handler:
        outcome = f"{route_handler.display_name} 서버 라우트 핸들러에 도달합니다."
    elif request_step_added:
        outcome = f"{request_label} 전송까지 확인되고 이후 연결은 알 수 없습니다."
    elif handler_step_added:
        outcome = f"{handler_name} 핸들러 진입까지 확인되고 이후 연결은 알 수 없습니다."
    else:
        outcome = "사용자 이벤트 이후의 핸들러 연결은 알 수 없습니다."
    if linked_steps and linked_steps[-1].relation_type in EFFECT_RELATIONS:
        outcome = linked_steps[-1].output_or_side_effect

    detail = FeatureFlowDetail(
        id=flow_id,
        title=title,
        user_goal=user_goal,
        trigger=trigger,
        outcome=outcome,
        normal_steps=linked_steps,
        failure_steps=[],
        involved_areas=involved_areas,
        confidence=confidence,
        limitations=limitations,
    )
    evidence_count = sum(bool(step.evidence) for step in linked_steps)
    summary = FeatureFlowSummary(
        id=flow_id,
        title=title,
        user_goal=user_goal,
        trigger=trigger,
        outcome=outcome,
        step_count=len(linked_steps),
        involved_areas=involved_areas,
        confidence=confidence,
        evidence_coverage=evidence_count / len(linked_steps),
        entry_evidence=entry_evidence,
    )
    rank = (
        4
        if added_effect_edges
        else 3
        if route_step_added
        else 2
        if request_step_added
        else 1
        if handler_step_added
        else 0,
        min(
            [float(trigger_edge.confidence)]
            + ([float(request_edge.confidence)] if request_edge and request_step_added else [])
            + ([float(handled_edge.confidence)] if handled_edge and route_step_added else [])
        ),
        semantic_key.casefold(),
    )
    return _FlowCandidate(summary=summary, detail=detail, rank=rank)


def _append_effect_steps(
    *,
    flow_id: str,
    steps: list[FeatureFlowStep],
    effect_edges: Sequence[SymbolEdge],
    owner_symbol: Symbol | None,
    file_by_id: dict[str, FileRecord],
    symbol_by_id: dict[str, Symbol],
) -> tuple[list[SymbolEdge], int]:
    added: list[SymbolEdge] = []
    omitted = 0
    for edge in sorted(effect_edges, key=_edge_sort_key):
        if len(steps) >= MAX_FLOW_STEPS:
            omitted += 1
            continue
        evidence = _source_evidence(
            edge,
            file_by_id,
            symbol_by_id,
            _effect_evidence_reason(edge),
        )
        if evidence is None:
            omitted += 1
            continue
        title, role, executes_when, input_text, output = _effect_copy(edge)
        steps.append(
            _step(
                flow_id=flow_id,
                ordinal=len(steps) + 1,
                identity=_step_identity(
                    relation=edge.relation,
                    symbol=owner_symbol,
                    evidence=evidence,
                    semantic_target=edge.target_path or "",
                ),
                title=title,
                role=role,
                executes_when=executes_when,
                input=input_text,
                output=output,
                relation_type=edge.relation,
                confidence=_confidence_for_edge(edge),
                evidence=evidence,
            )
        )
        added.append(edge)
    return added, omitted


def _effect_copy(edge: SymbolEdge) -> tuple[str, str, str, str, str]:
    metadata = _metadata(edge)
    target = str(edge.target_path or "대상")
    if edge.relation == "READS":
        storage = str(metadata.get("storage_kind") or "저장소")
        key = str(metadata.get("storage_key") or target)
        return (
            f"{storage}에서 {key} 읽기",
            "storage_read",
            "핸들러가 저장된 값을 필요로 할 때",
            f"{key} 키",
            f"저장된 {key} 값을 다음 로직에서 사용합니다.",
        )
    if edge.relation == "WRITES" and metadata.get("write_kind") == "react_state":
        state_name = str(metadata.get("state_name") or target.removeprefix("state:"))
        return (
            f"{state_name} 화면 상태 갱신",
            "state_write",
            "핸들러가 상태 setter를 호출할 때",
            f"{state_name}의 새 값",
            f"{state_name} 화면 상태가 갱신됩니다.",
        )
    if edge.relation == "WRITES":
        storage = str(metadata.get("storage_kind") or "저장소")
        key = str(metadata.get("storage_key") or target)
        operation = str(metadata.get("storage_operation") or "setItem")
        action = "삭제" if operation == "removeItem" else "저장"
        return (
            f"{storage}의 {key} {action}",
            "storage_write",
            "핸들러가 브라우저 저장소를 변경할 때",
            f"{key} 키",
            f"{storage}의 {key} 값이 {action}됩니다.",
        )
    if edge.relation == "NAVIGATES_TO":
        destination = _safe_request_path(metadata.get("destination") or target)
        destination = destination or "확인된 목적지"
        return (
            f"{destination} 화면으로 이동",
            "navigation",
            "Next.js 이동 함수가 실행될 때",
            destination,
            f"사용자 화면이 {destination}(으)로 이동합니다.",
        )
    if edge.relation == "USES_EXTERNAL":
        service = str(metadata.get("service") or target.removeprefix("external:"))
        operation = str(metadata.get("operation") or "SDK 호출")
        return (
            f"{service} 외부 서비스 사용",
            "external_service",
            "서버 또는 핸들러가 SDK 메서드를 호출할 때",
            operation,
            f"{service}의 {operation} 결과를 받습니다.",
        )
    return (
        f"{target} 처리",
        "effect",
        "관련 코드가 실행될 때",
        target,
        f"{target}에 대한 부수 효과가 발생합니다.",
    )


def _effect_evidence_reason(edge: SymbolEdge) -> str:
    return {
        "READS": "저장된 값을 읽는 코드 위치입니다.",
        "WRITES": "상태 또는 저장소를 변경하는 코드 위치입니다.",
        "NAVIGATES_TO": "다른 화면으로 이동하는 코드 위치입니다.",
        "USES_EXTERNAL": "인식된 외부 SDK를 호출하는 코드 위치입니다.",
    }.get(edge.relation, "후속 효과가 발생하는 코드 위치입니다.")


def _select_request_and_handler(
    request_edges: Sequence[SymbolEdge],
    handled_edges_by_request: dict[tuple[str, str, str], list[SymbolEdge]],
) -> tuple[SymbolEdge | None, SymbolEdge | None]:
    choices: list[tuple[SymbolEdge, SymbolEdge | None]] = []
    for request_edge in request_edges:
        request_key = _request_index_key(request_edge)
        matching_handlers = handled_edges_by_request.get(request_key, []) if request_key else []
        choices.append((request_edge, matching_handlers[0] if matching_handlers else None))
    choices.sort(
        key=lambda item: (
            0 if item[1] and item[1].target_symbol_id else 1,
            -float(item[0].confidence),
            _edge_sort_key(item[0]),
        )
    )
    return choices[0] if choices else (None, None)


def _index_request_edges(edges: Sequence[SymbolEdge]) -> dict[str, list[SymbolEdge]]:
    indexed: dict[str, list[SymbolEdge]] = {}
    for edge in edges:
        if edge.source_symbol_id:
            indexed.setdefault(edge.source_symbol_id, []).append(edge)
    for values in indexed.values():
        values.sort(key=_edge_sort_key)
    return indexed


def _index_handled_edges(
    edges: Sequence[SymbolEdge],
) -> dict[tuple[str, str, str], list[SymbolEdge]]:
    indexed: dict[tuple[str, str, str], list[SymbolEdge]] = {}
    for edge in edges:
        request_key = _request_index_key(edge)
        if request_key and edge.target_symbol_id:
            indexed.setdefault(request_key, []).append(edge)
    for values in indexed.values():
        values.sort(key=lambda edge: (-float(edge.confidence), _edge_sort_key(edge)))
    return indexed


def _index_effect_edges(edges: Sequence[SymbolEdge]) -> dict[str, list[SymbolEdge]]:
    indexed: dict[str, list[SymbolEdge]] = {}
    for edge in edges:
        if edge.source_symbol_id:
            indexed.setdefault(edge.source_symbol_id, []).append(edge)
    for values in indexed.values():
        values.sort(key=_edge_sort_key)
    return indexed


def _deduplicate_request_edges(edges: Sequence[SymbolEdge]) -> list[SymbolEdge]:
    best_by_request: dict[tuple[str, str, str], SymbolEdge] = {}
    for edge in edges:
        metadata = _metadata(edge)
        key = (
            edge.source_symbol_id or "",
            str(metadata.get("http_method") or "").upper(),
            _safe_request_path(metadata.get("request_path") or edge.target_path or ""),
        )
        current = best_by_request.get(key)
        if current is None or _request_edge_preference(edge) < _request_edge_preference(
            current
        ):
            best_by_request[key] = edge
    return sorted(best_by_request.values(), key=_edge_sort_key)


def _request_edge_preference(edge: SymbolEdge) -> tuple[Any, ...]:
    metadata = _metadata(edge)
    return (
        -float(edge.confidence),
        edge.source_start_line or 0,
        edge.source_end_line or 0,
        str(metadata.get("http_method") or "").upper(),
        _safe_request_path(metadata.get("request_path") or edge.target_path or ""),
    )


def _request_index_key(edge: SymbolEdge) -> tuple[str, str, str] | None:
    metadata = _metadata(edge)
    source_symbol_id = edge.source_symbol_id or ""
    method = str(metadata.get("http_method") or "").upper()
    raw_path = metadata.get("request_path")
    if edge.relation == "REQUESTS" and not raw_path:
        raw_path = edge.target_path
    request_path = _safe_request_path(raw_path)
    if not source_symbol_id or not request_path or not method or method == "UNKNOWN":
        return None
    return source_symbol_id, method, request_path


def _step(
    *,
    flow_id: str,
    ordinal: int,
    identity: str,
    title: str,
    role: str,
    executes_when: str,
    input: str,
    output: str,
    relation_type: str,
    confidence: Confidence,
    evidence: FeatureFlowEvidence,
) -> FeatureFlowStep:
    return FeatureFlowStep(
        id=_stable_id("step", f"{flow_id}|{identity}"),
        ordinal=ordinal,
        title=title,
        role=role,
        executes_when=executes_when,
        input=input,
        output_or_side_effect=output,
        relation_type=relation_type,
        confidence=confidence,
        evidence=[evidence],
    )


def _step_identity(
    *,
    relation: str,
    symbol: Symbol | None,
    evidence: FeatureFlowEvidence,
    method: str = "",
    request_path: str = "",
    semantic_target: str = "",
) -> str:
    return "|".join(
        (
            relation,
            symbol.qualified_name if symbol else "file-scope",
            evidence.path,
            str(evidence.start_line),
            str(evidence.end_line),
            method,
            _safe_request_path(request_path),
            semantic_target,
        )
    )


def _link_steps(steps: Sequence[FeatureFlowStep]) -> list[FeatureFlowStep]:
    return [
        step.model_copy(
            update={
                "ordinal": index + 1,
                "previous_step_id": steps[index - 1].id if index else None,
                "next_step_id": steps[index + 1].id if index + 1 < len(steps) else None,
            }
        )
        for index, step in enumerate(steps)
    ]


def _source_evidence(
    edge: SymbolEdge,
    file_by_id: dict[str, FileRecord],
    symbol_by_id: dict[str, Symbol],
    reason: str,
) -> FeatureFlowEvidence | None:
    file = file_by_id.get(edge.source_file_id)
    if file and _valid_range(edge.source_start_line, edge.source_end_line, file):
        return FeatureFlowEvidence(
            file_id=file.id,
            path=file.path,
            start_line=int(edge.source_start_line),
            end_line=int(edge.source_end_line),
            reason=reason,
        )
    source_symbol = symbol_by_id.get(edge.source_symbol_id or "")
    if source_symbol:
        return _symbol_evidence(source_symbol, file_by_id, reason)
    return None


def _symbol_evidence(
    symbol: Symbol,
    file_by_id: dict[str, FileRecord],
    reason: str,
) -> FeatureFlowEvidence | None:
    file = file_by_id.get(symbol.file_id)
    if not file or not _valid_range(symbol.start_line, symbol.end_line, file):
        return None
    return FeatureFlowEvidence(
        file_id=file.id,
        path=file.path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        reason=reason,
    )


def _valid_range(start: object, end: object, file: FileRecord) -> bool:
    return (
        isinstance(start, int)
        and isinstance(end, int)
        and 1 <= start <= end <= max(1, file.line_count)
    )


def _confidence_for_edge(edge: SymbolEdge) -> Confidence:
    confidence = float(edge.confidence)
    if confidence >= 0.9:
        return "verified"
    if confidence >= 0.65:
        return "inferred"
    return "unknown"


def _flow_confidence(
    *,
    trigger_edge: SymbolEdge,
    request_edge: SymbolEdge | None,
    handled_edge: SymbolEdge | None,
    has_handler: bool,
    has_route: bool,
) -> Confidence:
    confidences = [float(trigger_edge.confidence)]
    if request_edge:
        confidences.append(float(request_edge.confidence))
    if handled_edge:
        confidences.append(float(handled_edge.confidence))
    if has_handler and has_route and min(confidences) >= 0.9:
        return "verified"
    if has_handler and min(confidences) >= 0.65:
        return "inferred"
    return "unknown"


def _involved_areas(steps: Sequence[FeatureFlowStep]) -> list[str]:
    labels = {
        "user_trigger": "사용자 화면",
        "client_handler": "이벤트 처리",
        "request": "API 요청",
        "server_handler": "서버 라우트",
        "storage_read": "브라우저 저장소",
        "storage_write": "브라우저 저장소",
        "state_write": "화면 상태",
        "navigation": "화면 이동",
        "external_service": "외부 서비스",
    }
    return list(dict.fromkeys(labels.get(step.role, "기타") for step in steps))


def _event_label(event_name: str) -> str:
    return {
        "onClick": "클릭",
        "onSubmit": "폼 제출",
        "onChange": "입력 변경",
    }.get(event_name, event_name)


def _is_non_representative_file(file: FileRecord | None) -> bool:
    if file is None:
        return False
    parts = tuple(
        part.casefold() for part in PurePosixPath(file.path.replace("\\", "/")).parts
    )
    if any(part in NON_REPRESENTATIVE_DIRECTORIES for part in parts[:-1]):
        return True
    filename = parts[-1] if parts else ""
    stem = PurePosixPath(filename).stem
    return (
        stem in NON_REPRESENTATIVE_DIRECTORIES
        or filename.startswith(("test_", "spec_", "fixture_"))
        or any(
            marker in filename
            for marker in (".test.", ".spec.", ".stories.", ".story.", ".fixture.")
        )
        or stem.endswith(("_test", "_spec", "_fixture"))
    )


def _safe_request_path(value: object) -> str:
    if not isinstance(value, str):
        return ""
    without_query = value.strip().split("#", 1)[0].split("?", 1)[0]
    if not without_query:
        return ""
    try:
        parsed = urlsplit(without_query)
    except ValueError:
        return _strip_ambiguous_userinfo(without_query)
    if parsed.netloc:
        netloc = _safe_netloc(parsed)
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", "")) if netloc else parsed.path
    if parsed.scheme and "@" in parsed.path:
        return parsed.path.rsplit("@", 1)[-1]
    return parsed.path


def _safe_netloc(parsed: SplitResult) -> str:
    hostname = parsed.hostname or ""
    if not hostname:
        return ""
    safe_hostname = f"[{hostname}]" if ":" in hostname else hostname
    try:
        port = parsed.port
    except ValueError:
        port = None
    return f"{safe_hostname}:{port}" if port is not None else safe_hostname


def _strip_ambiguous_userinfo(value: str) -> str:
    if value.startswith(("/", "./", "../")):
        return value
    return value.rsplit("@", 1)[-1] if "@" in value else value


def _file_stem(path: str) -> str:
    return PurePosixPath(path).stem or path


def _metadata(edge: SymbolEdge | None) -> dict[str, Any]:
    metadata = getattr(edge, "metadata_json", None) if edge is not None else None
    return metadata if isinstance(metadata, dict) else {}


def _edge_sort_key(edge: SymbolEdge) -> tuple[Any, ...]:
    metadata = _metadata(edge)
    return (
        edge.source_file_id,
        edge.source_start_line or 0,
        edge.source_end_line or 0,
        edge.relation,
        edge.source_symbol_id or "",
        edge.target_symbol_id or "",
        edge.target_path or "",
        str(metadata.get("event_name") or ""),
        str(metadata.get("http_method") or ""),
        str(metadata.get("request_path") or ""),
        edge.id,
    )


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"
