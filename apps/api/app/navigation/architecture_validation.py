from __future__ import annotations

from dataclasses import dataclass

from app.models import FileRecord
from app.schemas import ArchitectureGraphResponse, FeatureFlowDetail, ProjectMapResponse


@dataclass(frozen=True)
class ArchitectureValidationResult:
    valid: bool
    issues: tuple[str, ...]
    flow_mapping_coverage: dict[str, float]


def validate_architecture_graph(
    graph: ArchitectureGraphResponse,
    *,
    files: list[FileRecord],
    project_map: ProjectMapResponse,
    feature_flows: list[FeatureFlowDetail],
) -> ArchitectureValidationResult:
    issues: list[str] = []
    file_by_id = {item.id: item for item in files}
    group_ids = [item.id for item in graph.groups]
    node_ids = [item.id for item in graph.nodes]
    capability_ids = {item.id for item in project_map.capabilities}
    flow_ids = {item.id for item in feature_flows}

    if len(group_ids) != len(set(group_ids)):
        issues.append("duplicate group id")
    if len(node_ids) != len(set(node_ids)):
        issues.append("duplicate node id")
    if len(graph.groups) > 8 or len(graph.nodes) > 34 or len(graph.edges) > 48:
        issues.append("graph size limit exceeded")

    known_groups = set(group_ids)
    known_nodes = set(node_ids)
    for node in graph.nodes:
        if node.group_id and node.group_id not in known_groups:
            issues.append(f"node {node.id} references an unknown group")
        if not set(node.capability_ids) <= capability_ids:
            issues.append(f"node {node.id} references an unknown capability")
        if not set(node.feature_flow_ids) <= flow_ids:
            issues.append(f"node {node.id} references an unknown feature flow")
        _validate_evidence(node.id, node.evidence, file_by_id, issues)

    seen_edges: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        signature = (edge.source, edge.target, edge.relation)
        if edge.source not in known_nodes or edge.target not in known_nodes:
            issues.append(f"edge {edge.id} references an unknown node")
        if edge.source == edge.target:
            issues.append(f"edge {edge.id} is a self edge")
        if signature in seen_edges:
            issues.append(f"edge {edge.id} duplicates a relationship")
        seen_edges.add(signature)
        if not set(edge.feature_flow_ids) <= flow_ids:
            issues.append(f"edge {edge.id} references an unknown feature flow")
        _validate_evidence(edge.id, edge.evidence, file_by_id, issues)

    flow_mapping_coverage: dict[str, float] = {}
    node_flow_ids = {flow_id for node in graph.nodes for flow_id in node.feature_flow_ids}
    for flow in feature_flows:
        step_files = {
            evidence.file_id
            for step in [*flow.normal_steps, *flow.failure_steps]
            for evidence in step.evidence
        }
        mapped_files = {
            evidence.file_id
            for node in graph.nodes
            if flow.id in node.feature_flow_ids
            for evidence in node.evidence
        }
        coverage = len(step_files & mapped_files) / len(step_files) if step_files else 0.0
        flow_mapping_coverage[flow.id] = round(coverage, 4)
        if flow.id not in node_flow_ids:
            issues.append(f"feature flow {flow.id} has no mapped node")

    return ArchitectureValidationResult(
        valid=not issues,
        issues=tuple(issues),
        flow_mapping_coverage=flow_mapping_coverage,
    )


def _validate_evidence(
    owner_id: str,
    evidence_items: list,
    file_by_id: dict[str, FileRecord],
    issues: list[str],
) -> None:
    for evidence in evidence_items:
        file = file_by_id.get(evidence.file_id)
        if file is None or file.path != evidence.path:
            issues.append(f"{owner_id} has invalid evidence path")
            continue
        if evidence.start_line > evidence.end_line or evidence.end_line > max(1, file.line_count):
            issues.append(f"{owner_id} has invalid evidence lines")
