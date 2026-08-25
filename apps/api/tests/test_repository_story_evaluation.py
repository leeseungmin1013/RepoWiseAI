from app.evaluation.repository_story import (
    GoldRepositoryRole,
    RepositoryStoryGoldFixture,
    evaluate_repository_story_output,
)
from app.navigation.architecture_graph import build_architecture_graph
from app.navigation.repository_story import build_repository_story
from app.schemas import FeatureFlowSummary
from tests.test_architecture_graph import graph_inputs


def test_repository_story_evaluator_scores_roles_narrative_and_evidence() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(snapshot, files, symbols, edges, project_map, flows)
    story = build_repository_story(
        snapshot,
        project_map,
        graph,
        [
            FeatureFlowSummary(
                id=flow.id,
                title=flow.title,
                user_goal=flow.user_goal,
                trigger=flow.trigger,
                outcome=flow.outcome,
                step_count=len(flow.normal_steps),
                involved_areas=flow.involved_areas,
                confidence=flow.confidence,
                evidence_coverage=1.0,
                entry_evidence=flow.normal_steps[0].evidence[0],
            )
            for flow in flows
        ],
    )
    fixture = RepositoryStoryGoldFixture(
        name="story-demo",
        repository="example/architecture-demo",
        roles=[
            GoldRepositoryRole(
                id=role.id,
                evidence_paths=[evidence.path for evidence in role.evidence],
            )
            for role in story.roles
        ],
        expected_feature_ids=[flow.id for flow in flows],
        thresholds={
            "role_recall": 1.0,
            "verified_role_precision": 1.0,
            "purpose_evidence_validity": 1.0,
            "role_evidence_coverage": 1.0,
            "feature_to_role_mapping_coverage": 1.0,
            "narrative_field_coverage": 1.0,
            "generic_responsibility_ratio": 0.0,
        },
    )

    report = evaluate_repository_story_output(story, fixture)

    assert report["role_recall"] == 1.0
    assert report["verified_role_precision"] == 1.0
    assert report["purpose_evidence_validity"] == 1.0
    assert report["role_evidence_coverage"] == 1.0
    assert report["feature_to_role_mapping_coverage"] == 1.0
    assert report["narrative_field_coverage"] == 1.0
    assert report["generic_responsibility_ratio"] == 0.0
    assert report["passed"] is True


def test_repository_story_evaluator_counts_snapshot_scoped_feature_mappings() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(snapshot, files, symbols, edges, project_map, flows)
    story = build_repository_story(snapshot, project_map, graph, [])
    fixture = RepositoryStoryGoldFixture(
        name="story-demo",
        repository="example/architecture-demo",
        roles=[
            GoldRepositoryRole(id=role.id, evidence_paths=[role.evidence[0].path])
            for role in story.roles
        ],
        expected_feature_ids=["flow-from-an-older-snapshot"],
    )

    assert (
        evaluate_repository_story_output(story, fixture)["feature_to_role_mapping_coverage"] == 1.0
    )
