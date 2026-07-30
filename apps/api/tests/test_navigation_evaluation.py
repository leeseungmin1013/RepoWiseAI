from pathlib import Path

from app.evaluation.navigation import (
    NavigationGoldFixture,
    evaluate_navigation_output,
)
from app.schemas import (
    FeatureFlowDetail,
    FeatureFlowEvidence,
    FeatureFlowListResponse,
    FeatureFlowStep,
    FeatureFlowSummary,
)


def _evidence(path: str) -> FeatureFlowEvidence:
    return FeatureFlowEvidence(
        file_id=f"file:{path}",
        path=path,
        start_line=1,
        end_line=1,
        reason="gold evaluation evidence",
    )


def _step(
    flow_id: str, ordinal: int, relation: str, role: str, path: str
) -> FeatureFlowStep:
    return FeatureFlowStep(
        id=f"{flow_id}:step:{ordinal}",
        ordinal=ordinal,
        title=f"{relation} {role}",
        role=role,
        executes_when="gold fixture condition",
        input="input",
        output_or_side_effect="output",
        relation_type=relation,
        confidence="verified",
        evidence=[_evidence(path)],
    )


def _detail(flow_id: str, component_path: str, route_path: str) -> FeatureFlowDetail:
    step_specs = [
        ("TRIGGERS", "user_trigger", component_path),
        ("TRIGGERS", "client_handler", component_path),
        ("REQUESTS", "request", component_path),
        ("HANDLED_BY", "server_handler", route_path),
    ]
    steps = [
        _step(flow_id, ordinal, relation, role, path)
        for ordinal, (relation, role, path) in enumerate(step_specs, start=1)
    ]
    return FeatureFlowDetail(
        id=flow_id,
        title=flow_id,
        user_goal=flow_id,
        trigger="사용자 행동",
        outcome="서버 처리",
        normal_steps=steps,
        failure_steps=[],
        involved_areas=["화면", "서버"],
        confidence="verified",
        limitations=[],
    )


def _catalog(details: list[FeatureFlowDetail]) -> FeatureFlowListResponse:
    return FeatureFlowListResponse(
        repository_name="example/flow-demo",
        snapshot_id="snap-gold",
        commit_sha="commit-gold",
        analysis_version="feature-flow-v3",
        flows=[
            FeatureFlowSummary(
                id=detail.id,
                title=detail.title,
                user_goal=detail.user_goal,
                trigger=detail.trigger,
                outcome=detail.outcome,
                step_count=len(detail.normal_steps),
                involved_areas=detail.involved_areas,
                confidence=detail.confidence,
                evidence_coverage=1.0,
                entry_evidence=detail.normal_steps[0].evidence[0],
            )
            for detail in details
        ],
        limitations=[],
    )


def _fixture() -> NavigationGoldFixture:
    fixture_path = (
        Path(__file__).parents[1]
        / "evaluation"
        / "fixtures"
        / "navigation_gold_v1.json"
    )
    return NavigationGoldFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )


def test_gold_evaluation_measures_top_flow_recall_and_verified_precision() -> None:
    details = [
        _detail(
            "flow-ask",
            "src/components/AskForm.tsx",
            "src/app/api/ask/route.ts",
        ),
        _detail(
            "flow-save",
            "src/components/SaveButton.tsx",
            "src/app/api/save/route.ts",
        ),
    ]

    report = evaluate_navigation_output(
        _catalog(details), {detail.id: detail for detail in details}, _fixture()
    )

    assert report["feature_recall"] == 1.0
    assert report["step_recall"] == 1.0
    assert report["verified_precision"] == 1.0
    assert report["verified_prediction_count"] == 8
    assert report["false_verified_steps"] == []
    assert all(feature["matched"] for feature in report["features"])


def test_gold_evaluation_exposes_false_verified_steps() -> None:
    detail = _detail(
        "flow-ask",
        "src/components/AskForm.tsx",
        "src/app/api/ask/route.ts",
    )
    detail.normal_steps.append(
        _step(
            detail.id,
            5,
            "NAVIGATES_TO",
            "navigation",
            "src/components/Unexpected.tsx",
        )
    )

    report = evaluate_navigation_output(
        _catalog([detail]), {detail.id: detail}, _fixture()
    )

    assert report["feature_recall"] == 0.5
    assert report["verified_precision"] == 0.8
    assert report["false_verified_steps"] == [
        {
            "flow_id": "flow-ask",
            "relation_type": "NAVIGATES_TO",
            "role": "navigation",
            "path": "src/components/unexpected.tsx",
        }
    ]
