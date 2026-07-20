import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChangeBrief, DeepTask } from "@/lib/api";

import { ChangeBriefPanel } from "./ChangeBriefPanel";

afterEach(cleanup);

const evidence = {
  file_id: "file_1",
  path: "src/auth.ts",
  start_line: 4,
  end_line: 9,
  reason: "선택 근거",
};

const brief: ChangeBrief = {
  id: "change_1",
  snapshot_id: "snap_1",
  analysis_version: "change-brief-v1",
  request_summary: "로그인 성공 후 이동 화면을 바꾸고 싶어요",
  selection: { file_id: "file_1", start_line: 4, end_line: 9 },
  candidate_locations: [{ title: "login", reason: "선택 위치", confidence: "verified", evidence }],
  confirmed_direct_impacts: [{ title: "화면 이동", description: "이동 대상이 연결됩니다.", relation_type: "NAVIGATES_TO", confidence: "verified", evidence: [evidence] }],
  possible_impacts_to_verify: [],
  unknown_boundaries: ["feature flag에 따른 동작"],
  risk_level: "medium",
  risk_rationale: "화면 이동 계약을 확인해야 합니다.",
  verification_steps: ["이동 흐름 테스트를 실행합니다."],
  rollback_guidance: ["독립 커밋을 되돌립니다."],
  evidence: [evidence],
  limitations: ["실제 패치는 적용하지 않았습니다."],
};

function renderPanel(overrides: Partial<Parameters<typeof ChangeBriefPanel>[0]> = {}) {
  const props = {
    cancelling: false,
    error: null,
    selection: { file_id: "file_1", start_line: 4, end_line: 9 },
    starting: false,
    task: null,
    onCancel: vi.fn(),
    onOpenEvidence: vi.fn(),
    onReset: vi.fn(),
    onStart: vi.fn(),
    ...overrides,
  };
  render(<ChangeBriefPanel {...props} />);
  return props;
}

describe("ChangeBriefPanel", () => {
  it("requires a code selection before starting", () => {
    renderPanel({ selection: null });
    fireEvent.change(screen.getByLabelText("변경 요청"), { target: { value: "이걸 바꾸고 싶어" } });
    expect((screen.getByRole("button", { name: "변경 영향 분석" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("submits the requested change and renders structured boundaries", () => {
    const props = renderPanel();
    fireEvent.change(screen.getByLabelText("변경 요청"), { target: { value: "이동 화면 변경" } });
    fireEvent.click(screen.getByRole("button", { name: "변경 영향 분석" }));
    expect(props.onStart).toHaveBeenCalledWith("이동 화면 변경");

    const completed: DeepTask = { id: "task_1", kind: "impact_analysis", status: "completed", progress: 100, message: "완료", result: brief };
    renderPanel({ task: completed });
    expect(screen.getByText("위험도 중간")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "확정된 직접 영향" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "확인이 필요한 영향" })).toBeTruthy();
    expect(screen.getByText("feature flag에 따른 동작")).toBeTruthy();
  });
});
