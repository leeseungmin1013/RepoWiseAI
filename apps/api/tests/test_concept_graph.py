from app.learning.concepts import (
    CONCEPT_REGISTRY,
    EDGE_REGISTRY,
    select_concept_gaps,
)


def graph_inputs():
    return (
        {item.id: item.display_name for item in CONCEPT_REGISTRY},
        [(item.source, item.target, item.rationale, item.confidence) for item in EDGE_REGISTRY],
    )


def test_gap_resolver_selects_only_missing_direct_prerequisite():
    names, edges = graph_inputs()

    gaps = select_concept_gaps(
        required_concept_ids=["async_await"],
        mastery={
            "function": {"score": 0.85, "confidence": 0.8},
            "async_await": {"score": 0.2, "confidence": 0.65},
        },
        concept_names=names,
        prerequisite_edges=edges,
    )

    assert [item.concept_id for item in gaps] == ["promise"]
    assert gaps[0].required_for == "async_await"
    assert gaps[0].depth == 1


def test_gap_resolver_falls_back_to_weak_target_when_prerequisites_are_ready():
    names, edges = graph_inputs()

    gaps = select_concept_gaps(
        required_concept_ids=["async_await"],
        mastery={
            "promise": {"score": 0.8, "confidence": 0.8},
            "async_await": {"score": 0.3, "confidence": 0.7},
        },
        concept_names=names,
        prerequisite_edges=edges,
    )

    assert [item.concept_id for item in gaps] == ["async_await"]
    assert gaps[0].depth == 0


def test_gap_resolver_caps_broad_react_prerequisites():
    names, edges = graph_inputs()

    gaps = select_concept_gaps(
        required_concept_ids=["react_component"],
        mastery={},
        concept_names=names,
        prerequisite_edges=edges,
        limit=3,
    )

    assert len(gaps) == 3
    assert all(item.required_for == "react_component" for item in gaps)
    assert len({item.concept_id for item in gaps}) == 3
