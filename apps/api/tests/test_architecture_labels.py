from test_architecture_graph import graph_inputs

from app.navigation.architecture_graph import build_architecture_graph
from app.navigation.architecture_labels import (
    ArchitectureLabelSuggestion,
    apply_architecture_label_suggestions,
)


def test_label_suggestions_can_only_update_existing_nodes() -> None:
    snapshot, files, symbols, edges, project_map, flows = graph_inputs()
    graph = build_architecture_graph(
        snapshot, files, symbols, edges, project_map, flows
    )
    target = graph.nodes[0]

    enhanced = apply_architecture_label_suggestions(
        graph,
        [
            ArchitectureLabelSuggestion(
                node_id=target.id,
                label="주문 화면",
                responsibility="사용자 주문 제출과 결과 표시를 담당합니다.",
            ),
            ArchitectureLabelSuggestion(
                node_id="node_not_allowed",
                label="Invented",
                responsibility="Must be ignored.",
            ),
        ],
    )

    assert len(enhanced.nodes) == len(graph.nodes)
    assert len(enhanced.edges) == len(graph.edges)
    assert enhanced.nodes[0].label == "주문 화면"
    assert enhanced.nodes[0].evidence == target.evidence
    assert {node.id for node in enhanced.nodes} == {node.id for node in graph.nodes}
    assert any("노드와 관계를 추가하지 않았습니다" in item for item in enhanced.limitations)
