from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.models import RepositorySnapshot
from app.navigation.versions import REPOSITORY_STORY_VERSION
from app.schemas import (
    ArchitectureGraphEdge,
    ArchitectureGraphEvidence,
    ArchitectureGraphNode,
    ArchitectureGraphResponse,
    FeatureFlowSummary,
    ProjectMapEvidence,
    ProjectMapResponse,
    RepositoryStoryConnection,
    RepositoryStoryPurpose,
    RepositoryStoryResponse,
    RepositoryStoryRole,
)


@dataclass(frozen=True)
class RoleDefinition:
    display_name: str
    role_summary: str
    why_it_exists: str
    contribution_to_goal: str
    receives: tuple[str, ...]
    produces: tuple[str, ...]


ROLE_ORDER = (
    "experience",
    "public_api",
    "request_gateway",
    "analysis",
    "understanding",
    "learning",
    "application",
    "persistence",
    "external",
    "runtime",
    "shared",
    "core",
)

ROLE_DEFINITIONS = {
    "experience": RoleDefinition(
        "사용자 작업 공간",
        "사용자의 입력을 받고 분석 결과를 구조도와 설명으로 보여줍니다.",
        "사람이 복잡한 코드를 직접 훑지 않고도 저장소를 탐색할 수 있는 입구가 필요합니다.",
        "저장소 분석 결과를 사람이 이해하고 다음 행동을 선택할 수 있는 화면으로 바꿉니다.",
        ("저장소 주소와 사용자의 탐색·학습 요청",),
        ("분석 요청과 선택한 구조·기능 문맥",),
    ),
    "public_api": RoleDefinition(
        "공개 사용 진입점",
        "다른 코드가 이 저장소의 핵심 기능을 호출할 수 있는 사용 방법을 제공합니다.",
        "라이브러리 내부 구현을 몰라도 안정된 방식으로 기능을 사용할 수 있어야 합니다.",
        "저장소의 핵심 기능을 외부 프로그램이 사용할 수 있는 결과로 전달합니다.",
        ("외부 프로그램의 입력과 옵션",),
        ("라이브러리의 처리 결과 또는 오류",),
    ),
    "request_gateway": RoleDefinition(
        "요청 접수와 작업 전달",
        "화면이나 외부 호출에서 온 요청을 확인하고 알맞은 처리 과정으로 전달합니다.",
        "빠른 요청 처리와 오래 걸리는 분석 작업을 분리해야 서비스가 안정적으로 동작합니다.",
        "사용자의 요청이 분석·저장·설명 기능으로 안전하게 이어지도록 연결합니다.",
        ("사용자 요청과 저장소 정보",),
        ("검증된 작업 요청과 API 응답",),
    ),
    "analysis": RoleDefinition(
        "저장소 수집과 코드 분석",
        "저장소 코드를 가져와 파일, 함수, 호출 관계처럼 분석 가능한 정보로 바꿉니다.",
        "구조도와 설명이 추측이 아니라 실제 코드 근거를 사용하려면 공통 분석 재료가 필요합니다.",
        "구조도, 기능 흐름, 코드 설명이 함께 사용하는 신뢰 가능한 분석 데이터를 만듭니다.",
        ("저장소 주소, branch와 commit 정보",),
        ("파일, 심볼, 관계와 분석 snapshot",),
    ),
    "understanding": RoleDefinition(
        "구조와 기능 흐름 구성",
        "분석 데이터를 사람이 읽을 수 있는 구조, 기능 흐름, 코드 근거로 정리합니다.",
        "파일과 함수의 원시 연결만으로는 저장소의 목적과 실행 과정을 이해하기 어렵습니다.",
        "복잡한 분석 결과를 전체 구조와 대표 기능 이야기로 바꿔 이해 시간을 줄입니다.",
        ("파일, 심볼, 호출·데이터 관계",),
        ("Repository Structure, 기능 흐름과 근거 설명",),
    ),
    "learning": RoleDefinition(
        "설명과 학습 제공",
        "현재 선택한 코드와 구조에 맞춰 설명, 질문, 학습 경로를 제공합니다.",
        "사용자의 배경지식과 궁금한 깊이가 서로 다르기 때문에 "
        "같은 정보를 상황에 맞게 설명해야 합니다.",
        "구조를 본 사용자가 실제 코드를 이해하고 스스로 다음 단계를 학습하도록 돕습니다.",
        ("선택한 역할·기능·코드와 학습 수준",),
        ("맞춤 설명, 학습 활동과 심화 조사 결과",),
    ),
    "application": RoleDefinition(
        "서비스 기능 실행",
        "여러 요청과 분석 결과를 조합해 서비스의 실제 동작을 수행합니다.",
        "화면, 분석, 저장소 사이의 규칙을 한곳에서 조정해야 기능이 일관되게 동작합니다.",
        "사용자의 목적을 실제 처리 단계와 결과로 연결합니다.",
        ("검증된 요청과 분석 문맥",),
        ("처리 결과와 다음 작업",),
    ),
    "persistence": RoleDefinition(
        "분석 결과와 상태 저장",
        "분석 결과, 작업 상태, 학습 진행 상황을 나중에 다시 사용할 수 있게 저장합니다.",
        "분석과 학습은 여러 단계에 걸쳐 진행되므로 결과와 진행 상태가 사라지지 않아야 합니다.",
        "한 번 만든 분석 결과를 구조도, 설명, 변경 검토에서 반복해서 사용할 수 있게 합니다.",
        ("분석 결과와 사용자 진행 상태",),
        ("다시 불러올 수 있는 snapshot과 기록",),
    ),
    "external": RoleDefinition(
        "외부 저장소와 AI 서비스",
        "GitHub 같은 외부 시스템에서 코드를 가져오거나 선택적인 AI 설명 기능을 사용합니다.",
        "서비스 밖에 있는 저장소와 모델 기능을 안전한 경계를 통해 사용해야 합니다.",
        "분석할 원본 코드와 보강 설명을 서비스 내부 처리 과정에 제공합니다.",
        ("외부 서비스 요청",),
        ("저장소 내용 또는 모델 응답",),
    ),
    "runtime": RoleDefinition(
        "실행 환경과 설정",
        "애플리케이션이 어떤 환경에서 어떻게 실행되고 연결되는지 정의합니다.",
        "Web, API, Worker와 데이터 서비스가 같은 설정을 사용해야 재현 가능하게 동작합니다.",
        "분석과 화면 기능이 개발·운영 환경에서 일관되게 실행되도록 받쳐 줍니다.",
        ("환경 변수와 실행 설정",),
        ("서비스별 런타임 구성",),
    ),
    "shared": RoleDefinition(
        "공통 계약과 도구",
        "여러 기능이 함께 사용하는 데이터 형식과 공통 도구를 제공합니다.",
        "같은 정보를 기능마다 다르게 해석하면 구조도와 설명이 서로 어긋날 수 있습니다.",
        "화면과 서버가 같은 의미와 형식으로 데이터를 주고받도록 합니다.",
        ("공통 데이터와 설정",),
        ("재사용 가능한 계약과 도구",),
    ),
    "core": RoleDefinition(
        "핵심 처리 엔진",
        "입력 데이터를 저장소가 약속한 핵심 규칙에 따라 처리합니다.",
        "외부 사용 방법과 세부 구현을 분리하면 핵심 동작을 안정적으로 유지할 수 있습니다.",
        "저장소가 제공하려는 가장 중요한 기능의 실제 결과를 만듭니다.",
        ("공개 진입점에서 전달된 입력",),
        ("처리된 결과와 명시적인 실패",),
    ),
}

CONNECTION_LABELS = {
    "TRIGGERS": ("사용자 행동을 시작합니다", "사용자의 행동이 다음 역할의 처리를 시작합니다."),
    "REQUESTS": ("요청을 전달합니다", "필요한 정보를 담은 요청을 다음 역할에 전달합니다."),
    "HANDLED_BY": ("처리를 맡깁니다", "요청을 실제로 처리할 책임 영역에 넘깁니다."),
    "CALLS": ("작업을 이어갑니다", "현재 작업을 끝내기 위해 다음 역할의 기능을 호출합니다."),
    "READS": ("저장된 정보를 읽습니다", "다음 역할이 관리하는 정보를 읽어 처리에 사용합니다."),
    "WRITES": ("결과를 저장합니다", "다음 단계에서 다시 사용할 수 있도록 처리 결과를 저장합니다."),
    "NAVIGATES_TO": (
        "화면 문맥을 이동합니다",
        "사용자를 다음 화면 또는 작업 문맥으로 이동시킵니다.",
    ),
    "USES_EXTERNAL": ("외부 기능을 사용합니다", "저장소 밖 서비스의 기능이나 데이터를 사용합니다."),
    "RAISES": ("실패 가능성을 알립니다", "처리를 계속할 수 없는 조건을 명시적으로 전달합니다."),
    "IMPORTS": ("공통 기능을 사용합니다", "다음 역할이 제공하는 코드와 계약을 재사용합니다."),
}

RELATION_PRIORITY = tuple(CONNECTION_LABELS)


def build_repository_story(
    snapshot: RepositorySnapshot,
    project_map: ProjectMapResponse,
    implementation_graph: ArchitectureGraphResponse,
    features: list[FeatureFlowSummary],
) -> RepositoryStoryResponse:
    is_library = not any(
        group.layer in {"client", "server"} for group in implementation_graph.groups
    )
    role_nodes: dict[str, list[ArchitectureGraphNode]] = defaultdict(list)
    role_by_node: dict[str, str] = {}
    for node in implementation_graph.nodes:
        role_key = _role_for_node(node, implementation_graph, is_library=is_library)
        role_nodes[role_key].append(node)
        role_by_node[node.id] = role_key

    roles = [
        _build_role(role_key, role_nodes[role_key])
        for role_key in ROLE_ORDER
        if role_nodes.get(role_key)
    ]
    connections = _build_connections(
        implementation_graph.edges,
        role_by_node,
    )
    purpose = _build_purpose(project_map, roles, features, is_library=is_library)
    limitations = [
        "기본 역할 보기는 여러 구현 파일을 같은 사용자 목적과 책임 기준으로 묶어 보여줍니다.",
        "실제 파일과 기술 관계는 각 역할의 구현 상세 보기에서 확인할 수 있습니다.",
        *implementation_graph.limitations[:2],
    ]
    return RepositoryStoryResponse(
        repository_name=implementation_graph.repository_name,
        snapshot_id=snapshot.id,
        commit_sha=snapshot.commit_sha or "",
        analysis_version=REPOSITORY_STORY_VERSION,
        purpose=purpose,
        roles=roles,
        connections=connections,
        features=features,
        implementation_graph=implementation_graph,
        limitations=list(dict.fromkeys(limitations)),
    )


def _role_for_node(
    node: ArchitectureGraphNode,
    graph: ArchitectureGraphResponse,
    *,
    is_library: bool,
) -> str:
    path = node.evidence[0].path.casefold()
    layer = next(
        (group.layer for group in graph.groups if group.id == node.group_id),
        "shared",
    )
    name = f"{path} {node.label.casefold()} {node.node_type.casefold()}"

    if is_library:
        filename = PurePosixPath(path).stem
        if node.feature_flow_ids or filename in {"index", "main", "lib", "__init__"}:
            return "public_api"
        if layer == "configuration":
            return "runtime"
        if layer in {"domain", "server"}:
            return "core"
        return "shared"

    if layer == "client":
        return "experience"
    if any(
        token in name
        for token in (
            "learning",
            "assessment",
            "mastery",
            "guidance",
            "deep_task",
            "deep-task",
            "chat",
            "voice",
            "concept",
        )
    ):
        return "learning"
    if any(
        token in name
        for token in (
            "/navigation/",
            "project_map",
            "feature_flow",
            "architecture_",
            "code_focus",
            "change_brief",
            "retrieval",
            "embedding",
        )
    ):
        return "understanding"
    if (
        node.node_type == "worker"
        or "/analysis/" in path
        or "repository_analysis" in name
        or "parser" in name
    ):
        return "analysis"
    if any(
        token in name
        for token in (
            "/api/repositories",
            "/queue",
            "router.py",
            "main.py",
            "health.py",
        )
    ):
        return "request_gateway"
    if layer == "data" or any(
        token in name for token in ("/models", "/schemas", "migration", "database")
    ):
        return "persistence"
    if layer == "external":
        return "external"
    if layer == "configuration":
        return "runtime"
    if layer == "shared":
        return "shared"
    return "application"


def _build_role(role_key: str, nodes: list[ArchitectureGraphNode]) -> RepositoryStoryRole:
    definition = ROLE_DEFINITIONS[role_key]
    evidence = _deduplicate_evidence(item for node in nodes for item in node.evidence)
    inputs = _plain_io(item for node in nodes for item in node.inputs)
    outputs = _plain_io(item for node in nodes for item in node.outputs)
    capability_ids = sorted({item for node in nodes for item in node.capability_ids})
    feature_flow_ids = sorted({item for node in nodes for item in node.feature_flow_ids})
    confidence = "verified" if any(node.confidence == "verified" for node in nodes) else "inferred"
    return RepositoryStoryRole(
        id=f"role_{role_key}",
        display_name=definition.display_name,
        role_summary=definition.role_summary,
        why_it_exists=definition.why_it_exists,
        contribution_to_goal=definition.contribution_to_goal,
        receives=inputs[:4] or list(definition.receives),
        produces=outputs[:4] or list(definition.produces),
        member_node_ids=sorted(node.id for node in nodes),
        member_file_ids=sorted({item.file_id for item in evidence}),
        capability_ids=capability_ids,
        feature_flow_ids=feature_flow_ids,
        confidence=confidence,
        evidence=evidence[:6],
    )


def _build_connections(
    edges: list[ArchitectureGraphEdge],
    role_by_node: dict[str, str],
) -> list[RepositoryStoryConnection]:
    grouped: dict[tuple[str, str], list[ArchitectureGraphEdge]] = defaultdict(list)
    for edge in edges:
        source_key = role_by_node.get(edge.source)
        target_key = role_by_node.get(edge.target)
        if source_key is None or target_key is None or source_key == target_key:
            continue
        grouped[(source_key, target_key)].append(edge)

    connections: list[RepositoryStoryConnection] = []
    for (source_key, target_key), grouped_edges in sorted(
        grouped.items(),
        key=lambda item: (
            ROLE_ORDER.index(item[0][0]),
            ROLE_ORDER.index(item[0][1]),
        ),
    ):
        relations = sorted(
            {edge.relation for edge in grouped_edges},
            key=lambda relation: (
                RELATION_PRIORITY.index(relation)
                if relation in RELATION_PRIORITY
                else len(RELATION_PRIORITY),
                relation,
            ),
        )
        primary_relation = relations[0]
        label, description = CONNECTION_LABELS.get(
            primary_relation,
            ("정보를 전달합니다", "현재 역할의 결과를 다음 역할에서 사용합니다."),
        )
        evidence = _deduplicate_evidence(item for edge in grouped_edges for item in edge.evidence)
        confidence = (
            "verified"
            if any(edge.confidence == "verified" for edge in grouped_edges)
            else "inferred"
        )
        source = f"role_{source_key}"
        target = f"role_{target_key}"
        connections.append(
            RepositoryStoryConnection(
                id=_stable_id("story_edge", f"{source}:{target}:{','.join(relations)}"),
                source=source,
                target=target,
                label=label,
                description=description,
                relation_types=relations,
                feature_flow_ids=sorted(
                    {flow_id for edge in grouped_edges for flow_id in edge.feature_flow_ids}
                ),
                confidence=confidence,
                evidence=evidence[:5],
            )
        )
    return connections


def _build_purpose(
    project_map: ProjectMapResponse,
    roles: list[RepositoryStoryRole],
    features: list[FeatureFlowSummary],
    *,
    is_library: bool,
) -> RepositoryStoryPurpose:
    evidence = _purpose_evidence(project_map, roles)
    one_liner = project_map.summary.strip()
    if not one_liner:
        one_liner = (
            f"{project_map.repository_name} 저장소가 제공하는 핵심 기능과 "
            "그 기능을 만드는 역할을 설명합니다."
        )
    if is_library:
        audience = "이 라이브러리의 기능을 자신의 프로그램에서 사용하는 사람"
        outcome = (
            features[0].outcome
            if features
            else "공개된 사용 방법을 통해 핵심 처리 결과를 안정적으로 얻을 수 있습니다."
        )
    elif any(role.id == "role_experience" for role in roles):
        audience = "저장소의 구조와 기능을 이해하거나 변경하려는 사용자"
        outcome = (
            "코드의 전체 구조, 대표 기능 흐름과 변경 지점을 실제 근거와 함께 이해할 수 있게 합니다."
        )
    else:
        audience = "이 서비스에 요청을 보내는 사용자와 다른 시스템"
        outcome = (
            features[0].outcome if features else "입력 요청을 저장소의 핵심 처리 결과로 바꿉니다."
        )
    how_it_works = [
        f"{index}. {role.display_name}: {role.role_summary}"
        for index, role in enumerate(roles[:5], start=1)
    ]
    return RepositoryStoryPurpose(
        one_liner=one_liner,
        primary_audience=audience,
        primary_outcome=outcome,
        how_it_works=how_it_works,
        confidence=project_map.summary_confidence,
        evidence=evidence,
    )


def _purpose_evidence(
    project_map: ProjectMapResponse,
    roles: list[RepositoryStoryRole],
) -> list[ArchitectureGraphEvidence]:
    candidates: list[ProjectMapEvidence | ArchitectureGraphEvidence] = []
    candidates.extend(project_map.read_first[:2])
    for capability in project_map.capabilities[:2]:
        candidates.extend(capability.evidence[:1])
    if not candidates and roles:
        candidates.extend(roles[0].evidence[:1])
    return _deduplicate_evidence(_as_architecture_evidence(item) for item in candidates)[:4]


def _as_architecture_evidence(
    evidence: ProjectMapEvidence | ArchitectureGraphEvidence,
) -> ArchitectureGraphEvidence:
    if isinstance(evidence, ArchitectureGraphEvidence):
        return evidence
    return ArchitectureGraphEvidence(
        file_id=evidence.file_id,
        path=evidence.path,
        start_line=evidence.start_line,
        end_line=evidence.end_line,
        reason=evidence.reason,
    )


def _deduplicate_evidence(
    evidence_items,
) -> list[ArchitectureGraphEvidence]:
    output: list[ArchitectureGraphEvidence] = []
    seen: set[tuple[str, int, int]] = set()
    for evidence in evidence_items:
        converted = _as_architecture_evidence(evidence)
        key = (converted.file_id, converted.start_line, converted.end_line)
        if key in seen:
            continue
        seen.add(key)
        output.append(converted)
    return output


def _plain_io(items) -> list[str]:
    output: list[str] = []
    for item in items:
        value = item.strip()
        if not value or value in output:
            continue
        output.append(value)
    return output


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
