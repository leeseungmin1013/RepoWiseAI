from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import SessionLocal
from app.models import FileRecord, Repository, RepositorySnapshot, Symbol, SymbolEdge
from app.navigation.architecture_graph import IMPORTANT_RELATIONS, build_architecture_graph
from app.navigation.feature_flow import build_feature_flow, build_feature_flows
from app.navigation.project_map import build_project_map
from app.schemas import ArchitectureGraphResponse


class GoldArchitectureNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    evidence_paths: list[str] = Field(min_length=1)


class GoldArchitectureEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    target_path: str
    relation: str


class GoldArchitectureFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    evidence_paths: list[str] = Field(min_length=1)


class ArchitectureGoldFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    repository: str
    nodes: list[GoldArchitectureNode] = Field(min_length=1)
    edges: list[GoldArchitectureEdge] = Field(default_factory=list)
    flows: list[GoldArchitectureFlow] = Field(default_factory=list)
    noise_paths: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)


def evaluate_architecture_output(
    graph: ArchitectureGraphResponse,
    fixture: ArchitectureGoldFixture,
) -> dict[str, float | int | str | bool]:
    node_paths = {_normalize(evidence.path) for node in graph.nodes for evidence in node.evidence}
    required_node_sets = [
        {_normalize(path) for path in node.evidence_paths} for node in fixture.nodes
    ]
    required_node_paths = set().union(*required_node_sets)
    matched_nodes = sum(bool(paths & node_paths) for paths in required_node_sets)

    node_by_id = {node.id: node for node in graph.nodes}
    actual_edges = set()
    for edge in graph.edges:
        source = node_by_id.get(edge.source)
        target = node_by_id.get(edge.target)
        if source is None or target is None:
            continue
        source_paths = {_normalize(item.path) for item in source.evidence}
        target_paths = {_normalize(item.path) for item in target.evidence}
        actual_edges.update(
            (source_path, target_path, edge.relation)
            for source_path in source_paths
            for target_path in target_paths
        )
    expected_edges = {
        (_normalize(edge.source_path), _normalize(edge.target_path), edge.relation)
        for edge in fixture.edges
    }
    matched_edges = len(actual_edges & expected_edges)

    verified_nodes = [node for node in graph.nodes if node.confidence == "verified"]
    correct_verified = sum(
        any(_normalize(evidence.path) in required_node_paths for evidence in node.evidence)
        for node in verified_nodes
    )
    noise_paths = {_normalize(path) for path in fixture.noise_paths}
    noise_nodes = sum(
        any(_normalize(evidence.path) in noise_paths for evidence in node.evidence)
        for node in graph.nodes
    )
    file_ranges = {
        _normalize(path): line_count
        for path, line_count in _evidence_file_ranges(graph).items()
    }
    all_evidence = [
        evidence
        for item in [*graph.groups, *graph.nodes, *graph.edges]
        for evidence in item.evidence
    ]
    valid_evidence = sum(
        _normalize(evidence.path) in file_ranges
        and 1
        <= evidence.start_line
        <= evidence.end_line
        <= file_ranges[_normalize(evidence.path)]
        for evidence in all_evidence
    )

    expected_flow_paths = {
        item.flow_id: {_normalize(path) for path in item.evidence_paths} for item in fixture.flows
    }
    mapped = 0
    total = 0
    for flow_id, paths in expected_flow_paths.items():
        total += len(paths)
        actual_paths = {
            _normalize(evidence.path)
            for node in graph.nodes
            if flow_id in node.feature_flow_ids
            for evidence in node.evidence
        }
        mapped += len(paths & actual_paths)

    report: dict[str, float | int | str | bool] = {
        "fixture": fixture.name,
        "repository": fixture.repository,
        "architecture_node_recall": round(matched_nodes / len(required_node_sets), 4),
        "verified_node_precision": round(
            correct_verified / len(verified_nodes) if verified_nodes else 0.0,
            4,
        ),
        "required_edge_recall": round(
            matched_edges / len(expected_edges) if expected_edges else 1.0,
            4,
        ),
        "feature_mapping_coverage": round(mapped / total if total else 1.0, 4),
        "noise_ratio": round(noise_nodes / len(graph.nodes) if graph.nodes else 0.0, 4),
        "evidence_validity": round(
            valid_evidence / len(all_evidence) if all_evidence else 1.0,
            4,
        ),
        "graph_size_compliance": float(
            len(graph.groups) <= 8 and len(graph.nodes) <= 34 and len(graph.edges) <= 48
        ),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
    }
    report["passed"] = all(
        (
            float(report.get(metric, 0.0)) <= threshold
            if metric == "noise_ratio"
            else float(report.get(metric, 0.0)) >= threshold
        )
        for metric, threshold in fixture.thresholds.items()
    )
    return report


def _normalize(path: str) -> str:
    return path.replace("\\", "/").strip().casefold()


def _evidence_file_ranges(graph: ArchitectureGraphResponse) -> dict[str, int]:
    ranges: dict[str, int] = {}
    for item in [*graph.groups, *graph.nodes, *graph.edges]:
        for evidence in item.evidence:
            ranges[evidence.path] = max(
                ranges.get(evidence.path, 0),
                evidence.end_line,
            )
    return ranges


def evaluate_fixture(
    fixture: ArchitectureGoldFixture,
    *,
    snapshot_id: str | None = None,
) -> dict[str, float | int | str | bool]:
    with SessionLocal() as db:
        snapshot = _load_snapshot(db, fixture.repository, snapshot_id)
        files = db.scalars(
            select(FileRecord).where(FileRecord.snapshot_id == snapshot.id)
        ).all()
        symbols = db.scalars(
            select(Symbol).where(Symbol.snapshot_id == snapshot.id)
        ).all()
        edges = db.scalars(
            select(SymbolEdge).where(
                SymbolEdge.snapshot_id == snapshot.id,
                SymbolEdge.relation.in_(IMPORTANT_RELATIONS),
            )
        ).all()
        file_line_counts = {file.path: file.line_count for file in files}
        project_map = build_project_map(
            snapshot,
            files,
            [edge for edge in edges if edge.relation == "IMPORTS"],
        )
        catalog = build_feature_flows(snapshot, files, symbols, edges)
        flows = [
            detail
            for summary in catalog.flows
            if (
                detail := build_feature_flow(
                    snapshot, files, symbols, edges, summary.id
                )
            )
            is not None
        ]
        graph = build_architecture_graph(
            snapshot, files, symbols, edges, project_map, flows
        )
    report = evaluate_architecture_output(graph, fixture)
    evidence = [
        item
        for candidate in [*graph.groups, *graph.nodes, *graph.edges]
        for item in candidate.evidence
    ]
    valid = sum(
        item.path in file_line_counts
        and 1
        <= item.start_line
        <= item.end_line
        <= file_line_counts[item.path]
        for item in evidence
    )
    report["evidence_validity"] = round(
        valid / len(evidence) if evidence else 1.0, 4
    )
    report["snapshot_id"] = snapshot.id
    report["commit_sha"] = snapshot.commit_sha or ""
    report["passed"] = all(
        (
            float(report.get(metric, 0.0)) <= threshold
            if metric == "noise_ratio"
            else float(report.get(metric, 0.0)) >= threshold
        )
        for metric, threshold in fixture.thresholds.items()
    )
    return report


def _load_snapshot(
    db: Any,
    repository_name: str,
    snapshot_id: str | None,
) -> RepositorySnapshot:
    statement = (
        select(RepositorySnapshot)
        .join(Repository, Repository.id == RepositorySnapshot.repository_id)
        .where(
            RepositorySnapshot.status == "ready",
            RepositorySnapshot.parser_version == "semantic-ts-v2",
        )
        .options(selectinload(RepositorySnapshot.repository))
    )
    if snapshot_id:
        statement = statement.where(RepositorySnapshot.id == snapshot_id)
    else:
        owner, name = repository_name.split("/", 1)
        statement = statement.where(Repository.owner == owner, Repository.name == name)
    snapshot = db.scalar(
        statement.order_by(RepositorySnapshot.created_at.desc()).limit(1)
    )
    if snapshot is None:
        raise RuntimeError("No semantic-ts-v2 snapshot matched the architecture fixture")
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an architecture graph fixture")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("apps/api/evaluation/fixtures/architecture_gold_v1.json"),
    )
    parser.add_argument("--snapshot-id")
    args = parser.parse_args()
    fixture = ArchitectureGoldFixture.model_validate_json(
        args.fixture.read_text(encoding="utf-8")
    )
    print(
        json.dumps(
            evaluate_fixture(fixture, snapshot_id=args.snapshot_id),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
