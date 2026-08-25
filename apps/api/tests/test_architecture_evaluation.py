from app.evaluation.architecture import (
    ArchitectureGoldFixture,
    GoldArchitectureEdge,
    GoldArchitectureFlow,
    GoldArchitectureNode,
    evaluate_architecture_output,
)
from app.navigation.architecture_graph import build_architecture_graph
from tests.test_architecture_graph import graph_inputs


def test_architecture_evaluator_scores_required_nodes_edges_and_flow_mapping() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(snapshot, files, symbols, edges, project_map, flows)
    fixture = ArchitectureGoldFixture(
        name="architecture-demo",
        repository="example/architecture-demo",
        nodes=[
            GoldArchitectureNode(id="client", evidence_paths=[files[0].path]),
            GoldArchitectureNode(id="server", evidence_paths=[files[1].path]),
            GoldArchitectureNode(id="data", evidence_paths=[files[2].path]),
        ],
        edges=[
            GoldArchitectureEdge(
                source_path=files[0].path,
                target_path=files[1].path,
                relation="REQUESTS",
            ),
            GoldArchitectureEdge(
                source_path=files[1].path,
                target_path=files[2].path,
                relation="WRITES",
            ),
        ],
        flows=[
            GoldArchitectureFlow(
                flow_id="submit-flow",
                evidence_paths=[file.path for file in files],
            )
        ],
    )

    report = evaluate_architecture_output(graph, fixture)

    assert report["architecture_node_recall"] == 1.0
    assert report["verified_node_precision"] == 1.0
    assert report["required_edge_recall"] == 1.0
    assert report["feature_mapping_coverage"] == 1.0
    assert report["noise_ratio"] == 0.0
    assert report["evidence_validity"] == 1.0
    assert report["graph_size_compliance"] == 1.0
    assert report["passed"] is True


def test_architecture_evaluator_matches_snapshot_scoped_flow_by_evidence() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(snapshot, files, symbols, edges, project_map, flows)
    fixture = ArchitectureGoldFixture(
        name="architecture-demo",
        repository="example/architecture-demo",
        nodes=[GoldArchitectureNode(id="client", evidence_paths=[files[0].path])],
        flows=[
            GoldArchitectureFlow(
                flow_id="flow-from-an-older-snapshot",
                evidence_paths=[file.path for file in files],
            )
        ],
    )

    report = evaluate_architecture_output(graph, fixture)

    assert report["feature_mapping_coverage"] == 1.0
