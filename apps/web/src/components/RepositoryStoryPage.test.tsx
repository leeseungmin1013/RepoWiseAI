import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RepositoryStory } from "@/lib/api";

import { RepositoryStoryPage } from "./RepositoryStoryPage";

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
    ReactFlow: ({
      nodes,
      edges,
      onNodeClick,
      onEdgeClick,
    }: {
      nodes: Array<{ id: string; data: { display_name: string } }>;
      edges: Array<{ id: string; label?: string }>;
      onNodeClick: (event: unknown, node: { id: string }) => void;
      onEdgeClick: (event: unknown, edge: { id: string }) => void;
    }) =>
      React.createElement(
        "div",
        { "data-testid": "story-graph" },
        ...nodes.map((node) =>
          React.createElement(
            "button",
            { key: node.id, onClick: () => onNodeClick({}, node) },
            node.data.display_name,
          ),
        ),
        ...edges.map((edge) =>
          React.createElement(
            "button",
            { key: edge.id, onClick: () => onEdgeClick({}, edge) },
            edge.label ?? edge.id,
          ),
        ),
      ),
  };
});

vi.mock("./ArchitectureMapPanel", () => ({
  ArchitectureMapPanel: ({ graph }: { graph: { nodes: Array<{ id: string }> } }) => (
    <div data-testid="implementation-graph">{graph.nodes.map((node) => node.id).join(",")}</div>
  ),
}));

const evidence = {
  file_id: "file_api",
  path: "apps/api/routes.py",
  start_line: 10,
  end_line: 28,
  reason: "요청을 받는 API",
};

const story: RepositoryStory = {
  repository_name: "example/repository",
  snapshot_id: "snap_1",
  commit_sha: "abc",
  analysis_version: "repository-story-v1",
  purpose: {
    one_liner: "사용자가 복잡한 저장소를 역할 중심으로 이해하도록 돕습니다.",
    primary_audience: "처음 코드를 읽는 개발자",
    primary_outcome: "어디서 무엇을 바꿔야 하는지 이해합니다.",
    how_it_works: ["1. 저장소를 분석합니다.", "2. 역할과 기능 흐름을 연결합니다."],
    confidence: "verified",
    evidence: [evidence],
  },
  roles: [
    {
      id: "role_gateway",
      display_name: "요청을 받는 입구",
      role_summary: "사용자 요청을 받아 분석 기능으로 전달합니다.",
      why_it_exists: "외부 요청과 내부 처리 규칙을 분리하기 위해 필요합니다.",
      contribution_to_goal: "사용자의 행동을 실제 저장소 분석으로 이어 줍니다.",
      receives: ["저장소 URL"],
      produces: ["분석 작업"],
      member_node_ids: ["node_api"],
      member_file_ids: [evidence.file_id],
      capability_ids: ["analyze"],
      feature_flow_ids: ["flow_analyze"],
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  connections: [],
  features: [
    {
      id: "flow_analyze",
      title: "저장소 분석",
      user_goal: "저장소 이해",
      trigger: "분석 시작",
      outcome: "구조도 생성",
      step_count: 3,
      involved_areas: ["server"],
      confidence: "verified",
      evidence_coverage: 1,
      entry_evidence: evidence,
    },
  ],
  implementation_graph: {
    repository_name: "example/repository",
    snapshot_id: "snap_1",
    commit_sha: "abc",
    analysis_version: "architecture-graph-v2",
    summary: "구현 구조",
    groups: [],
    nodes: [
      {
        id: "node_api",
        label: "API",
        responsibility: "요청을 받습니다.",
        node_type: "api",
        group_id: null,
        confidence: "verified",
        inputs: ["URL"],
        outputs: ["job"],
        capability_ids: ["analyze"],
        feature_flow_ids: ["flow_analyze"],
        evidence: [evidence],
      },
    ],
    edges: [],
    limitations: [],
  },
  limitations: ["정적 분석을 기반으로 하므로 런타임 분기는 확인이 필요합니다."],
};

describe("RepositoryStoryPage", () => {
  const onSelectFlow = vi.fn();
  const onOpenEvidence = vi.fn();
  const onOpenDependencyGraph = vi.fn();
  const onRequestChangeBrief = vi.fn();
  const onStartLearning = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(cleanup);

  function renderPage() {
    render(
      <RepositoryStoryPage
        changeBrief={null}
        error={null}
        flow={null}
        loading={false}
        onOpenDependencyGraph={onOpenDependencyGraph}
        onOpenEvidence={onOpenEvidence}
        onRequestChangeBrief={onRequestChangeBrief}
        onSelectFlow={onSelectFlow}
        onStartLearning={onStartLearning}
        selectedFlowId={null}
        story={story}
      />,
    );
  }

  it("explains the repository purpose before exposing implementation details", () => {
    renderPage();

    expect(screen.getByText(story.purpose.one_liner)).toBeTruthy();
    expect(screen.getByText(story.purpose.primary_audience)).toBeTruthy();
    expect(screen.getAllByText(story.purpose.primary_outcome).length).toBeGreaterThan(0);
    expect(screen.getByText("저장소를 분석합니다.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "역할 보기" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("shows a plain-language role explanation and connects its support actions", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: story.roles[0].display_name }));
    expect(screen.getByText(story.roles[0].role_summary)).toBeTruthy();
    expect(screen.getByText(story.roles[0].why_it_exists)).toBeTruthy();
    expect(screen.getByText(story.roles[0].contribution_to_goal)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "근거" }));
    fireEvent.click(screen.getByRole("button", { name: /apps\/api\/routes.py/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(evidence);

    fireEvent.click(screen.getByRole("button", { name: "이 부분을 바꾸면?" }));
    fireEvent.click(screen.getByRole("button", { name: "이 역할 배우기" }));
    expect(onRequestChangeBrief).toHaveBeenCalledWith(evidence);
    expect(onStartLearning).toHaveBeenCalledTimes(1);
  });

  it("filters by a feature and can drill into the implementation graph", () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("그래프에 표시할 기능 흐름"), {
      target: { value: "flow_analyze" },
    });
    expect(onSelectFlow).toHaveBeenCalledWith("flow_analyze");

    fireEvent.click(screen.getByRole("button", { name: story.roles[0].display_name }));
    fireEvent.click(screen.getByRole("button", { name: "구현 상세" }));
    expect(screen.getByTestId("implementation-graph").textContent).toBe("node_api");
  });
});
