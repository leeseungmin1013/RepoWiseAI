import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FeatureFlowCatalog, FeatureFlowDetail } from "@/lib/api";

import { FeatureFlowPanel } from "./FeatureFlowPanel";

const entryEvidence = {
  file_id: "file-route",
  path: "apps/api/app/api/repositories.py",
  start_line: 100,
  end_line: 112,
  reason: "요청을 받는 API 라우트입니다.",
};

const serviceEvidence = {
  file_id: "file-service",
  path: "apps/api/app/navigation/feature_flow.py",
  start_line: 45,
  end_line: 63,
  reason: "흐름을 조립하는 서비스입니다.",
};

const catalog: FeatureFlowCatalog = {
  repository_name: "RepoWiseAI",
  snapshot_id: "snapshot-1",
  commit_sha: "abcdef1234567890",
  analysis_version: "feature-flow-v2",
  flows: [
    {
      id: "flow-project-map",
      title: "프로젝트 지도 조회",
      user_goal: "저장소의 큰 그림을 먼저 이해합니다.",
      trigger: "사용자가 프로젝트 지도를 엽니다.",
      outcome: "기능과 시스템 영역이 표시됩니다.",
      step_count: 2,
      involved_areas: ["API", "Web"],
      confidence: "verified",
      evidence_coverage: 1,
      entry_evidence: entryEvidence,
    },
  ],
  limitations: ["동적 호출은 정적 분석 범위에 포함되지 않습니다."],
};

const detail: FeatureFlowDetail = {
  id: "flow-project-map",
  title: "프로젝트 지도 조회",
  user_goal: "저장소의 큰 그림을 먼저 이해합니다.",
  trigger: "사용자가 프로젝트 지도를 엽니다.",
  outcome: "기능과 시스템 영역이 표시됩니다.",
  normal_steps: [
    {
      id: "step-service",
      ordinal: 2,
      title: "지도 근거 조립",
      role: "server_handler",
      executes_when: "라우트가 준비된 스냅샷을 전달할 때",
      input: "스냅샷 파일과 심볼",
      output_or_side_effect: "프로젝트 지도 응답",
      previous_step_id: "step-route",
      next_step_id: null,
      relation_type: "HANDLED_BY",
      confidence: "inferred",
      evidence: [serviceEvidence],
    },
    {
      id: "step-route",
      ordinal: 1,
      title: "지도 API 요청 수신",
      role: "user_trigger",
      executes_when: "GET 요청이 도착할 때",
      input: "snapshot_id",
      output_or_side_effect: "서비스 호출",
      previous_step_id: null,
      next_step_id: "step-service",
      relation_type: "TRIGGERS",
      confidence: "verified",
      evidence: [entryEvidence],
    },
  ],
  failure_steps: [],
  involved_areas: ["API", "Web"],
  confidence: "inferred",
  limitations: ["클라이언트 런타임 이벤트는 정적 코드만으로 확정할 수 없습니다."],
};

const defaultProps = {
  catalog,
  flow: null,
  loading: false,
  detailLoading: false,
  error: null,
  onBackToMap: vi.fn(),
  onBackToCatalog: vi.fn(),
  onOpenEvidence: vi.fn(),
  onRetry: vi.fn(),
  onSelectFlow: vi.fn(),
  onStartLearning: vi.fn(),
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("FeatureFlowPanel", () => {
  it("renders the catalog as user goals and selects an actual flow id", () => {
    const onSelectFlow = vi.fn();
    const onOpenEvidence = vi.fn();
    render(
      <FeatureFlowPanel
        {...defaultProps}
        onOpenEvidence={onOpenEvidence}
        onSelectFlow={onSelectFlow}
      />,
    );

    expect(screen.getByRole("heading", { name: "어떤 사용자 행동을 따라가 볼까요?" })).toBeTruthy();
    expect(screen.getByText("저장소의 큰 그림을 먼저 이해합니다.")).toBeTruthy();
    expect(screen.getByText("코드 근거 100%")).toBeTruthy();
    expect(screen.getByText("동적 호출은 정적 분석 범위에 포함되지 않습니다.")).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", { name: "프로젝트 지도 조회 흐름 따라가기" }),
    );
    expect(onSelectFlow).toHaveBeenCalledWith("flow-project-map");

    fireEvent.click(screen.getByRole("button", { name: /프로젝트 지도 조회 진입점/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(entryEvidence, {
      featureFlowId: "flow-project-map",
    });
  });

  it("orders normal steps, exposes user-facing relation and confidence, and opens exact evidence", () => {
    const onOpenEvidence = vi.fn();
    const { container } = render(
      <FeatureFlowPanel
        {...defaultProps}
        flow={detail}
        onOpenEvidence={onOpenEvidence}
      />,
    );

    const text = container.textContent ?? "";
    expect(text.indexOf("지도 API 요청 수신")).toBeLessThan(text.indexOf("지도 근거 조립"));
    expect(screen.getByText("관계 · 다음 동작 시작")).toBeTruthy();
    expect(screen.getByText("관계 · 요청 처리")).toBeTruthy();
    expect(screen.getByText("사용자 행동")).toBeTruthy();
    expect(screen.getByText("서버 처리")).toBeTruthy();
    expect(screen.getAllByText("코드로 확인").length).toBeGreaterThan(0);
    expect(screen.getByText(/클라이언트 런타임 이벤트/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "실패·예외 흐름" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /지도 API 요청 수신/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(entryEvidence, {
      featureFlowId: "flow-project-map",
      flowStepId: "step-route",
    });
  });

  it("labels an impossible no-evidence step defensively without treating it as valid backend data", () => {
    const defensiveDetail: FeatureFlowDetail = {
      ...detail,
      normal_steps: [
        {
          ...detail.normal_steps[0],
          id: "defensive-unknown",
          confidence: "unknown",
          evidence: [],
        },
      ],
    };
    render(<FeatureFlowPanel {...defaultProps} flow={defensiveDetail} />);

    expect(screen.getByText(/정확한 코드 위치는 아직 확인하지 못했습니다/)).toBeTruthy();
    expect(screen.getByText(/‘확인 필요’ 단계는 정적 코드만으로/)).toBeTruthy();
  });

  it("explains storage, state, navigation, and external service effects in plain language", () => {
    const effectRelations = [
      ["READS", "storage_read", "임시 저장값 읽기"],
      ["WRITES", "state_write", "답변 화면 상태 갱신"],
      ["NAVIGATES_TO", "navigation", "결과 화면으로 이동"],
      ["USES_EXTERNAL", "external_service", "OpenAI 외부 서비스 사용"],
    ] as const;
    const effectDetail: FeatureFlowDetail = {
      ...detail,
      normal_steps: effectRelations.map(([relation, role, title], index) => ({
        ...detail.normal_steps[0],
        id: `effect-${relation}`,
        ordinal: index + 1,
        title,
        role,
        relation_type: relation,
      })),
    };

    render(<FeatureFlowPanel {...defaultProps} flow={effectDetail} />);

    expect(screen.getByText("관계 · 저장된 값 읽기")).toBeTruthy();
    expect(screen.getByText("관계 · 결과 저장")).toBeTruthy();
    expect(screen.getByText("관계 · 화면 이동")).toBeTruthy();
    expect(screen.getByText("관계 · 외부 서비스 사용")).toBeTruthy();
    expect(screen.getByText("저장값 읽기")).toBeTruthy();
    expect(screen.getByText("화면 상태 변경")).toBeTruthy();
    expect(screen.getByText("화면 이동")).toBeTruthy();
    expect(screen.getByText("외부 서비스")).toBeTruthy();
  });

  it("shows a failure section only when failure steps exist", () => {
    const failureDetail: FeatureFlowDetail = {
      ...detail,
      failure_steps: [
        {
          ...detail.normal_steps[0],
          id: "failure-step",
          ordinal: 1,
          title: "잘못된 스냅샷 거절",
          relation_type: "FAILS_WITH",
        },
      ],
    };
    render(<FeatureFlowPanel {...defaultProps} flow={failureDetail} />);

    expect(screen.getByRole("heading", { name: "실패·예외 흐름" })).toBeTruthy();
    expect(screen.getByText("잘못된 스냅샷 거절")).toBeTruthy();
  });

  it("preserves backend limitations when the catalog has no flows", () => {
    render(
      <FeatureFlowPanel
        {...defaultProps}
        catalog={{
          ...catalog,
          flows: [],
          limitations: ["새 관계 분석을 적용하려면 저장소를 다시 분석해 주세요."],
        }}
      />,
    );

    expect(screen.getByText("확인된 기능 흐름이 없습니다")).toBeTruthy();
    expect(
      screen.getByText("새 관계 분석을 적용하려면 저장소를 다시 분석해 주세요."),
    ).toBeTruthy();
  });
});
