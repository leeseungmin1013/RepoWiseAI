from test_architecture_graph import graph_inputs

from app.navigation.architecture_diff import (
    architecture_graph_to_mermaid,
    diff_architecture_graphs,
)
from app.navigation.architecture_graph import build_architecture_graph


def test_architecture_diff_reports_node_and_edge_changes() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    base = build_architecture_graph(
        snapshot, files, symbols, edges, project_map, flows
    )
    target = base.model_copy(
        update={
            "snapshot_id": "snap_target",
            "commit_sha": "target-commit",
            "nodes": [
                base.nodes[0].model_copy(
                    update={"responsibility": "Updated responsibility"}
                ),
                *base.nodes[1:-1],
            ],
            "edges": base.edges[:-1],
        }
    )

    result = diff_architecture_graphs(base, target)

    assert result.summary["nodes_changed"] == 1
    assert result.summary["nodes_removed"] == 1
    assert result.summary["edges_removed"] >= 1
    assert result.base_snapshot_id == base.snapshot_id
    assert result.target_snapshot_id == "snap_target"


def test_mermaid_export_contains_groups_nodes_and_relations() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(
        snapshot, files, symbols, edges, project_map, flows
    )

    mermaid = architecture_graph_to_mermaid(graph)

    assert mermaid.startswith("flowchart LR\n")
    assert "subgraph group_client" in mermaid
    assert "-->" in mermaid
    assert graph.nodes[0].label in mermaid
