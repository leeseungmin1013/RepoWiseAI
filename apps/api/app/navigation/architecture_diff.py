from __future__ import annotations

from app.schemas import (
    ArchitectureGraphDiffEdge,
    ArchitectureGraphDiffNode,
    ArchitectureGraphDiffResponse,
    ArchitectureGraphResponse,
)


def diff_architecture_graphs(
    base: ArchitectureGraphResponse,
    target: ArchitectureGraphResponse,
) -> ArchitectureGraphDiffResponse:
    base_nodes = {_node_path(node): node for node in base.nodes}
    target_nodes = {_node_path(node): node for node in target.nodes}
    node_diffs: list[ArchitectureGraphDiffNode] = []
    for path in sorted(base_nodes.keys() | target_nodes.keys()):
        before = base_nodes.get(path)
        after = target_nodes.get(path)
        if before is None and after is not None:
            node_diffs.append(
                ArchitectureGraphDiffNode(
                    path=path,
                    status="added",
                    after_label=after.label,
                    after_responsibility=after.responsibility,
                )
            )
        elif before is not None and after is None:
            node_diffs.append(
                ArchitectureGraphDiffNode(
                    path=path,
                    status="removed",
                    before_label=before.label,
                    before_responsibility=before.responsibility,
                )
            )
        elif before is not None and after is not None and (
            before.label != after.label
            or before.responsibility != after.responsibility
            or before.group_id != after.group_id
            or before.node_type != after.node_type
        ):
            node_diffs.append(
                ArchitectureGraphDiffNode(
                    path=path,
                    status="changed",
                    before_label=before.label,
                    after_label=after.label,
                    before_responsibility=before.responsibility,
                    after_responsibility=after.responsibility,
                )
            )

    base_edges = _edge_signatures(base)
    target_edges = _edge_signatures(target)
    edge_diffs = [
        ArchitectureGraphDiffEdge(
            source_path=source,
            target_path=destination,
            relation=relation,
            status="removed",
        )
        for source, destination, relation in sorted(base_edges - target_edges)
    ]
    edge_diffs.extend(
        ArchitectureGraphDiffEdge(
            source_path=source,
            target_path=destination,
            relation=relation,
            status="added",
        )
        for source, destination, relation in sorted(target_edges - base_edges)
    )

    summary = {
        "nodes_added": sum(item.status == "added" for item in node_diffs),
        "nodes_removed": sum(item.status == "removed" for item in node_diffs),
        "nodes_changed": sum(item.status == "changed" for item in node_diffs),
        "edges_added": sum(item.status == "added" for item in edge_diffs),
        "edges_removed": sum(item.status == "removed" for item in edge_diffs),
    }
    return ArchitectureGraphDiffResponse(
        repository_name=target.repository_name,
        base_snapshot_id=base.snapshot_id,
        target_snapshot_id=target.snapshot_id,
        base_commit_sha=base.commit_sha,
        target_commit_sha=target.commit_sha,
        nodes=node_diffs,
        edges=edge_diffs,
        summary=summary,
    )


def architecture_graph_to_mermaid(graph: ArchitectureGraphResponse) -> str:
    lines = [
        "flowchart LR",
        f"%% {graph.repository_name} @ {graph.commit_sha}",
    ]
    nodes_by_group = {
        group.id: [node for node in graph.nodes if node.group_id == group.id]
        for group in graph.groups
    }
    for group in graph.groups:
        lines.append(f'  subgraph {group.id}["{_escape(group.label)}"]')
        for node in nodes_by_group[group.id]:
            lines.append(
                f'    {node.id}["{_escape(node.label)}<br/>{_escape(node.responsibility)}"]'
            )
        lines.append("  end")
    for node in graph.nodes:
        if node.group_id is None:
            lines.append(
                f'  {node.id}["{_escape(node.label)}<br/>{_escape(node.responsibility)}"]'
            )
    for edge in graph.edges:
        lines.append(
            f'  {edge.source} -->|"{_escape(edge.label)}"| {edge.target}'
        )
    return "\n".join(lines) + "\n"


def _node_path(node) -> str:
    return node.evidence[0].path.replace("\\", "/").casefold()


def _edge_signatures(graph: ArchitectureGraphResponse) -> set[tuple[str, str, str]]:
    node_paths = {node.id: _node_path(node) for node in graph.nodes}
    return {
        (node_paths[edge.source], node_paths[edge.target], edge.relation)
        for edge in graph.edges
        if edge.source in node_paths and edge.target in node_paths
    }


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", " ")
    )
