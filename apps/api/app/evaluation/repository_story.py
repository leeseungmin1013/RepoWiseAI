from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.db import SessionLocal
from app.evaluation.architecture import _load_snapshot, _normalize
from app.models import FileRecord, Symbol, SymbolEdge
from app.navigation.architecture_graph import IMPORTANT_RELATIONS, build_architecture_graph
from app.navigation.feature_flow import build_feature_flow, build_feature_flows
from app.navigation.project_map import build_project_map
from app.navigation.repository_story import build_repository_story
from app.schemas import RepositoryStoryResponse


class GoldRepositoryRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    evidence_paths: list[str] = Field(min_length=1)


class RepositoryStoryGoldFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    repository: str
    roles: list[GoldRepositoryRole] = Field(min_length=1)
    expected_feature_ids: list[str] = Field(default_factory=list)
    thresholds: dict[str, float] = Field(default_factory=dict)


GENERIC_MARKERS = (
    "주요 책임과 경계를 나타냅니다",
    "module의 주요 책임",
    "api의 주요 책임",
)


def evaluate_repository_story_output(
    story: RepositoryStoryResponse,
    fixture: RepositoryStoryGoldFixture,
    *,
    file_line_counts: dict[str, int] | None = None,
) -> dict[str, float | int | str | bool]:
    expected_roles = {item.id: item for item in fixture.roles}
    actual_roles = {item.id: item for item in story.roles}
    matched_roles = len(expected_roles.keys() & actual_roles.keys())
    expected_paths = {
        _normalize(path)
        for role in fixture.roles
        for path in role.evidence_paths
    }

    verified_roles = [role for role in story.roles if role.confidence == "verified"]
    correct_verified = sum(
        bool(
            expected_paths
            & {_normalize(evidence.path) for evidence in role.evidence}
        )
        for role in verified_roles
    )

    required_fields = (
        "display_name",
        "role_summary",
        "why_it_exists",
        "contribution_to_goal",
    )
    narrative_total = len(story.roles) * len(required_fields)
    narrative_present = sum(
        bool(getattr(role, field_name).strip())
        for role in story.roles
        for field_name in required_fields
    )
    generic_roles = sum(
        any(
            marker in " ".join(
                (
                    role.role_summary,
                    role.why_it_exists,
                    role.contribution_to_goal,
                )
            ).casefold()
            for marker in GENERIC_MARKERS
        )
        for role in story.roles
    )

    evidence = [
        *story.purpose.evidence,
        *(item for role in story.roles for item in role.evidence),
        *(item for connection in story.connections for item in connection.evidence),
    ]
    if file_line_counts is None:
        evidence_validity = float(
            all(
                item.file_id
                and item.path
                and 1 <= item.start_line <= item.end_line
                for item in evidence
            )
        )
    else:
        normalized_ranges = {
            _normalize(path): line_count for path, line_count in file_line_counts.items()
        }
        valid_evidence = sum(
            _normalize(item.path) in normalized_ranges
            and 1
            <= item.start_line
            <= item.end_line
            <= normalized_ranges[_normalize(item.path)]
            for item in evidence
        )
        evidence_validity = valid_evidence / len(evidence) if evidence else 0.0

    mapped_feature_ids = {
        feature_id for role in story.roles for feature_id in role.feature_flow_ids
    }
    expected_feature_ids = set(fixture.expected_feature_ids)
    feature_mapping_coverage = (
        len(expected_feature_ids & mapped_feature_ids) / len(expected_feature_ids)
        if expected_feature_ids
        else 1.0
    )
    role_evidence_coverage = sum(bool(role.evidence) for role in story.roles) / len(
        story.roles
    )
    report: dict[str, float | int | str | bool] = {
        "fixture": fixture.name,
        "repository": fixture.repository,
        "role_recall": round(
            matched_roles / len(expected_roles) if expected_roles else 1.0,
            4,
        ),
        "verified_role_precision": round(
            correct_verified / len(verified_roles) if verified_roles else 0.0,
            4,
        ),
        "purpose_evidence_validity": round(evidence_validity, 4),
        "role_evidence_validity": round(evidence_validity, 4),
        "role_evidence_coverage": round(role_evidence_coverage, 4),
        "feature_to_role_mapping_coverage": round(feature_mapping_coverage, 4),
        "narrative_field_coverage": round(
            narrative_present / narrative_total if narrative_total else 0.0,
            4,
        ),
        "generic_responsibility_ratio": round(
            generic_roles / len(story.roles) if story.roles else 1.0,
            4,
        ),
        "overview_role_count_compliance": float(3 <= len(story.roles) <= 12),
        "role_count": len(story.roles),
        "connection_count": len(story.connections),
    }
    report["passed"] = _passes_thresholds(report, fixture.thresholds)
    return report


def evaluate_fixture(
    fixture: RepositoryStoryGoldFixture,
    *,
    snapshot_id: str | None = None,
) -> dict[str, float | int | str | bool]:
    with SessionLocal() as db:
        snapshot = _load_snapshot(db, fixture.repository, snapshot_id)
        files = list(
            db.scalars(
                select(FileRecord).where(FileRecord.snapshot_id == snapshot.id)
            ).all()
        )
        symbols = list(
            db.scalars(select(Symbol).where(Symbol.snapshot_id == snapshot.id)).all()
        )
        edges = list(
            db.scalars(
                select(SymbolEdge).where(
                    SymbolEdge.snapshot_id == snapshot.id,
                    SymbolEdge.relation.in_(IMPORTANT_RELATIONS),
                )
            ).all()
        )
        project_map = build_project_map(
            snapshot,
            files,
            [edge for edge in edges if edge.relation == "IMPORTS"],
        )
        catalog = build_feature_flows(snapshot, files, symbols, edges)
        flow_details = [
            detail
            for summary in catalog.flows
            if (
                detail := build_feature_flow(
                    snapshot,
                    files,
                    symbols,
                    edges,
                    summary.id,
                )
            )
            is not None
        ]
        graph = build_architecture_graph(
            snapshot,
            files,
            symbols,
            edges,
            project_map,
            flow_details,
        )
        story = build_repository_story(snapshot, project_map, graph, catalog.flows)
        file_line_counts = {file.path: file.line_count for file in files}

    report = evaluate_repository_story_output(
        story,
        fixture,
        file_line_counts=file_line_counts,
    )
    report["snapshot_id"] = snapshot.id
    report["commit_sha"] = snapshot.commit_sha or ""
    report["passed"] = _passes_thresholds(report, fixture.thresholds)
    return report


def _passes_thresholds(
    report: dict[str, float | int | str | bool],
    thresholds: dict[str, float],
) -> bool:
    lower_is_better = {"generic_responsibility_ratio"}
    return all(
        (
            float(report.get(metric, 1.0)) <= threshold
            if metric in lower_is_better
            else float(report.get(metric, 0.0)) >= threshold
        )
        for metric, threshold in thresholds.items()
    )


def _fixture_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("repository_story_*_gold_v1.json"))
    return [path]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Repository Story fixtures")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("apps/api/evaluation/fixtures"),
    )
    parser.add_argument("--snapshot-id")
    args = parser.parse_args()
    reports: list[dict[str, Any]] = []
    for path in _fixture_paths(args.fixture):
        fixture = RepositoryStoryGoldFixture.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        reports.append(evaluate_fixture(fixture, snapshot_id=args.snapshot_id))
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    if not reports or not all(bool(report["passed"]) for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
