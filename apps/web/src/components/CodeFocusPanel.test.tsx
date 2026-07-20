import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CodeExplanation } from "@/lib/api";

import { CodeFocusPanel } from "./CodeFocusPanel";

const evidence = {
  file_id: "file-focus",
  path: "src/components/AskButton.tsx",
  start_line: 3,
  end_line: 7,
  reason: "선택 범위",
};

const explanation: CodeExplanation = {
  id: "focus-1",
  snapshot_id: "snap-1",
  analysis_version: "minimum-sufficient-v1",
  depth: "minimum",
  selection: {
    file_id: evidence.file_id,
    start_line: evidence.start_line,
    end_line: evidence.end_line,
  },
  purpose: "submit 함수 안에서 맡은 동작을 구현합니다.",
  executes_when: "사용자가 질문 보내기를 누를 때 실행됩니다.",
  input: "POST /api/ask 요청에 필요한 화면 상태",
  output_or_side_effect: "서버 요청을 보내고 answer 상태를 바꿉니다.",
  project_role: "사용자 행동을 처리하는 화면 로직",
  change_impact: "질문 전송과 화면 상태가 직접 달라질 수 있습니다.",
  required_concepts: ["비동기 실행과 await", "HTTP 요청"],
  related_steps: [
    {
      relation_type: "REQUESTS",
      title: "서버에 요청을 보냅니다",
      target: "/api/ask",
      confidence: "verified",
      evidence: { ...evidence, start_line: 5, end_line: 5 },
    },
  ],
  syntax_segments: [],
  analogy: null,
  confidence: "verified",
  evidence: [evidence],
  limitations: ["실제 런타임 값은 확인하지 않았습니다."],
};

afterEach(cleanup);

describe("CodeFocusPanel", () => {
  it("starts a minimum explanation for a selected range", () => {
    const onExplain = vi.fn();
    render(
      <CodeFocusPanel
        error={null}
        explanation={null}
        loading={false}
        onExplain={onExplain}
        onOpenEvidence={vi.fn()}
        onRequestChangeBrief={vi.fn()}
        selection={explanation.selection}
      />,
    );

    expect(screen.getByText("L3–L7 범위의 역할과 결과부터 설명합니다.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "선택 범위 설명" }));
    expect(onExplain).toHaveBeenCalledWith("minimum");
  });

  it("shows the six minimum-sufficient facts and requests deeper views explicitly", () => {
    const onExplain = vi.fn();
    const onOpenEvidence = vi.fn();
    render(
      <CodeFocusPanel
        error={null}
        explanation={explanation}
        loading={false}
        onExplain={onExplain}
        onOpenEvidence={onOpenEvidence}
        onRequestChangeBrief={vi.fn()}
        selection={explanation.selection}
      />,
    );

    expect(screen.getByText(explanation.purpose)).toBeTruthy();
    expect(screen.getByText(explanation.executes_when)).toBeTruthy();
    expect(screen.getByText(explanation.input)).toBeTruthy();
    expect(screen.getByText(explanation.output_or_side_effect)).toBeTruthy();
    expect(screen.getByText(explanation.project_role)).toBeTruthy();
    expect(screen.getByText(explanation.change_impact)).toBeTruthy();
    expect(screen.getByText("비동기 실행과 await")).toBeTruthy();
    expect(screen.getByText("이 범위에서 확인된 다음 연결")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "문법" }));
    expect(onExplain).toHaveBeenCalledWith("syntax");

    fireEvent.click(screen.getByRole("button", { name: /AskButton\.tsx/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(evidence);
    fireEvent.click(screen.getByRole("button", { name: /서버에 요청을 보냅니다/ }));
    expect(onOpenEvidence).toHaveBeenCalledWith(explanation.related_steps[0].evidence);
  });
});
