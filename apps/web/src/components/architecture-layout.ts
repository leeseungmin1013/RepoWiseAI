import ELK from "elkjs/lib/elk.bundled.js";

import type { ArchitectureGraph } from "@/lib/api";

export type ArchitecturePosition = { x: number; y: number; width: number; height: number };

const elk = new ELK();
const NODE_WIDTH = 224;
const NODE_HEIGHT = 104;

export async function layoutArchitectureGraph(graph: ArchitectureGraph) {
  const groupById = new Map(graph.groups.map((group) => [group.id, group]));
  const root = await elk.layout({
    id: "architecture-root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.spacing.nodeNode": "48",
      "elk.layered.spacing.nodeNodeBetweenLayers": "80",
      "elk.padding": "[top=24,left=24,bottom=24,right=24]",
    },
    children: graph.groups.map((group) => ({
      id: group.id,
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.padding": "[top=52,left=20,bottom=20,right=20]",
        "elk.spacing.nodeNode": "28",
      },
      children: graph.nodes
        .filter((node) => node.group_id === group.id)
        .map((node) => ({ id: node.id, width: NODE_WIDTH, height: NODE_HEIGHT })),
    })),
    edges: graph.edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  });

  const groups = new Map<string, ArchitecturePosition>();
  const nodes = new Map<string, ArchitecturePosition>();
  for (const child of root.children ?? []) {
    if (!groupById.has(child.id)) continue;
    const groupPosition = {
      x: child.x ?? 0,
      y: child.y ?? 0,
      width: Math.max(264, child.width ?? 264),
      height: Math.max(176, child.height ?? 176),
    };
    groups.set(child.id, groupPosition);
    for (const node of child.children ?? []) {
      nodes.set(node.id, {
        x: node.x ?? 20,
        y: node.y ?? 52,
        width: node.width ?? NODE_WIDTH,
        height: node.height ?? NODE_HEIGHT,
      });
    }
  }
  return { groups, nodes };
}

export function fallbackArchitectureLayout(graph: ArchitectureGraph) {
  const groups = new Map<string, ArchitecturePosition>();
  const nodes = new Map<string, ArchitecturePosition>();
  graph.groups.forEach((group, groupIndex) => {
    const children = graph.nodes.filter((node) => node.group_id === group.id);
    groups.set(group.id, {
      x: groupIndex * 330,
      y: 0,
      width: 284,
      height: Math.max(176, 76 + children.length * 126),
    });
    children.forEach((node, nodeIndex) => {
      nodes.set(node.id, {
        x: 30,
        y: 52 + nodeIndex * 126,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      });
    });
  });
  return { groups, nodes };
}
