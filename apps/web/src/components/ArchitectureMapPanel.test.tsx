import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureGraph, ChangeBrief, FeatureFlowDetail } from "@/lib/api";

import { ArchitectureMapPanel } from "./ArchitectureMapPanel";

vi.mock("@xyflow/react", async () => {
  const React = await import("react");
  return {
    Background: () => null,
    BackgroundVariant: { Dots: "dots" },
    Controls: () => null,
    Handle: () => null,
    MarkerType: { ArrowClosed: "arrowclosed" },
    MiniMap: () => null,
    Position: { Left: "left", Right: "right" },
    ReactFlow: ({ nodes, edges, onNodeClick, onEdgeClick }: {
      nodes: Array<{ id: string; data: { label?: string } }>;
      edges: Array<{ id: string; label?: string }>;
      onNodeClick: (event: unknown, node: { id: string }) => void;
      onEdgeClick: (event: unknown, edge: { id: string }) => void;
    }) => React.createElement(
      "div",
      null,
      nodes.map((node) => React.createElement(
        "button",
        { key: node.id, onClick: () => onNodeClick({}, node) },
        node.data.label ?? node.id,
      )),
      edges.map((edge) => React.createElement(
        "button",
        { key: edge.id, onClick: () => onEdgeClick({}, edge) },
        edge.label ?? edge.id,
      )),
    ),
  };
});

vi.mock("./architecture-layout", () => ({
  fallbackArchitectureLayout: vi.fn(),
  layoutArchitectureGraph: vi.fn(async () => ({
    groups: new Map([["group_client", { x: 0, y: 0, width: 280, height: 180 }]]),
    nodes: new Map([["node_client", { x: 20, y: 50, width: 224, height: 104 }]]),
  })),
}));

const evidence = {
  file_id: "file_client",
  path: "src/components/SubmitButton.tsx",
  start_line: 2,
  end_line: 6,
  reason: "client handler",
};

const graph: ArchitectureGraph = {
  repository_name: "example/demo",
  snapshot_id: "snap_1",
  commit_sha: "abc",
  analysis_version: "architecture-graph-v2",
  summary: "제출 기능 예제",
  groups: [
    {
      id: "group_client",
      label: "Client",
      description: "화면",
      layer: "client",
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  nodes: [
    {
      id: "node_client",
      label: "Submit Button",
      responsibility: "사용자 제출을 시작합니다.",
      node_type: "component",
      group_id: "group_client",
      confidence: "verified",
      inputs: ["form values"],
      outputs: ["POST request"],
      capability_ids: ["submit"],
      feature_flow_ids: ["submit-flow"],
      evidence: [evidence],
    },
  ],
  edges: [],
  limitations: ["정적 분석 결과입니다."],
};

const flow: FeatureFlowDetail = {
  id: "submit-flow",
  title: "제출 저장",
  user_goal: "제출",
  trigger: "버튼 클릭",
  outcome: "저장 완료",
  normal_steps: [
    {
      id: "step_1",
      ordinal: 1,
      title: "요청 시작",
      role: "client_handler",
      executes_when: "클릭",
      input: "form",
      output_or_side_effect: "request",
      previous_step_id: null,
      next_step_id: null,
      relation_type: "REQUESTS",
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  failure_steps: [],
  involved_areas: ["client"],
  confidence: "verified",
  limitations: [],
};

const changeBrief: ChangeBrief = {
  id: "brief_1",
  snapshot_id: "snap_1",
  analysis_version: "change-brief-v1",
  request_summary: "제출 변경",
  selection: { file_id: evidence.file_id, start_line: 2, end_line: 6 },
  candidate_locations: [],
  confirmed_direct_impacts: [
    {
      title: "제출 버튼",
      description: "직접 영향",
      relation_type: "DIRECT",
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  possible_impacts_to_verify: [],
  unknown_boundaries: ["runtime"],
  risk_level: "medium",
  risk_rationale: "확인 필요",
  verification_steps: ["test"],
  rollback_guidance: ["revert"],
  evidence: [evidence],
  limitations: [],
};

describe("ArchitectureMapPanel", () => {
  const onOpenEvidence = vi.fn();
  const onSelectFlow = vi.fn();
  const onRequestChangeBrief = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the bounded structure and opens node evidence", async () => {
    render(
      <ArchitectureMapPanel
        changeBrief={changeBrief}
        error={null}
        flow={null}
        flows={[{ id: "submit-flow", title: "제출 저장" } as never]}
        graph={graph}
        loading={false}
        onOpenDependencyGraph={vi.fn()}
        onOpenEvidence={onOpenEvidence}
        onRequestChangeBrief={onRequestChangeBrief}
        onSelectFlow={onSelectFlow}
        selectedFlowId={null}
      />,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: "Submit Button" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Submit Button" }));
    expect(screen.getByText("사용자 제출을 시작합니다.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /src\/components\/SubmitButton/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(evidence);
    fireEvent.click(screen.getByRole("button", { name: "이 영역 변경 검토" }));
    expect(onRequestChangeBrief).toHaveBeenCalledWith(evidence);
  });

  it("selects a feature flow and renders its steps", async () => {
    render(
      <ArchitectureMapPanel
        changeBrief={null}
        error={null}
        flow={flow}
        flows={[{ id: "submit-flow", title: "제출 저장" } as never]}
        graph={graph}
        loading={false}
        onOpenDependencyGraph={vi.fn()}
        onOpenEvidence={onOpenEvidence}
        onRequestChangeBrief={onRequestChangeBrief}
        onSelectFlow={onSelectFlow}
        selectedFlowId="submit-flow"
      />,
    );

    expect(await screen.findByText("요청 시작")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("구조도 기능 흐름"), { target: { value: "" } });
    expect(onSelectFlow).toHaveBeenCalledWith(null);
  });
});
