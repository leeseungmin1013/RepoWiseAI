"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  AlertTriangle,
  Braces,
  Download,
  FileText,
  GitCompareArrows,
  ImageDown,
  Loader2,
  Network,
  Route,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { toPng } from "html-to-image";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  ArchitectureGraph,
  ArchitectureGraphDiff,
  ArchitectureGraphEdge,
  ArchitectureGraphNode,
  ChangeBrief,
  FeatureFlowDetail,
  FeatureFlowSummary,
  ProjectMapEvidence,
  Snapshot,
} from "@/lib/api";

import { ArchitectureNode, type ArchitectureNodeData } from "./ArchitectureNode";
import {
  architectureGraphToMermaid,
  downloadDataUrl,
  downloadTextFile,
} from "./architecture-export";
import { fallbackArchitectureLayout, layoutArchitectureGraph } from "./architecture-layout";
import styles from "./ArchitectureMapPanel.module.css";

type Props = {
  graph: ArchitectureGraph | null;
  loading: boolean;
  error: string | null;
  flows: FeatureFlowSummary[];
  flow: FeatureFlowDetail | null;
  selectedFlowId: string | null;
  changeBrief: ChangeBrief | null;
  onSelectFlow: (flowId: string | null) => void;
  onOpenEvidence: (evidence: ProjectMapEvidence) => void;
  onOpenDependencyGraph: () => void;
  onRequestChangeBrief: (evidence: ProjectMapEvidence) => void;
  comparisonSnapshots?: Snapshot[];
  diff?: ArchitectureGraphDiff | null;
  diffLoading?: boolean;
  onCompareSnapshot?: (snapshotId: string | null) => void;
  canEnhanceLabels?: boolean;
  enhancingLabels?: boolean;
  onEnhanceLabels?: () => void;
};

type Selected =
  | { kind: "node"; value: ArchitectureGraphNode }
  | { kind: "edge"; value: ArchitectureGraphEdge }
  | null;

const nodeTypes = { architecture: ArchitectureNode };

export function ArchitectureMapPanel({
  graph,
  loading,
  error,
  flows,
  flow,
  selectedFlowId,
  changeBrief,
  onSelectFlow,
  onOpenEvidence,
  onOpenDependencyGraph,
  onRequestChangeBrief,
  comparisonSnapshots = [],
  diff = null,
  diffLoading = false,
  onCompareSnapshot,
  canEnhanceLabels = false,
  enhancingLabels = false,
  onEnhanceLabels,
}: Props) {
  const [layoutState, setLayoutState] = useState<{
    key: string;
    value: ReturnType<typeof fallbackArchitectureLayout>;
  } | null>(null);
  const [selected, setSelected] = useState<Selected>(null);
  const [showFailure, setShowFailure] = useState(false);
  const [exporting, setExporting] = useState<"png" | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!graph) return;
    let cancelled = false;
    const key = `${graph.snapshot_id}:${graph.commit_sha}:${graph.analysis_version}`;
    layoutArchitectureGraph(graph)
      .catch(() => fallbackArchitectureLayout(graph))
      .then((nextLayout) => {
        if (!cancelled) setLayoutState({ key, value: nextLayout });
      });
    return () => {
      cancelled = true;
    };
  }, [graph]);
  const layoutKey = graph
    ? `${graph.snapshot_id}:${graph.commit_sha}:${graph.analysis_version}`
    : null;
  const layout = layoutState?.key === layoutKey ? layoutState.value : null;

  const flowSteps = useMemo(
    () => (flow ? (showFailure ? flow.failure_steps : flow.normal_steps) : []),
    [flow, showFailure],
  );
  const stepByFile = useMemo(() => {
    const result = new Map<string, number>();
    for (const step of flowSteps) {
      for (const evidence of step.evidence) {
        if (!result.has(evidence.file_id)) result.set(evidence.file_id, step.ordinal);
      }
    }
    return result;
  }, [flowSteps]);
  const directImpactFiles = useMemo(
    () =>
      new Set(
        changeBrief?.confirmed_direct_impacts.flatMap((impact) =>
          impact.evidence.map((evidence) => evidence.file_id),
        ) ?? [],
      ),
    [changeBrief],
  );
  const possibleImpactFiles = useMemo(
    () =>
      new Set(
        changeBrief?.possible_impacts_to_verify.flatMap((impact) =>
          impact.evidence.map((evidence) => evidence.file_id),
        ) ?? [],
      ),
    [changeBrief],
  );
  const diffByPath = useMemo(
    () =>
      new Map(
        diff?.nodes.map((item) => [
          item.path.replaceAll("\\", "/").toLowerCase(),
          item.status,
        ]) ?? [],
      ),
    [diff],
  );

  const nodes = useMemo<Node<ArchitectureNodeData>[]>(() => {
    if (!graph || !layout) return [];
    const groupNodes: Node<ArchitectureNodeData>[] = graph.groups.map((group) => {
      const position = layout.groups.get(group.id) ?? { x: 0, y: 0, width: 284, height: 176 };
      return {
        id: group.id,
        type: "group",
        position: { x: position.x, y: position.y },
        data: { label: group.label } as unknown as ArchitectureNodeData,
        style: {
          width: position.width,
          height: position.height,
          borderRadius: 14,
          border: "1px solid #c7d4d8",
          background: "rgba(246, 248, 249, 0.82)",
          color: "#40515a",
          fontSize: 12,
          fontWeight: 800,
          padding: "14px 16px",
        },
        selectable: false,
      };
    });
    const architectureNodes: Node<ArchitectureNodeData>[] = graph.nodes.map((node) => {
      const position = layout.nodes.get(node.id) ?? { x: 20, y: 52, width: 224, height: 104 };
      const evidenceFiles = node.evidence.map((item) => item.file_id);
      return {
        id: node.id,
        type: "architecture",
        parentId: node.group_id ?? undefined,
        extent: node.group_id ? "parent" : undefined,
        position: { x: position.x, y: position.y },
        data: {
          ...node,
          dimmed: Boolean(selectedFlowId && !node.feature_flow_ids.includes(selectedFlowId)),
          flowOrdinal: evidenceFiles.map((id) => stepByFile.get(id)).find(Boolean) ?? null,
          directImpact: evidenceFiles.some((id) => directImpactFiles.has(id)),
          possibleImpact: evidenceFiles.some((id) => possibleImpactFiles.has(id)),
          diffStatus:
            diffByPath.get(
              node.evidence[0]?.path.replaceAll("\\", "/").toLowerCase() ?? "",
            ) ?? null,
        },
        style: { width: position.width, height: position.height },
      };
    });
    return [...groupNodes, ...architectureNodes];
  }, [
    diffByPath,
    directImpactFiles,
    graph,
    layout,
    possibleImpactFiles,
    selectedFlowId,
    stepByFile,
  ]);

  const edges = useMemo<Edge[]>(() => {
    if (!graph) return [];
    return graph.edges.map((edge) => {
      const active = !selectedFlowId || edge.feature_flow_ids.includes(selectedFlowId);
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: active ? edge.label : undefined,
        animated: Boolean(selectedFlowId && active),
        markerEnd: { type: MarkerType.ArrowClosed, color: active ? "#087f73" : "#b9c5ca" },
        style: {
          stroke: active ? "#087f73" : "#c7d0d4",
          strokeWidth: active && selectedFlowId ? 2.6 : 1.25,
          opacity: active ? 1 : 0.2,
          strokeDasharray: edge.confidence === "inferred" ? "6 4" : undefined,
        },
        labelStyle: { fill: "#40515a", fontSize: 9, fontWeight: 700 },
        data: edge,
      };
    });
  }, [graph, selectedFlowId]);

  if (loading) {
    return <div className={styles.state}><Loader2 className={styles.spin} /> 구조도를 구성하고 있습니다.</div>;
  }
  if (error) {
    return <div className={styles.state}><AlertTriangle /> {error}</div>;
  }
  if (!graph || !graph.nodes.length) {
    return <div className={styles.state}><Network /> 표시할 구조 관계가 없습니다.</div>;
  }

  const selectedEvidence = selected?.value.evidence ?? [];
  const exportMermaid = () => {
    downloadTextFile(
      `${graph.repository_name.replace("/", "-")}-${graph.commit_sha.slice(0, 8)}.mmd`,
      architectureGraphToMermaid(graph),
    );
  };
  const exportPng = async () => {
    if (!canvasRef.current) return;
    setExporting("png");
    try {
      const dataUrl = await toPng(canvasRef.current, {
        backgroundColor: "#f8fafb",
        cacheBust: true,
        pixelRatio: 2,
      });
      downloadDataUrl(
        `${graph.repository_name.replace("/", "-")}-${graph.commit_sha.slice(0, 8)}.png`,
        dataUrl,
      );
    } finally {
      setExporting(null);
    }
  };
  return (
    <section className={styles.panel} aria-label="저장소 구조도">
      <header className={styles.toolbar}>
        <div><Network size={16} /><strong>Repository Structure</strong><span>{graph.nodes.length} nodes · {graph.edges.length} edges</span></div>
        <div className={styles.flowControls}>
          <Route size={14} />
          <select
            aria-label="구조도 기능 흐름"
            value={selectedFlowId ?? ""}
            onChange={(event) => onSelectFlow(event.target.value || null)}
          >
            <option value="">전체 구조</option>
            {flows.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
          {flow?.failure_steps.length ? (
            <button type="button" aria-pressed={showFailure} onClick={() => setShowFailure((value) => !value)}>
              {showFailure ? "정상 경로" : "실패 경로"}
            </button>
          ) : null}
          <button type="button" onClick={onOpenDependencyGraph}><Braces size={13} /> 원시 의존성</button>
          {comparisonSnapshots.length > 0 && onCompareSnapshot ? (
            <label className={styles.compareControl}>
              <GitCompareArrows size={13} />
              <select
                aria-label="비교할 이전 snapshot"
                value={diff?.base_snapshot_id ?? ""}
                disabled={diffLoading}
                onChange={(event) => onCompareSnapshot(event.target.value || null)}
              >
                <option value="">커밋 비교</option>
                {comparisonSnapshots.map((item) => (
                  <option key={item.id} value={item.id}>
                    {(item.commit_sha ?? item.id).slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {canEnhanceLabels && onEnhanceLabels ? (
            <button type="button" disabled={enhancingLabels} onClick={onEnhanceLabels}>
              <Sparkles size={13} /> {enhancingLabels ? "라벨 개선 중" : "AI 라벨 개선"}
            </button>
          ) : null}
          <button type="button" onClick={exportMermaid}>
            <Download size={13} /> Mermaid
          </button>
          <button type="button" disabled={exporting === "png"} onClick={() => void exportPng()}>
            <ImageDown size={13} /> {exporting === "png" ? "PNG 생성 중" : "PNG"}
          </button>
        </div>
      </header>

      <div className={styles.workspace}>
        <div ref={canvasRef} className={styles.canvas}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.12 }}
            minZoom={0.25}
            maxZoom={1.6}
            nodesDraggable={false}
            onNodeClick={(_, node) => {
              const value = graph.nodes.find((item) => item.id === node.id);
              if (value) setSelected({ kind: "node", value });
            }}
            onEdgeClick={(_, edge) => {
              const value = graph.edges.find((item) => item.id === edge.id);
              if (value) setSelected({ kind: "edge", value });
            }}
            onPaneClick={() => setSelected(null)}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#d7dfe2" />
            <MiniMap pannable zoomable maskColor="rgba(238, 241, 243, 0.7)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>

        <aside className={styles.inspector} aria-live="polite">
          {selected ? (
            <>
              <span className={styles.kind}>{selected.kind === "node" ? selected.value.node_type : selected.value.relation}</span>
              <h2>{selected.kind === "node" ? selected.value.label : selected.value.label}</h2>
              <p>{selected.kind === "node" ? selected.value.responsibility : selected.value.description}</p>
              <div className={styles.confidence} data-confidence={selected.value.confidence}>{selected.value.confidence}</div>
              {selected.kind === "node" && selected.value.inputs.length ? <DetailList title="입력" items={selected.value.inputs} /> : null}
              {selected.kind === "node" && selected.value.outputs.length ? <DetailList title="출력·연결" items={selected.value.outputs} /> : null}
              <h3>코드 근거</h3>
              <div className={styles.evidenceList}>
                {selectedEvidence.map((evidence) => (
                  <button key={`${evidence.file_id}:${evidence.start_line}`} type="button" onClick={() => onOpenEvidence(evidence)}>
                    <FileText size={13} /><span>{evidence.path}</span><small>L{evidence.start_line}</small>
                  </button>
                ))}
              </div>
              {selected.kind === "node" && selected.value.evidence[0] ? (
                <button className={styles.changeButton} type="button" onClick={() => onRequestChangeBrief(selected.value.evidence[0])}>
                  <ShieldAlert size={14} /> 이 영역 변경 검토
                </button>
              ) : null}
            </>
          ) : flow ? (
            <>
              <span className={styles.kind}>FEATURE FLOW</span>
              <h2>{flow.title}</h2>
              <p>{flow.trigger} → {flow.outcome}</p>
              <ol className={styles.stepList}>
                {flowSteps.map((step) => (
                  <li key={step.id}>
                    <button type="button" onClick={() => step.evidence[0] && onOpenEvidence(step.evidence[0])}>
                      <b>{step.ordinal}</b><span><strong>{step.title}</strong><small>{step.output_or_side_effect}</small></span>
                    </button>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <>
              <span className={styles.kind}>OVERVIEW</span>
              <h2>{graph.repository_name}</h2>
              <p>{graph.summary}</p>
              <p className={styles.hint}>노드나 관계를 선택하면 책임, 입력·출력과 실제 코드 근거를 확인할 수 있습니다.</p>
              {changeBrief ? <div className={styles.impactLegend}><span>직접 영향</span><span>확인 필요</span></div> : null}
              {diff ? (
                <div className={styles.diffSummary}>
                  <strong>커밋 구조 변경</strong>
                  <span>
                    노드 +{diff.summary.nodes_added} / -{diff.summary.nodes_removed} /
                    변경 {diff.summary.nodes_changed}
                  </span>
                  <span>
                    관계 +{diff.summary.edges_added} / -{diff.summary.edges_removed}
                  </span>
                </div>
              ) : null}
            </>
          )}
        </aside>
      </div>
      {graph.limitations.length ? <footer className={styles.limitations}><AlertTriangle size={14} /> {graph.limitations[0]}</footer> : null}
    </section>
  );
}

function DetailList({ title, items }: { title: string; items: string[] }) {
  return <section className={styles.details}><h3>{title}</h3><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></section>;
}
