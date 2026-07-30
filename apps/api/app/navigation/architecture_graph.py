from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from app.models import FileRecord, RepositorySnapshot, Symbol, SymbolEdge
from app.navigation.versions import ARCHITECTURE_GRAPH_VERSION
from app.schemas import (
    ArchitectureGraphEdge,
    ArchitectureGraphEvidence,
    ArchitectureGraphGroup,
    ArchitectureGraphNode,
    ArchitectureGraphResponse,
    FeatureFlowDetail,
    ProjectMapResponse,
)

MAX_DEFAULT_NODES = 22
MAX_NODES = 34
MAX_EDGES = 48
IMPORTANT_RELATIONS = (
    "TRIGGERS",
    "REQUESTS",
    "HANDLED_BY",
    "READS",
    "WRITES",
    "NAVIGATES_TO",
    "USES_EXTERNAL",
    "RAISES",
    "CALLS",
    "IMPORTS",
)
RELATION_PRIORITY = {relation: index for index, relation in enumerate(IMPORTANT_RELATIONS)}
RELATION_LABELS = {
    "TRIGGERS": "triggers",
    "REQUESTS": "requests",
    "HANDLED_BY": "handled by",
    "READS": "reads",
    "WRITES": "writes",
    "NAVIGATES_TO": "navigates to",
    "USES_EXTERNAL": "uses",
    "RAISES": "fails with",
    "CALLS": "calls",
    "IMPORTS": "depends on",
}
LAYER_LABELS = {
    "client": ("Client", "사용자 상호작용과 화면 상태를 담당합니다."),
    "server": ("Server", "요청 처리와 백그라운드 실행을 담당합니다."),
    "domain": ("Domain", "저장소 분석과 제품 기능의 핵심 규칙을 담당합니다."),
    "data": ("Data", "영속 데이터 모델과 접근 경계를 담당합니다."),
    "external": ("External", "저장소 밖 서비스와 런타임 경계를 나타냅니다."),
    "configuration": ("Configuration", "빌드와 런타임 설정을 담당합니다."),
    "shared": ("Shared", "여러 영역에서 재사용되는 공통 계약을 담당합니다."),
}
EXCLUDED_SEGMENTS = frozenset(
    {
        "test",
        "tests",
        "__tests__",
        "fixture",
        "fixtures",
        "migrations",
        "mocks",
        "stories",
    }
)


def build_architecture_graph(
    snapshot: RepositorySnapshot,
    files: list[FileRecord],
    symbols: list[Symbol],
    semantic_edges: list[SymbolEdge],
    project_map: ProjectMapResponse,
    feature_flows: list[FeatureFlowDetail],
) -> ArchitectureGraphResponse:
    ordered_files = sorted(files, key=lambda item: (item.path.casefold(), item.id))
    file_by_id = {item.id: item for item in ordered_files}
    file_by_path = {item.path: item for item in ordered_files}
    symbol_by_id = {item.id: item for item in symbols}
    capability_by_file: dict[str, set[str]] = defaultdict(set)
    description_by_file: dict[str, list[str]] = defaultdict(list)
    flow_by_file: dict[str, set[str]] = defaultdict(set)
    flow_role_by_file: dict[str, list[str]] = defaultdict(list)
    score: Counter[str] = Counter()

    for capability in project_map.capabilities:
        for evidence in capability.evidence:
            capability_by_file[evidence.file_id].add(capability.id)
            description_by_file[evidence.file_id].append(capability.description)
            score[evidence.file_id] += 3
    for area in project_map.system_areas:
        for evidence in area.evidence:
            description_by_file[evidence.file_id].append(area.description)
            score[evidence.file_id] += 2
    for item in project_map.read_first:
        score[item.file_id] += 3

    mandatory_file_ids: set[str] = set()
    for flow in feature_flows:
        for step in [*flow.normal_steps, *flow.failure_steps]:
            for evidence in step.evidence:
                if evidence.file_id not in file_by_id:
                    continue
                mandatory_file_ids.add(evidence.file_id)
                flow_by_file[evidence.file_id].add(flow.id)
                flow_role_by_file[evidence.file_id].append(step.role)
                score[evidence.file_id] += 4

    resolved_edges: list[tuple[SymbolEdge, FileRecord, FileRecord | None]] = []
    for edge in sorted(semantic_edges, key=_edge_sort_key):
        source_file = file_by_id.get(edge.source_file_id)
        if source_file is None:
            continue
        target_file = _target_file(edge, file_by_id, file_by_path, symbol_by_id)
        resolved_edges.append((edge, source_file, target_file))
        if edge.relation != "IMPORTS":
            score[source_file.id] += 2
            if target_file:
                score[target_file.id] += 2
        else:
            score[source_file.id] += 1
            if target_file:
                score[target_file.id] += 1

    candidates = [item for item in ordered_files if not _is_noise_path(item.path)]
    candidate_layer = {item.id: _layer_for_path(item.path) for item in candidates}
    ranked = sorted(
        candidates,
        key=lambda item: (-score[item.id], _path_priority(item.path), item.path.casefold()),
    )
    target_count = min(MAX_NODES, max(MAX_DEFAULT_NODES, len(mandatory_file_ids)))
    selected_ids = set(mandatory_file_ids)
    ranked_by_layer: dict[str, list[FileRecord]] = defaultdict(list)
    for file in ranked:
        ranked_by_layer[candidate_layer[file.id]].append(file)
    for layer in LAYER_LABELS:
        layer_candidates = ranked_by_layer.get(layer, [])
        if not layer_candidates or not any(score[item.id] > 0 for item in layer_candidates):
            continue
        for file in layer_candidates[:2]:
            if len(selected_ids) >= target_count:
                break
            selected_ids.add(file.id)
    for file in ranked:
        if len(selected_ids) >= target_count:
            break
        if score[file.id] <= 0 and len(selected_ids) >= min(12, target_count):
            break
        selected_ids.add(file.id)
    if not selected_ids:
        selected_ids.update(item.id for item in ranked[: min(12, len(ranked))])

    selected_files = [item for item in ordered_files if item.id in selected_ids]
    layer_by_file = {item.id: _layer_for_path(item.path) for item in selected_files}
    used_layers = sorted(
        set(layer_by_file.values()),
        key=lambda value: list(LAYER_LABELS).index(value),
    )
    groups = [_build_group(layer, selected_files, layer_by_file) for layer in used_layers]

    relation_io = _relation_io(resolved_edges, selected_ids)
    nodes = [
        _build_node(
            file,
            layer_by_file[file.id],
            capability_by_file[file.id],
            flow_by_file[file.id],
            flow_role_by_file[file.id],
            description_by_file[file.id],
            relation_io[file.id],
        )
        for file in selected_files
    ]
    node_id_by_file = {item.id: _node_id(item.path) for item in selected_files}
    edges = _build_edges(resolved_edges, node_id_by_file, flow_by_file)

    limitations = [
        "구조도는 검증된 정적 관계와 저장소 메타데이터를 사용하며 "
        "런타임 동적 연결은 포함하지 않습니다.",
        "원시 import 관계는 가독성을 위해 핵심 책임 노드를 연결할 때만 표시합니다.",
    ]
    if len(candidates) > len(selected_files):
        limitations.append(
            f"가독성을 위해 후보 파일 {len(candidates)}개 중 "
            f"핵심 {len(selected_files)}개만 표시합니다."
        )
    if any(not flow_by_file[file.id] for file in selected_files):
        limitations.append(
            "기능 흐름에 포함되지 않은 구조 노드는 Project Map과 의미 관계를 근거로 선택했습니다."
        )
    if snapshot.parser_version != "semantic-ts-v2":
        limitations.append(
            f"현재 snapshot 분석 버전은 {snapshot.parser_version}입니다. "
            "semantic-ts-v2 재분석이 필요합니다."
        )

    repository = snapshot.repository
    return ArchitectureGraphResponse(
        repository_name=f"{repository.owner}/{repository.name}",
        snapshot_id=snapshot.id,
        commit_sha=snapshot.commit_sha or "",
        analysis_version=ARCHITECTURE_GRAPH_VERSION,
        summary=project_map.summary,
        groups=groups,
        nodes=nodes,
        edges=edges,
        limitations=limitations,
    )


def _build_group(
    layer: str,
    selected_files: list[FileRecord],
    layer_by_file: dict[str, str],
) -> ArchitectureGraphGroup:
    label, description = LAYER_LABELS[layer]
    evidence_file = next(item for item in selected_files if layer_by_file[item.id] == layer)
    return ArchitectureGraphGroup(
        id=f"group_{layer}",
        label=label,
        description=description,
        layer=layer,
        confidence="verified",
        evidence=[_evidence(evidence_file, description)],
    )


def _build_node(
    file: FileRecord,
    layer: str,
    capability_ids: set[str],
    flow_ids: set[str],
    flow_roles: list[str],
    descriptions: list[str],
    relation_io: tuple[set[str], set[str]],
) -> ArchitectureGraphNode:
    inputs, outputs = relation_io
    node_type = _node_type(file.path, layer)
    responsibility = _responsibility(file.path, node_type, flow_roles, descriptions)
    return ArchitectureGraphNode(
        id=_node_id(file.path),
        label=_human_label(file.path),
        responsibility=responsibility,
        node_type=node_type,
        group_id=f"group_{layer}",
        confidence="verified" if flow_ids or capability_ids else "inferred",
        inputs=sorted(inputs)[:4],
        outputs=sorted(outputs)[:4],
        capability_ids=sorted(capability_ids),
        feature_flow_ids=sorted(flow_ids),
        evidence=[_evidence(file, responsibility)],
    )


def _build_edges(
    resolved_edges: list[tuple[SymbolEdge, FileRecord, FileRecord | None]],
    node_id_by_file: dict[str, str],
    flow_by_file: dict[str, set[str]],
) -> list[ArchitectureGraphEdge]:
    aggregated: dict[tuple[str, str, str], list[tuple[SymbolEdge, FileRecord]]] = defaultdict(list)
    for edge, source, target in resolved_edges:
        if target is None or source.id not in node_id_by_file or target.id not in node_id_by_file:
            continue
        if source.id == target.id:
            continue
        signature = (source.id, target.id, edge.relation)
        aggregated[signature].append((edge, source))

    ranked = sorted(
        aggregated.items(),
        key=lambda item: (
            RELATION_PRIORITY.get(item[0][2], 99),
            -max(edge.confidence for edge, _ in item[1]),
            item[0],
        ),
    )
    output: list[ArchitectureGraphEdge] = []
    connected_pairs: set[tuple[str, str]] = set()
    for (source_id, target_id, relation), items in ranked:
        pair = (source_id, target_id)
        if relation == "IMPORTS" and pair in connected_pairs:
            continue
        edge, source_file = items[0]
        confidence = max(item.confidence for item, _ in items)
        shared_flows = flow_by_file[source_id] & flow_by_file[target_id]
        label = RELATION_LABELS.get(relation, relation.lower().replace("_", " "))
        start_line = min(
            max(1, source_file.line_count),
            max(1, edge.source_start_line or 1),
        )
        end_line = min(
            max(1, source_file.line_count),
            max(start_line, edge.source_end_line or start_line),
        )
        output.append(
            ArchitectureGraphEdge(
                id=_stable_id("edge", f"{source_id}|{target_id}|{relation}"),
                source=node_id_by_file[source_id],
                target=node_id_by_file[target_id],
                relation=relation,
                label=label,
                description=f"{source_file.path}가 {label} 관계로 다음 책임 영역에 연결됩니다.",
                confidence=_confidence(confidence),
                feature_flow_ids=sorted(shared_flows),
                evidence=[
                    ArchitectureGraphEvidence(
                        file_id=source_file.id,
                        path=source_file.path,
                        start_line=start_line,
                        end_line=end_line,
                        reason=f"{relation} 관계가 이 위치에서 확인됩니다.",
                    )
                ],
            )
        )
        connected_pairs.add(pair)
        if len(output) >= MAX_EDGES:
            break
    return output


def _relation_io(
    edges: list[tuple[SymbolEdge, FileRecord, FileRecord | None]],
    selected_ids: set[str],
) -> dict[str, tuple[set[str], set[str]]]:
    result: dict[str, tuple[set[str], set[str]]] = defaultdict(lambda: (set(), set()))
    for edge, source, target in edges:
        if source.id not in selected_ids or target is None or target.id not in selected_ids:
            continue
        label = RELATION_LABELS.get(edge.relation, edge.relation.lower())
        result[source.id][1].add(f"{label}: {_human_label(target.path)}")
        result[target.id][0].add(f"{label}: {_human_label(source.path)}")
    return result


def _target_file(
    edge: SymbolEdge,
    file_by_id: dict[str, FileRecord],
    file_by_path: dict[str, FileRecord],
    symbol_by_id: dict[str, Symbol],
) -> FileRecord | None:
    if edge.target_symbol_id and edge.target_symbol_id in symbol_by_id:
        return file_by_id.get(symbol_by_id[edge.target_symbol_id].file_id)
    if edge.target_path:
        return file_by_path.get(edge.target_path)
    return None


def _layer_for_path(path: str) -> str:
    lowered = path.casefold()
    name = PurePosixPath(path).name.casefold()
    parts = {part.casefold() for part in PurePosixPath(path).parts}
    if name in {"package.json", "pyproject.toml", "dockerfile"} or "config" in name:
        return "configuration"
    if (
        name in {"models.py", "model.py", "schemas.py", "schema.py"}
        or parts & {"models", "model", "schemas", "schema", "database", "db"}
    ):
        return "data"
    if (
        "/app/api/" in lowered
        or parts & {"server", "workers", "worker", "queue"}
        or name == "queue.py"
    ):
        return "server"
    if any(
        token in lowered for token in ("/components/", "/app/", "/pages/", "/hooks/")
    ) and not any(token in lowered for token in ("/api/", "route.")):
        return "client"
    if any(
        token in lowered for token in ("/services/", "/navigation/", "/analysis/", "/learning/")
    ):
        return "domain"
    if any(token in lowered for token in ("/types", "/schemas", "/lib/", "/utils")):
        return "shared"
    return "domain"


def _node_type(path: str, layer: str) -> str:
    lowered = path.casefold()
    if "worker" in lowered:
        return "worker"
    if "/api/" in lowered or PurePosixPath(path).stem == "route":
        return "api"
    if "model" in lowered or "schema" in lowered:
        return "data model"
    if "component" in lowered:
        return "component"
    if "hook" in lowered:
        return "hook"
    if layer == "configuration":
        return "configuration"
    return "module"


def _responsibility(path: str, node_type: str, roles: list[str], descriptions: list[str]) -> str:
    if descriptions:
        return _truncate(descriptions[0], 150)
    if roles:
        role = roles[0].replace("_", " ")
        return f"기능 흐름에서 {role} 단계를 담당합니다."
    return f"{_human_label(path)} {node_type}의 주요 책임과 경계를 나타냅니다."


def _human_label(path: str) -> str:
    pure = PurePosixPath(path)
    stem = pure.stem
    if stem.casefold() in {"index", "route", "page", "main", "__init__"} and pure.parent.name:
        stem = f"{pure.parent.name} {stem}"
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem).replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() for part in words.split()) or pure.name


def _is_noise_path(path: str) -> bool:
    parts = {part.casefold() for part in PurePosixPath(path).parts}
    name = PurePosixPath(path).name.casefold()
    return (
        bool(parts & EXCLUDED_SEGMENTS)
        or PurePosixPath(name).stem in {"test", "tests", "spec", "fixture"}
        or name.startswith(("test-", "test_", "spec-", "spec_"))
        or any(
            marker in name
            for marker in (
                ".test.",
                ".spec.",
                ".stories.",
                ".story.",
                ".fixture.",
                ".test-",
            )
        )
        or "/.github/" in f"/{path.casefold()}"
        or (name.startswith("generate_") and "pdf" in name)
    )


def _path_priority(path: str) -> int:
    lowered = path.casefold()
    if any(token in lowered for token in ("page.", "route.", "main.", "worker")):
        return 0
    if any(token in lowered for token in ("component", "service", "navigation", "model")):
        return 1
    return 2


def _evidence(file: FileRecord, reason: str) -> ArchitectureGraphEvidence:
    return ArchitectureGraphEvidence(
        file_id=file.id,
        path=file.path,
        start_line=1,
        end_line=1,
        reason=reason,
    )


def _node_id(path: str) -> str:
    return _stable_id("node", path)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _confidence(value: float) -> str:
    if value >= 0.85:
        return "verified"
    if value >= 0.5:
        return "inferred"
    return "unknown"


def _edge_sort_key(edge: SymbolEdge) -> tuple:
    return (
        RELATION_PRIORITY.get(edge.relation, 99),
        edge.source_file_id,
        edge.source_start_line or 0,
        edge.target_path or "",
        edge.id,
    )


def _truncate(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1].rstrip()}…"
