from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import REPOSITORY_ROOT
from app.core.db import SessionLocal
from app.models import FileRecord, Repository, RepositorySnapshot, Symbol, SymbolEdge
from app.navigation.feature_flow import (
    SEMANTIC_RELATIONS,
    build_feature_flow,
    build_feature_flows,
)
from app.schemas import FeatureFlowDetail, FeatureFlowListResponse, FeatureFlowStep


class GoldStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_type: str
    role: str
    path: str


class GoldFeature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    minimum_coverage: float = Field(default=1.0, ge=0, le=1)
    expected_steps: list[GoldStep] = Field(min_length=1)


class NavigationGoldFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    repository: str
    features: list[GoldFeature] = Field(min_length=1)
    thresholds: dict[str, float] = Field(default_factory=dict)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate navigation feature flows")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("apps/api/evaluation/fixtures/navigation_repowise_gold_v1.json"),
    )
    parser.add_argument("--snapshot-id")
    parser.add_argument("--fail-feature-recall", type=float)
    parser.add_argument("--fail-verified-precision", type=float)
    args = parser.parse_args()

    fixture_path = args.fixture
    if not fixture_path.is_absolute():
        fixture_path = REPOSITORY_ROOT / fixture_path
    fixture = NavigationGoldFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    report = evaluate_fixture(fixture, snapshot_id=args.snapshot_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    feature_threshold = (
        args.fail_feature_recall
        if args.fail_feature_recall is not None
        else fixture.thresholds.get("feature_recall", 0.0)
    )
    precision_threshold = (
        args.fail_verified_precision
        if args.fail_verified_precision is not None
        else fixture.thresholds.get("verified_precision", 0.0)
    )
    if (
        report["feature_recall"] < feature_threshold
        or report["verified_precision"] < precision_threshold
    ):
        raise SystemExit(1)


def evaluate_fixture(
    fixture: NavigationGoldFixture, *, snapshot_id: str | None = None
) -> dict[str, Any]:
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
                SymbolEdge.relation.in_(SEMANTIC_RELATIONS),
            )
        ).all()

    catalog = build_feature_flows(snapshot, files, symbols, edges)
    details = {
        summary.id: detail
        for summary in catalog.flows
        if (
            detail := build_feature_flow(
                snapshot, files, symbols, edges, summary.id
            )
        )
        is not None
    }
    report = evaluate_navigation_output(catalog, details, fixture)
    return {
        **report,
        "snapshot_id": snapshot.id,
        "commit_sha": snapshot.commit_sha or "",
        "analysis_version": catalog.analysis_version,
    }


def evaluate_navigation_output(
    catalog: FeatureFlowListResponse,
    details: dict[str, FeatureFlowDetail],
    fixture: NavigationGoldFixture,
) -> dict[str, Any]:
    actual = [details[summary.id] for summary in catalog.flows if summary.id in details]
    gold_signatures = [
        {_gold_step_signature(step) for step in feature.expected_steps}
        for feature in fixture.features
    ]
    actual_signatures = [
        {_actual_step_signature(step) for step in detail.normal_steps}
        for detail in actual
    ]

    scored_pairs: list[tuple[float, int, int, int]] = []
    for gold_index, expected in enumerate(gold_signatures):
        for actual_index, predicted in enumerate(actual_signatures):
            overlap = len(expected & predicted)
            coverage = overlap / len(expected)
            scored_pairs.append((coverage, overlap, gold_index, actual_index))
    scored_pairs.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))

    pairs: dict[int, int] = {}
    used_actual: set[int] = set()
    for _coverage, overlap, gold_index, actual_index in scored_pairs:
        if not overlap or gold_index in pairs or actual_index in used_actual:
            continue
        pairs[gold_index] = actual_index
        used_actual.add(actual_index)

    feature_results = []
    matched_features = 0
    matched_steps = 0
    total_expected_steps = sum(len(signatures) for signatures in gold_signatures)
    actual_to_gold = {actual_index: gold_index for gold_index, actual_index in pairs.items()}
    for gold_index, feature in enumerate(fixture.features):
        actual_index = pairs.get(gold_index)
        overlap = (
            len(gold_signatures[gold_index] & actual_signatures[actual_index])
            if actual_index is not None
            else 0
        )
        coverage = overlap / len(gold_signatures[gold_index])
        matched = actual_index is not None and coverage >= feature.minimum_coverage
        matched_features += int(matched)
        matched_steps += overlap
        feature_results.append(
            {
                "id": feature.id,
                "name": feature.name,
                "matched": matched,
                "step_coverage": round(coverage, 4),
                "matched_flow_id": (
                    actual[actual_index].id if actual_index is not None else None
                ),
            }
        )

    verified_predictions = 0
    correct_verified_predictions = 0
    false_verified_steps = []
    for actual_index, detail in enumerate(actual):
        paired_gold = actual_to_gold.get(actual_index)
        expected = gold_signatures[paired_gold] if paired_gold is not None else set()
        for step in detail.normal_steps:
            if step.confidence != "verified":
                continue
            verified_predictions += 1
            signature = _actual_step_signature(step)
            if signature in expected:
                correct_verified_predictions += 1
            else:
                false_verified_steps.append(
                    {
                        "flow_id": detail.id,
                        "relation_type": step.relation_type,
                        "role": step.role,
                        "path": signature[2],
                    }
                )

    feature_recall = matched_features / len(fixture.features)
    step_recall = (
        matched_steps / total_expected_steps if total_expected_steps else 0.0
    )
    verified_precision = (
        correct_verified_predictions / verified_predictions
        if verified_predictions
        else 0.0
    )
    return {
        "fixture": fixture.name,
        "repository": fixture.repository,
        "expected_feature_count": len(fixture.features),
        "actual_top_flow_count": len(actual),
        "feature_recall": round(feature_recall, 4),
        "step_recall": round(step_recall, 4),
        "verified_precision": round(verified_precision, 4),
        "verified_prediction_count": verified_predictions,
        "false_verified_steps": false_verified_steps,
        "features": feature_results,
    }


def _load_snapshot(
    db: Any, repository_name: str, snapshot_id: str | None
) -> RepositorySnapshot:
    statement = (
        select(RepositorySnapshot)
        .join(Repository, Repository.id == RepositorySnapshot.repository_id)
        .where(RepositorySnapshot.status == "ready")
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
        raise RuntimeError("No ready snapshot matched the navigation gold fixture")
    return snapshot


def _gold_step_signature(step: GoldStep) -> tuple[str, str, str]:
    return step.relation_type, step.role, _normalize_path(step.path)


def _actual_step_signature(step: FeatureFlowStep) -> tuple[str, str, str]:
    path = step.evidence[0].path if step.evidence else ""
    return step.relation_type, step.role, _normalize_path(path)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().casefold()


if __name__ == "__main__":
    main()
