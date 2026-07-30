import type { ArchitectureGraph } from "@/lib/api";

export function architectureGraphToMermaid(graph: ArchitectureGraph): string {
  const lines = [
    "flowchart LR",
    `%% ${graph.repository_name} @ ${graph.commit_sha}`,
  ];
  for (const group of graph.groups) {
    lines.push(`  subgraph ${group.id}["${escapeMermaid(group.label)}"]`);
    for (const node of graph.nodes.filter((item) => item.group_id === group.id)) {
      lines.push(
        `    ${node.id}["${escapeMermaid(node.label)}<br/>${escapeMermaid(
          node.responsibility,
        )}"]`,
      );
    }
    lines.push("  end");
  }
  for (const node of graph.nodes.filter((item) => !item.group_id)) {
    lines.push(
      `  ${node.id}["${escapeMermaid(node.label)}<br/>${escapeMermaid(
        node.responsibility,
      )}"]`,
    );
  }
  for (const edge of graph.edges) {
    lines.push(
      `  ${edge.source} -->|"${escapeMermaid(edge.label)}"| ${edge.target}`,
    );
  }
  return `${lines.join("\n")}\n`;
}

export function downloadTextFile(
  filename: string,
  value: string,
  type = "text/plain;charset=utf-8",
): void {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function downloadDataUrl(filename: string, dataUrl: string): void {
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  link.click();
}

function escapeMermaid(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\n", " ");
}
