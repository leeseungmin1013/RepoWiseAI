"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  type Edge,
  MiniMap,
  type Node,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import type { GraphData } from "@/lib/api";

type GraphNodeData = {
  label: string;
  fileId: string | null;
  kind: string;
};

type Props = {
  graph: GraphData | null;
  onOpenFile: (fileId: string) => void;
};

export function DependencyGraph({ graph, onOpenFile }: Props) {
  const nodes = useMemo<Node<GraphNodeData>[]>(
    () =>
      (graph?.nodes ?? []).map((node, index) => ({
        id: node.id,
        position: { x: (index % 4) * 220, y: Math.floor(index / 4) * 105 },
        data: { label: node.label, fileId: node.file_id, kind: node.kind },
        style: {
          width: 180,
          borderRadius: 6,
          border: node.kind === "file" ? "1px solid #72a99f" : "1px solid #d4b06b",
          background: node.kind === "file" ? "#f1faf8" : "#fff8e8",
          color: "#243038",
          fontSize: 12,
          padding: "9px 10px",
        },
      })),
    [graph],
  );

  const edges = useMemo<Edge[]>(
    () =>
      (graph?.edges ?? []).map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        animated: false,
        style: { stroke: "#8a969d", strokeWidth: 1.2 },
      })),
    [graph],
  );

  if (!graph?.nodes.length) {
    return (
      <div className="panel-empty compact-empty">
        <span>이 스냅샷에서 표시할 import 관계가 없습니다.</span>
      </div>
    );
  }

  return (
    <div className="graph-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={1.8}
        onNodeClick={(_, node) => node.data.fileId && onOpenFile(node.data.fileId)}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#cbd2d6" />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) => (node.data.kind === "file" ? "#3d8f82" : "#d6a23f")}
          maskColor="rgba(238, 241, 243, 0.72)"
        />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
