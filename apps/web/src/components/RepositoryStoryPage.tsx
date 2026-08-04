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
  ArrowRight,
  BookOpen,
  Braces,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Code2,
  FileText,
  GitBranch,
  GraduationCap,
  Loader2,
  Network,
  Route,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import type {
  ArchitectureGraph,
  ArchitectureGraphDiff,
  ChangeBrief,
  FeatureFlowDetail,
  ProjectMapEvidence,
  RepositoryStory,
  RepositoryStoryConnection,
  RepositoryStoryRole,
  Snapshot,
} from "@/lib/api";

import { ArchitectureMapPanel } from "./ArchitectureMapPanel";
import { RoleNode, type RoleNodeData } from "./RoleNode";
import styles from "./RepositoryStoryPage.module.css";

type Props = {
  story: RepositoryStory | null;
  loading: boolean;
  error: string | null;
  flow: FeatureFlowDetail | null;
  selectedFlowId: string | null;
  changeBrief: ChangeBrief | null;
  onSelectFlow: (flowId: string | null) => void;
  onOpenEvidence: (evidence: ProjectMapEvidence) => void;
  onOpenDependencyGraph: () => void;
  onRequestChangeBrief: (evidence: ProjectMapEvidence) => void;
  onStartLearning: () => void;
  comparisonSnapshots?: Snapshot[];
  diff?: ArchitectureGraphDiff | null;
  diffLoading?: boolean;
  onCompareSnapshot?: (snapshotId: string | null) => void;
  canEnhanceLabels?: boolean;
  enhancingLabels?: boolean;
  onEnhanceLabels?: () => void;
};

type Selection =
  | { kind: "role"; value: RepositoryStoryRole }
  | { kind: "connection"; value: RepositoryStoryConnection }
  | null;

type InspectorTab = "overview" | "flow" | "evidence";

const nodeTypes = { storyRole: RoleNode };

export function RepositoryStoryPage({
  story,
  loading,
  error,
  flow,
  selectedFlowId,
  changeBrief,
  onSelectFlow,
  onOpenEvidence,
  onOpenDependencyGraph,
  onRequestChangeBrief,
  onStartLearning,
  comparisonSnapshots = [],
  diff = null,
  diffLoading = false,
  onCompareSnapshot,
  canEnhanceLabels = false,
  enhancingLabels = false,
  onEnhanceLabels,
}: Props) {
  const [selection, setSelection] = useState<Selection>(null);
  const [viewLevel, setViewLevel] = useState<"roles" | "implementation">("roles");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("overview");

  const flowStepByFile = useMemo(() => {
    const result = new Map<string, number>();
    for (const step of flow?.normal_steps ?? []) {
      for (const evidence of step.evidence) {
        const previous = result.get(evidence.file_id);
        if (previous === undefined || step.ordinal < previous) {
          result.set(evidence.file_id, step.ordinal);
        }
      }
    }
    return result;
  }, [flow]);

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

  const nodes = useMemo<Node<RoleNodeData>[]>(() => {
    if (!story) return [];
    const columns = story.roles.length <= 4 ? story.roles.length : 4;
    return story.roles.map((role, index) => {
      const flowOrdinals = role.member_file_ids
        .map((fileId) => flowStepByFile.get(fileId))
        .filter((value): value is number => value !== undefined);
      return {
        id: role.id,
        type: "storyRole",
        position: {
          x: (index % columns) * 320,
          y: Math.floor(index / columns) * 224,
        },
        data: {
          ...role,
          onActivate: (roleId: string) => {
            const value = story.roles.find((item) => item.id === roleId);
            if (value) {
              setSelection({ kind: "role", value });
              setInspectorTab("overview");
            }
          },
          dimmed: Boolean(
            selectedFlowId && !role.feature_flow_ids.includes(selectedFlowId),
          ),
          flowOrdinal: flowOrdinals.length ? Math.min(...flowOrdinals) : null,
          directImpact: role.member_file_ids.some((fileId) =>
            directImpactFiles.has(fileId),
          ),
          possibleImpact: role.member_file_ids.some((fileId) =>
            possibleImpactFiles.has(fileId),
          ),
        },
        style: { width: 276, height: 178 },
      };
    });
  }, [
    directImpactFiles,
    flowStepByFile,
    possibleImpactFiles,
    selectedFlowId,
    story,
  ]);

  const edges = useMemo<Edge[]>(() => {
    if (!story) return [];
    return story.connections.map((connection) => {
      const active =
        !selectedFlowId || connection.feature_flow_ids.includes(selectedFlowId);
      return {
        id: connection.id,
        source: connection.source,
        target: connection.target,
        label: active ? connection.label : undefined,
        animated: Boolean(selectedFlowId && active),
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: active ? "#087f73" : "#aeb9be",
        },
        style: {
          stroke: active ? "#087f73" : "#bfc8cc",
          strokeWidth: selectedFlowId && active ? 2.8 : 1.5,
          opacity: active ? 1 : 0.16,
          strokeDasharray:
            connection.confidence === "inferred" ? "6 4" : undefined,
        },
        labelStyle: { fill: "#3b4a51", fontSize: 10, fontWeight: 750 },
        labelBgStyle: { fill: "#f8fafb", fillOpacity: 0.94 },
        data: connection,
      };
    });
  }, [selectedFlowId, story]);

  const implementationGraph = useMemo(() => {
    if (!story) return null;
    if (selection?.kind !== "role") return story.implementation_graph;
    return filterImplementationGraph(
      story.implementation_graph,
      new Set(selection.value.member_node_ids),
    );
  }, [selection, story]);

  if (loading) {
    return (
      <section className={styles.state}>
        <Loader2 className={styles.spin} aria-hidden />
        <div><strong>저장소 이야기를 구성하고 있습니다.</strong><span>목적, 역할과 기능 흐름을 실제 코드 근거에 연결합니다.</span></div>
      </section>
    );
  }
  if (error) {
    return (
      <section className={styles.state} data-error>
        <AlertTriangle aria-hidden />
        <div><strong>Repository Structure를 불러오지 못했습니다.</strong><span>{error}</span></div>
      </section>
    );
  }
  if (!story) {
    return (
      <section className={styles.state}>
        <Network aria-hidden />
        <div><strong>아직 구조도가 없습니다.</strong><span>저장소 분석이 끝나면 전체 목적부터 보여드립니다.</span></div>
      </section>
    );
  }

  return (
    <section className={styles.page} aria-label="Repository Structure">
      <section className={styles.purpose}>
        <div className={styles.purposeCopy}>
          <div className={styles.eyebrow}>
            <Sparkles aria-hidden size={15} />
            <span>REPOSITORY STORY</span>
            <span className={styles.confidence} data-confidence={story.purpose.confidence}>
              {story.purpose.confidence === "verified" ? "근거 확인" : "분석 추론"}
            </span>
          </div>
          <h1>{story.repository_name}</h1>
          <p>{story.purpose.one_liner}</p>
          <div className={styles.purposeFacts}>
            <div><span>누가 사용하나요?</span><strong>{story.purpose.primary_audience}</strong></div>
            <div><span>무엇을 얻나요?</span><strong>{story.purpose.primary_outcome}</strong></div>
          </div>
        </div>
        <ol className={styles.storySteps} aria-label="저장소가 작동하는 순서">
          {story.purpose.how_it_works.slice(0, 4).map((step, index) => (
            <li key={step}><b>{index + 1}</b><span>{step.replace(/^\d+\.\s*/, "")}</span></li>
          ))}
        </ol>
      </section>

      <header className={styles.actionBar}>
        <div className={styles.viewToggle} aria-label="구조 상세 수준">
          <button
            aria-pressed={viewLevel === "roles"}
            className={viewLevel === "roles" ? styles.active : ""}
            onClick={() => setViewLevel("roles")}
            type="button"
          >
            <Sparkles aria-hidden size={15} /> 역할 보기
          </button>
          <button
            aria-pressed={viewLevel === "implementation"}
            className={viewLevel === "implementation" ? styles.active : ""}
            onClick={() => setViewLevel("implementation")}
            type="button"
          >
            <GitBranch aria-hidden size={15} /> 구현 보기
          </button>
        </div>
        <label className={styles.featureSelect}>
          <Route aria-hidden size={15} />
          <span>기능 흐름</span>
          <select
            aria-label="그래프에 표시할 기능 흐름"
            value={selectedFlowId ?? ""}
            onChange={(event) => onSelectFlow(event.target.value || null)}
          >
            <option value="">전체 구조</option>
            {story.features.map((feature) => (
              <option key={feature.id} value={feature.id}>{feature.title}</option>
            ))}
          </select>
        </label>
        <details className={styles.moreMenu}>
          <summary><span>더 보기</span><ChevronDown aria-hidden size={15} /></summary>
          <div>
            <button type="button" onClick={onOpenDependencyGraph}><Braces aria-hidden size={14} /> 고급 코드 탐색</button>
            <button type="button" onClick={onStartLearning}><GraduationCap aria-hidden size={14} /> 전체 구조 배우기</button>
            <button
              type="button"
              onClick={() => {
                setViewLevel("implementation");
                setSelection(null);
              }}
            >
              <Code2 aria-hidden size={14} /> 전체 구현 그래프
            </button>
          </div>
        </details>
      </header>

      {viewLevel === "implementation" && implementationGraph ? (
        <ArchitectureMapPanel
          canEnhanceLabels={canEnhanceLabels}
          changeBrief={changeBrief}
          comparisonSnapshots={comparisonSnapshots}
          diff={diff}
          diffLoading={diffLoading}
          enhancingLabels={enhancingLabels}
          error={null}
          flow={flow}
          flows={story.features}
          graph={implementationGraph}
          loading={false}
          onCompareSnapshot={onCompareSnapshot}
          onEnhanceLabels={onEnhanceLabels}
          onOpenDependencyGraph={onOpenDependencyGraph}
          onOpenEvidence={onOpenEvidence}
          onRequestChangeBrief={onRequestChangeBrief}
          onSelectFlow={onSelectFlow}
          selectedFlowId={selectedFlowId}
        />
      ) : (
        <div className={styles.storyWorkspace}>
          <div className={styles.canvas}>
            <ReactFlow
              aria-label="저장소 역할 구조도"
              edges={edges}
              fitView
              fitViewOptions={{ padding: 0.16 }}
              maxZoom={1.45}
              minZoom={0.36}
              nodes={nodes}
              nodesDraggable={false}
              nodeTypes={nodeTypes}
              onEdgeClick={(_, edge) => {
                const value = story.connections.find((item) => item.id === edge.id);
                if (value) {
                  setSelection({ kind: "connection", value });
                  setInspectorTab("overview");
                }
              }}
              onNodeClick={(_, node) => {
                const value = story.roles.find((item) => item.id === node.id);
                if (value) {
                  setSelection({ kind: "role", value });
                  setInspectorTab("overview");
                }
              }}
              onPaneClick={() => setSelection(null)}
            >
              <Background color="#d4dddf" gap={22} size={1} variant={BackgroundVariant.Dots} />
              <MiniMap pannable zoomable maskColor="rgba(238, 243, 243, 0.74)" />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          <StoryInspector
            changeBrief={changeBrief}
            flow={flow}
            onClose={() => setSelection(null)}
            onOpenEvidence={onOpenEvidence}
            onRequestChangeBrief={onRequestChangeBrief}
            onShowImplementation={() => setViewLevel("implementation")}
            onStartLearning={onStartLearning}
            selection={selection}
            setTab={setInspectorTab}
            story={story}
            tab={inspectorTab}
          />
        </div>
      )}

      <footer className={styles.limitations}>
        <CircleHelp aria-hidden size={15} />
        <span>{story.limitations[0]}</span>
      </footer>
    </section>
  );
}

function StoryInspector({
  story,
  selection,
  flow,
  changeBrief,
  tab,
  setTab,
  onClose,
  onOpenEvidence,
  onRequestChangeBrief,
  onStartLearning,
  onShowImplementation,
}: {
  story: RepositoryStory;
  selection: Selection;
  flow: FeatureFlowDetail | null;
  changeBrief: ChangeBrief | null;
  tab: InspectorTab;
  setTab: (tab: InspectorTab) => void;
  onClose: () => void;
  onOpenEvidence: (evidence: ProjectMapEvidence) => void;
  onRequestChangeBrief: (evidence: ProjectMapEvidence) => void;
  onStartLearning: () => void;
  onShowImplementation: () => void;
}) {
  const evidence = selection?.value.evidence ?? story.purpose.evidence;
  const role = selection?.kind === "role" ? selection.value : null;
  const connection = selection?.kind === "connection" ? selection.value : null;
  const relatedFeatures = role
    ? story.features.filter((feature) => role.feature_flow_ids.includes(feature.id))
    : connection
      ? story.features.filter((feature) =>
          connection.feature_flow_ids.includes(feature.id),
        )
      : story.features;

  return (
    <aside
      aria-live="polite"
      aria-label="선택한 구조 요소 설명"
      className={styles.inspector}
      data-selected={Boolean(selection)}
    >
      <header className={styles.inspectorHeader}>
        <div>
          <span>{role ? "SYSTEM ROLE" : connection ? "CONNECTION" : "HOW IT WORKS"}</span>
          <h2>{role?.display_name ?? connection?.label ?? "이 저장소가 목적을 이루는 방법"}</h2>
        </div>
        {selection ? <button aria-label="설명 닫기" onClick={onClose} type="button"><X size={17} /></button> : null}
      </header>

      {selection ? (
        <nav className={styles.inspectorTabs} aria-label="구조 설명 보기">
          <button className={tab === "overview" ? styles.active : ""} onClick={() => setTab("overview")} type="button">설명</button>
          <button className={tab === "flow" ? styles.active : ""} onClick={() => setTab("flow")} type="button">기능</button>
          <button className={tab === "evidence" ? styles.active : ""} onClick={() => setTab("evidence")} type="button">근거</button>
        </nav>
      ) : null}

      <div className={styles.inspectorScroll}>
        {!selection ? (
          <>
            <p className={styles.lead}>{story.purpose.primary_outcome}</p>
            <ol className={styles.howList}>
              {story.purpose.how_it_works.map((step) => <li key={step}>{step}</li>)}
            </ol>
            <p className={styles.hint}>역할을 선택하면 이 저장소의 목적에 왜 필요한지 쉬운 설명과 코드 근거를 볼 수 있습니다.</p>
          </>
        ) : tab === "overview" ? (
          role ? (
            <>
              <p className={styles.lead}>{role.role_summary}</p>
              <ExplainBlock title="왜 필요한가요?" text={role.why_it_exists} />
              <ExplainBlock title="전체 목적에 어떻게 기여하나요?" text={role.contribution_to_goal} />
              <IoList title="무엇을 받나요?" items={role.receives} />
              <IoList title="무엇을 넘기나요?" items={role.produces} />
            </>
          ) : (
            <>
              <p className={styles.lead}>{connection?.description}</p>
              <ExplainBlock
                title="어떤 연결인가요?"
                text={(connection?.relation_types ?? []).join(" · ")}
              />
            </>
          )
        ) : tab === "flow" ? (
          <>
            {flow ? (
              <div className={styles.activeFlow}>
                <span>현재 선택한 기능</span>
                <strong>{flow.title}</strong>
                <p>{flow.trigger} → {flow.outcome}</p>
              </div>
            ) : null}
            <div className={styles.featureCards}>
              {relatedFeatures.length ? relatedFeatures.map((feature) => (
                <article key={feature.id}>
                  <Route aria-hidden size={15} />
                  <div><strong>{feature.title}</strong><span>{feature.user_goal}</span></div>
                </article>
              )) : <p className={styles.hint}>대표 기능 흐름과 직접 연결된 근거를 찾지 못했습니다.</p>}
            </div>
          </>
        ) : (
          <div className={styles.evidenceList}>
            <p className={styles.hint}>설명은 아래 저장소 파일과 line을 근거로 만들었습니다.</p>
            {evidence.map((item) => (
              <button key={`${item.file_id}:${item.start_line}`} onClick={() => onOpenEvidence(item)} type="button">
                <FileText aria-hidden size={15} />
                <span><strong>{item.path}</strong><small>{item.reason}</small></span>
                <b>L{item.start_line}</b>
              </button>
            ))}
          </div>
        )}
      </div>

      {role ? (
        <footer className={styles.inspectorActions}>
          <button onClick={onShowImplementation} type="button"><Code2 aria-hidden size={15} /> 구현 상세</button>
          <button onClick={onStartLearning} type="button"><BookOpen aria-hidden size={15} /> 이 역할 배우기</button>
          {role.evidence[0] ? (
            <button onClick={() => onRequestChangeBrief(role.evidence[0])} type="button"><ShieldAlert aria-hidden size={15} /> 이 부분을 바꾸면?</button>
          ) : null}
          {changeBrief ? <span><CheckCircle2 aria-hidden size={14} /> 변경 영향 결과가 구조도에 표시됐습니다.</span> : null}
        </footer>
      ) : connection?.evidence[0] ? (
        <footer className={styles.inspectorActions}>
          <button onClick={() => onOpenEvidence(connection.evidence[0])} type="button"><FileText aria-hidden size={15} /> 연결 근거 보기</button>
        </footer>
      ) : null}
    </aside>
  );
}

function ExplainBlock({ title, text }: { title: string; text: string }) {
  return <section className={styles.explainBlock}><h3>{title}</h3><p>{text}</p></section>;
}

function IoList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className={styles.ioList}>
      <h3>{title}</h3>
      <ul>{items.map((item) => <li key={item}><ArrowRight aria-hidden size={13} /> {item}</li>)}</ul>
    </section>
  );
}

function filterImplementationGraph(
  graph: ArchitectureGraph,
  memberNodeIds: Set<string>,
): ArchitectureGraph {
  const nodes = graph.nodes.filter((node) => memberNodeIds.has(node.id));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const groupIds = new Set(nodes.map((node) => node.group_id).filter(Boolean));
  return {
    ...graph,
    groups: graph.groups.filter((group) => groupIds.has(group.id)),
    nodes,
    edges: graph.edges.filter(
      (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
    ),
    limitations: [
      "선택한 역할을 구현하는 파일만 표시합니다. 전체 구현은 상단의 역할 보기를 선택한 뒤 구현 보기로 다시 열 수 있습니다.",
      ...graph.limitations,
    ],
  };
}
