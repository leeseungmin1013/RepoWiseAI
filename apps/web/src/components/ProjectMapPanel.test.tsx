import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProjectMap, Snapshot } from "@/lib/api";

import { ProjectMapPanel } from "./ProjectMapPanel";

const evidence = {
  file_id: "file-entry",
  path: "src/app/page.tsx",
  start_line: 12,
  end_line: 48,
  reason: "사용자가 처음 만나는 화면입니다.",
};

const map = {
  repository_name: "RepoWiseAI",
  snapshot_id: "snapshot-1",
  commit_sha: "abcdef1234567890",
  summary: "GitHub 저장소의 구조와 기능 흐름을 초보자도 읽을 수 있게 안내합니다.",
  summary_confidence: "verified",
  tech_stack: [
    { name: "Next.js", category: "frontend", confidence: "verified", evidence: [evidence] },
  ],
  capabilities: [
    {
      id: "map",
      name: "프로젝트 지도 만들기",
      description: "저장소를 사용자 기능 중심으로 정리합니다.",
      confidence: "verified",
      evidence: [evidence],
    },
    {
      id: "flow",
      name: "기능 흐름 따라가기",
      description: "여러 파일에 걸친 실행 순서를 보여줍니다.",
      confidence: "inferred",
      evidence: [],
    },
    {
      id: "learn",
      name: "필요한 개념 배우기",
      description: "코드를 읽다가 필요한 개념만 깊게 학습합니다.",
      confidence: "verified",
      evidence: [],
    },
    {
      id: "hidden",
      name: "처음부터 강조하지 않을 네 번째 기능",
      description: "대표 기능은 세 개만 보여야 합니다.",
      confidence: "unknown",
      evidence: [],
    },
  ],
  system_areas: [
    {
      id: "web",
      name: "웹 화면",
      description: "저장소 지도를 표시하고 탐색 입력을 받습니다.",
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  external_services: [
    {
      name: "GitHub",
      description: "분석할 저장소 코드를 가져옵니다.",
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  environment_variables: [
    {
      name: "OPENAI_API_KEY=sk-inline-secret",
      description: "AI 설명 생성에 필요합니다.",
      confidence: "verified",
      evidence: [evidence],
      value: "sk-this-must-never-render",
    },
  ],
  read_first: [
    {
      ...evidence,
      confidence: "verified",
    },
  ],
  limitations: ["동적으로 생성되는 경로는 정적 분석만으로 확인하지 못했습니다."],
} as unknown as ProjectMap;

const snapshot: Snapshot = {
  id: "snapshot-1",
  repository_id: "repository-1",
  branch: "main",
  commit_sha: "abcdef1234567890",
  status: "ready",
  parser_version: "parser-v1",
  index_version: "index-v1",
  file_count: 20,
  symbol_count: 80,
  edge_count: 100,
  chunk_count: 90,
  total_bytes: 1000,
  embedding_model: "text-embedding-3-small",
  error_message: null,
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
  job: null,
};

const featureFlows = ["저장소 분석", "프로젝트 지도 조회", "코드 근거 열기", "숨겨진 네 번째 흐름"].map(
  (title, index) => ({
    id: `flow-${index + 1}`,
    title,
    user_goal: `${title} 결과를 얻습니다.`,
    trigger: `${title} 요청`,
    outcome: `${title} 완료`,
    step_count: 2,
    involved_areas: ["Web"],
    confidence: "verified" as const,
    evidence_coverage: 1,
    entry_evidence: evidence,
  }),
);

afterEach(cleanup);

describe("ProjectMapPanel", () => {
  it("leads with the map, limits prominent capabilities, and keeps secrets out of the UI", () => {
    const onOpenEvidence = vi.fn();
    const onOpenExplorer = vi.fn();
    const onOpenFeatureFlows = vi.fn();
    const onStartLearning = vi.fn();
    const { container } = render(
      <ProjectMapPanel
        map={map}
        snapshot={snapshot}
        loading={false}
        featureFlows={featureFlows}
        onOpenEvidence={onOpenEvidence}
        onOpenExplorer={onOpenExplorer}
        onOpenFeatureFlows={onOpenFeatureFlows}
        onStartLearning={onStartLearning}
      />,
    );

    expect(container.textContent).toContain(
      "GitHub 저장소의 구조와 기능 흐름을 초보자도 읽을 수 있게 안내합니다.",
    );
    expect(container.textContent).toContain("프로젝트 지도 만들기");
    expect(container.textContent).toContain("필요한 개념 배우기");
    expect(container.textContent).not.toContain("처음부터 강조하지 않을 네 번째 기능");
    expect(container.textContent).toContain("저장소 분석");
    expect(container.textContent).not.toContain("숨겨진 네 번째 흐름");
    expect(container.textContent).toContain("OPENAI_API_KEY");
    expect(container.textContent).not.toContain("sk-inline-secret");
    expect(container.textContent).not.toContain("sk-this-must-never-render");
    expect(container.textContent).toContain("동적으로 생성되는 경로");

    fireEvent.click(
      screen.getByRole("button", { name: "근거 코드 열기: 프로젝트 지도 만들기, src/app/page.tsx" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "근거 코드 열기: GitHub, src/app/page.tsx" }));
    fireEvent.click(screen.getByRole("button", { name: "코드 열기: src/app/page.tsx" }));
    fireEvent.click(screen.getByRole("button", { name: "원본 코드 탐색" }));
    fireEvent.click(screen.getByRole("button", { name: "기능 흐름 보기" }));
    fireEvent.click(screen.getByRole("button", { name: /저장소 분석저장소 분석 요청/ }));
    fireEvent.click(screen.getByRole("button", { name: /깊이 배우기/ }));

    expect(onOpenEvidence).toHaveBeenNthCalledWith(1, evidence);
    expect(onOpenEvidence).toHaveBeenNthCalledWith(2, evidence);
    expect(onOpenEvidence).toHaveBeenNthCalledWith(3, {
      ...evidence,
      confidence: "verified",
    });
    expect(onOpenExplorer).toHaveBeenCalledTimes(1);
    expect(onOpenFeatureFlows).toHaveBeenNthCalledWith(1);
    expect(onOpenFeatureFlows).toHaveBeenNthCalledWith(2, "flow-1");
    expect(onStartLearning).toHaveBeenCalledTimes(1);
  });

  it("lets the user choose an intent without a skill assessment", () => {
    render(
      <ProjectMapPanel
        map={map}
        snapshot={snapshot}
        loading={false}
        featureFlows={[]}
        onOpenEvidence={vi.fn()}
        onOpenExplorer={vi.fn()}
        onOpenFeatureFlows={vi.fn()}
        onStartLearning={vi.fn()}
      />,
    );

    const changeIntent = screen.getByRole("button", { name: "작은 수정 준비" });
    expect(changeIntent.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(changeIntent);
    expect(changeIntent.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("status").textContent).toContain("먼저 읽을 코드");
  });

  it("shows a dedicated loading state", () => {
    render(
      <ProjectMapPanel
        map={null}
        snapshot={null}
        loading
        featureFlows={[]}
        onOpenEvidence={vi.fn()}
        onOpenExplorer={vi.fn()}
        onOpenFeatureFlows={vi.fn()}
        onStartLearning={vi.fn()}
      />,
    );

    expect(screen.getByText("프로젝트 지도를 만들고 있어요")).toBeTruthy();
  });
});
