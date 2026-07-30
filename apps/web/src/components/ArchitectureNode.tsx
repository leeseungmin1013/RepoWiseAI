import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { ArchitectureGraphNode } from "@/lib/api";

export type ArchitectureNodeData = ArchitectureGraphNode & {
  dimmed: boolean;
  flowOrdinal: number | null;
  directImpact: boolean;
  possibleImpact: boolean;
  diffStatus: "added" | "removed" | "changed" | null;
};

export function ArchitectureNode({ data, selected }: NodeProps) {
  const node = data as unknown as ArchitectureNodeData;
  return (
    <article
      className="architecture-node"
      data-confidence={node.confidence}
      data-dimmed={node.dimmed}
      data-direct-impact={node.directImpact}
      data-possible-impact={node.possibleImpact}
      data-selected={selected}
      data-diff-status={node.diffStatus ?? undefined}
      aria-label={`${node.label}: ${node.responsibility}, ${node.confidence}`}
    >
      <Handle type="target" position={Position.Left} />
      <header>
        <span>{node.node_type}</span>
        <small>{node.confidence}</small>
      </header>
      <strong>{node.label}</strong>
      <p>{node.responsibility}</p>
      {node.flowOrdinal ? <b aria-label={`기능 흐름 ${node.flowOrdinal}단계`}>{node.flowOrdinal}</b> : null}
      <Handle type="source" position={Position.Right} />
    </article>
  );
}
