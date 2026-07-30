from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from app.learning.explanations import segment_source
from app.models import CodeChunk, FileRecord, RepositorySnapshot, Symbol, SymbolEdge
from app.navigation.versions import CODE_EXPLANATION_VERSION
from app.schemas import (
    CodeExplanationEvidence,
    CodeExplanationRelatedStep,
    CodeExplanationResponse,
    CodeExplanationSyntaxSegment,
    CodeSelection,
    FeatureFlowStep,
)

SEMANTIC_FOCUS_RELATIONS = frozenset(
    {
        "TRIGGERS",
        "REQUESTS",
        "HANDLED_BY",
        "READS",
        "WRITES",
        "NAVIGATES_TO",
        "USES_EXTERNAL",
        "CALLS",
        "RAISES",
    }
)
RELATION_COPY = {
    "TRIGGERS": "다음 동작을 시작합니다",
    "REQUESTS": "서버에 요청을 보냅니다",
    "HANDLED_BY": "서버 요청 처리로 연결됩니다",
    "READS": "저장된 값을 읽습니다",
    "WRITES": "상태 또는 저장값을 바꿉니다",
    "NAVIGATES_TO": "다른 화면으로 이동합니다",
    "USES_EXTERNAL": "외부 서비스를 사용합니다",
    "CALLS": "연결된 함수나 서비스를 호출합니다",
    "RAISES": "명시적인 실패 조건에서 예외를 발생시킵니다",
}
ROLE_COPY = {
    "user_trigger": "사용자 행동이 시작되는 화면 경계",
    "client_handler": "사용자 행동을 처리하는 화면 로직",
    "request": "화면과 서버를 잇는 네트워크 경계",
    "server_handler": "요청을 받는 서버 경계",
    "storage_read": "저장된 값을 불러오는 경계",
    "storage_write": "값을 저장하는 경계",
    "state_write": "사용자에게 보이는 화면 상태를 바꾸는 경계",
    "navigation": "다음 화면으로 사용자를 이동시키는 경계",
    "external_service": "프로젝트 밖 서비스와 통신하는 경계",
}
NODE_COPY = {
    "function_declaration": "여기서 이름 있는 함수를 선언합니다.",
    "function_expression": "함수 값을 만들어 변수나 인자로 전달합니다.",
    "arrow_function": "짧은 함수 표현으로 실행할 동작을 정의합니다.",
    "method_definition": "객체나 클래스가 제공하는 동작을 정의합니다.",
    "lexical_declaration": "이후 코드에서 사용할 값을 변수에 묶습니다.",
    "variable_declaration": "이후 코드에서 사용할 변수를 선언합니다.",
    "expression_statement": "함수 호출이나 값 변경 같은 동작을 실행합니다.",
    "return_statement": "호출한 곳으로 결과를 돌려줍니다.",
    "throw_statement": "현재 정상 흐름을 멈추고 오류를 전달합니다.",
    "if_statement": "조건에 따라 실행할 경로를 나눕니다.",
    "for_statement": "조건을 만족하는 동안 같은 동작을 반복합니다.",
    "for_in_statement": "여러 항목을 하나씩 꺼내 같은 동작을 반복합니다.",
    "while_statement": "조건이 유지되는 동안 같은 동작을 반복합니다.",
    "switch_statement": "값에 따라 여러 실행 경로 중 하나를 선택합니다.",
    "try_statement": "실패할 수 있는 동작과 오류 처리 범위를 묶습니다.",
    "catch_clause": "앞선 동작에서 발생한 오류를 받아 처리합니다.",
    "import_statement": "다른 모듈이 제공하는 기능을 이 파일로 가져옵니다.",
}


def build_code_explanation(
    *,
    snapshot: RepositorySnapshot,
    file: FileRecord,
    selection: CodeSelection,
    depth: str,
    symbols: Sequence[Symbol],
    edges: Sequence[SymbolEdge],
    flow_step: FeatureFlowStep | None = None,
) -> CodeExplanationResponse:
    selected_source = _selected_source(file, selection)
    enclosing_symbol = _enclosing_symbol(symbols, selection)
    relevant_edges = _relevant_edges(edges, selection, file)
    evidence = CodeExplanationEvidence(
        file_id=file.id,
        path=file.path,
        start_line=selection.start_line,
        end_line=selection.end_line,
        reason="사용자가 선택했거나 기능 흐름에서 연 코드 범위입니다.",
    )
    related_steps = [
        _related_step(edge, file) for edge in relevant_edges[:5]
    ]
    concepts = _required_concepts(selected_source, file.language)
    limitations = [
        "정적 코드와 검증된 의미 관계만 사용했으며 실제 런타임 값은 확인하지 않았습니다."
    ]
    if flow_step is None:
        limitations.append(
            "검증된 기능 흐름 단계와 직접 연결되지 않아 파일·심볼·관계 근거로 설명했습니다."
        )
    if not relevant_edges:
        limitations.append(
            "선택 범위와 겹치는 의미 관계가 없어 다음 실행 연결을 충분히 확인하지 못했습니다."
        )

    confidence = (
        flow_step.confidence
        if flow_step
        else "inferred"
        if enclosing_symbol
        else "unknown"
    )
    purpose = (
        flow_step.title
        if flow_step
        else _purpose(enclosing_symbol, file, relevant_edges)
    )
    executes_when = (
        flow_step.executes_when
        if flow_step
        else _executes_when(enclosing_symbol, relevant_edges)
    )
    input_text = (
        flow_step.input
        if flow_step
        else _input_description(enclosing_symbol, relevant_edges)
    )
    output = (
        flow_step.output_or_side_effect
        if flow_step
        else _output_description(relevant_edges)
    )
    project_role = (
        ROLE_COPY.get(flow_step.role, _project_role(file.path))
        if flow_step
        else _project_role(file.path)
    )
    syntax_segments = (
        _syntax_segments(snapshot, file, selection, selected_source)
        if depth == "syntax"
        else []
    )
    analogy = (
        _analogy(project_role, output) if depth == "analogy" else None
    )
    semantic_key = "|".join(
        (
            snapshot.id,
            snapshot.commit_sha or "",
            file.id,
            str(selection.start_line),
            str(selection.end_line),
            depth,
            flow_step.id if flow_step else "",
        )
    )
    return CodeExplanationResponse(
        id=_stable_id("focus", semantic_key),
        snapshot_id=snapshot.id,
        analysis_version=CODE_EXPLANATION_VERSION,
        depth=depth,
        selection=selection,
        purpose=purpose,
        executes_when=executes_when,
        input=input_text,
        output_or_side_effect=output,
        project_role=project_role,
        change_impact=_change_impact(file, enclosing_symbol, relevant_edges),
        required_concepts=concepts,
        related_steps=related_steps,
        syntax_segments=syntax_segments,
        analogy=analogy,
        confidence=confidence,
        evidence=[evidence],
        limitations=limitations,
    )


def _selected_source(file: FileRecord, selection: CodeSelection) -> str:
    lines = file.content.splitlines()
    return "\n".join(lines[selection.start_line - 1 : selection.end_line])


def _enclosing_symbol(
    symbols: Sequence[Symbol], selection: CodeSelection
) -> Symbol | None:
    candidates = [
        symbol
        for symbol in symbols
        if symbol.start_line <= selection.start_line
        and symbol.end_line >= selection.end_line
    ]
    return min(
        candidates,
        key=lambda symbol: (
            symbol.end_line - symbol.start_line,
            symbol.start_line,
            symbol.qualified_name,
        ),
        default=None,
    )


def _relevant_edges(
    edges: Sequence[SymbolEdge], selection: CodeSelection, file: FileRecord
) -> list[SymbolEdge]:
    return sorted(
        (
            edge
            for edge in edges
            if edge.relation in SEMANTIC_FOCUS_RELATIONS
            and edge.source_file_id == file.id
            and isinstance(edge.source_start_line, int)
            and isinstance(edge.source_end_line, int)
            and edge.source_start_line <= selection.end_line
            and edge.source_end_line >= selection.start_line
        ),
        key=lambda edge: (
            edge.source_start_line or 0,
            edge.source_end_line or 0,
            edge.relation,
            edge.target_path or "",
            edge.id,
        ),
    )


def _purpose(
    symbol: Symbol | None, file: FileRecord, edges: Sequence[SymbolEdge]
) -> str:
    if symbol:
        kind = {
            "component": "화면 컴포넌트",
            "route": "서버 라우트",
            "function": "함수",
            "method": "메서드",
            "class": "클래스",
        }.get(symbol.kind, "코드 단위")
        return f"{symbol.display_name} {kind} 안에서 맡은 동작을 구현합니다."
    if edges:
        return RELATION_COPY.get(edges[0].relation, "프로젝트 동작 일부를 구현합니다.")
    return f"{PurePosixPath(file.path).name} 파일의 선택된 코드 범위입니다."


def _executes_when(symbol: Symbol | None, edges: Sequence[SymbolEdge]) -> str:
    relations = {edge.relation for edge in edges}
    if symbol and symbol.kind == "route":
        return "해당 HTTP 메서드와 경로로 서버 요청이 들어올 때 실행됩니다."
    if "TRIGGERS" in relations:
        return "사용자가 연결된 화면 요소를 조작할 때 실행됩니다."
    if "REQUESTS" in relations:
        return "상위 핸들러가 서버 요청 코드를 실행할 때 동작합니다."
    if symbol:
        return f"다른 코드가 {symbol.display_name}을 호출하거나 렌더링할 때 실행됩니다."
    return "상위 코드가 이 범위에 도달할 때 실행됩니다."


def _input_description(
    symbol: Symbol | None, edges: Sequence[SymbolEdge]
) -> str:
    request = next((edge for edge in edges if edge.relation == "REQUESTS"), None)
    if request:
        metadata = _metadata(request)
        method = str(metadata.get("http_method") or "HTTP")
        path = str(metadata.get("request_path") or request.target_path or "요청 경로")
        return f"{method} {path} 요청에 필요한 화면 상태 또는 함수 인자"
    if symbol:
        return f"{symbol.display_name}에 전달되는 인자와 이 범위에서 참조하는 주변 상태"
    return "상위 코드에서 전달되거나 앞선 줄에서 준비된 값"


def _output_description(edges: Sequence[SymbolEdge]) -> str:
    if not edges:
        return "선택 범위 이후의 결과는 정적 관계로 확인되지 않았습니다."
    descriptions = [
        RELATION_COPY.get(edge.relation, "다음 동작으로 이어집니다")
        for edge in edges
    ]
    return " · ".join(dict.fromkeys(descriptions))


def _project_role(path: str) -> str:
    lower = f"/{path.casefold()}"
    name = PurePosixPath(lower).name
    if "/api/" in lower or name.startswith("route."):
        return "화면이나 외부 호출에서 들어온 요청을 받는 서버 경계"
    if any(part in lower for part in ("/components/", "/app/", "/pages/")):
        return "사용자에게 보이는 화면과 상호작용을 구성하는 인터페이스 영역"
    if any(part in lower for part in ("/services/", "/lib/", "/core/")):
        return "여러 화면이나 서버 경계에서 재사용하는 핵심 로직"
    if any(part in lower for part in ("/models/", "/data/", "/database/")):
        return "데이터의 형태와 저장·조회 방식을 담당하는 영역"
    if ".test." in name or ".spec." in name or "/tests/" in lower:
        return "기대 동작을 검증하고 회귀를 막는 테스트 영역"
    return "이 파일이 속한 기능을 구현하는 코드 영역"


def _change_impact(
    file: FileRecord, symbol: Symbol | None, edges: Sequence[SymbolEdge]
) -> str:
    target = symbol.display_name if symbol else f"{PurePosixPath(file.path).name}의 선택 범위"
    if edges:
        relations = ", ".join(
            dict.fromkeys(edge.relation for edge in edges)
        )
        return (
            f"{target}을 바꾸면 이 범위에서 확인된 {relations} 동작이 직접 달라질 수 있습니다. "
            "호출하는 다른 파일과 런타임 분기는 별도로 확인해야 합니다."
        )
    return (
        f"{target}의 로컬 동작이 달라질 수 있습니다. 직접 연결된 관계가 없어 "
        "다른 파일에 미치는 영향은 추가 검색이 필요합니다."
    )


def _required_concepts(source: str, language: str) -> list[str]:
    concepts: list[str] = []
    checks = (
        (r"\basync\b|\bawait\b", "비동기 실행과 await"),
        (r"\bfetch\s*\(|\baxios\.", "HTTP 요청"),
        (r"\buseState\s*\(|\bset[A-Z]\w*\s*\(", "React 화면 상태"),
        (r"\b(?:localStorage|sessionStorage)\.", "브라우저 저장소"),
        (r"\b(?:router\.(?:push|replace)|redirect)\s*\(", "Next.js 화면 이동"),
        (r"\bon(?:Click|Submit|Change)=", "사용자 이벤트 연결"),
        (r"\btry\s*\{|\bcatch\s*\(", "오류 처리"),
        (r"\bif\s*\(", "조건 분기"),
        (r"\breturn\b", "함수의 반환값"),
    )
    for pattern, label in checks:
        if re.search(pattern, source):
            concepts.append(label)
    if language in {"typescript", "tsx"} and re.search(r"\w+\s*:\s*[A-Za-z]", source):
        concepts.append("TypeScript 타입 표기")
    return concepts[:6] or ["위에서 아래로 실행되는 코드 흐름"]


def _related_step(edge: SymbolEdge, file: FileRecord) -> CodeExplanationRelatedStep:
    target = str(edge.target_path or "확인된 대상")
    return CodeExplanationRelatedStep(
        relation_type=edge.relation,
        title=RELATION_COPY.get(edge.relation, edge.relation),
        target=target,
        confidence=_confidence(float(edge.confidence)),
        evidence=CodeExplanationEvidence(
            file_id=file.id,
            path=file.path,
            start_line=int(edge.source_start_line),
            end_line=int(edge.source_end_line),
            reason=f"{edge.relation} 관계를 추출한 코드 위치입니다.",
        ),
    )


def _syntax_segments(
    snapshot: RepositorySnapshot,
    file: FileRecord,
    selection: CodeSelection,
    source: str,
) -> list[CodeExplanationSyntaxSegment]:
    chunk = CodeChunk(
        id="focus-segment",
        snapshot_id=snapshot.id,
        file_id=file.id,
        chunk_type="selection",
        ordinal=0,
        title=f"{file.path} lines {selection.start_line}-{selection.end_line}",
        language=file.language,
        start_line=selection.start_line,
        end_line=selection.end_line,
        content=source,
        search_text=source,
        embedding_model="none",
        content_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )
    return [
        CodeExplanationSyntaxSegment(
            node_type=segment.node_type,
            start_line=segment.start_line,
            end_line=segment.end_line,
            explanation=NODE_COPY.get(
                segment.node_type,
                "이 문법 단위가 선택 범위의 실행 흐름 일부를 구성합니다.",
            ),
        )
        for segment in segment_source(chunk)[:12]
    ]


def _analogy(project_role: str, output: str) -> str:
    return (
        f"이 코드는 작업대의 한 공정과 같습니다. {project_role}에서 입력을 받아 처리하고, "
        f"다음 공정에는 ‘{output}’에 해당하는 결과를 넘깁니다."
    )


def _confidence(value: float) -> str:
    if value >= 0.9:
        return "verified"
    if value >= 0.65:
        return "inferred"
    return "unknown"


def _metadata(edge: SymbolEdge) -> dict:
    return edge.metadata_json if isinstance(edge.metadata_json, dict) else {}


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"
