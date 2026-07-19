import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DeepTask } from "@/lib/api";

import { DeepTaskTray } from "./DeepTaskTray";

afterEach(cleanup);

const runningTask: DeepTask = {
  id: "deep_1",
  status: "reasoning",
  kind: "impact_analysis",
  progress: 62,
  message: "호출 관계의 변경 영향을 분석하고 있어요.",
};

describe("DeepTaskTray", () => {
  it("shows progress for a running task", () => {
    render(
      <DeepTaskTray
        error={null}
        isCancelling={false}
        isStarting={false}
        onCancel={vi.fn()}
        onDismiss={vi.fn()}
        task={runningTask}
      />,
    );

    expect(screen.getByText("영향 분석")).toBeTruthy();
    expect(screen.getByText("호출 관계의 변경 영향을 분석하고 있어요.")).toBeTruthy();
    expect(
      screen.getByRole("progressbar", { name: "심층 작업 진행률" }).getAttribute(
        "aria-valuenow",
      ),
    ).toBe("62");
  });

  it("shows terminal errors and allows dismissal", () => {
    const onDismiss = vi.fn();
    render(
      <DeepTaskTray
        error={null}
        isCancelling={false}
        isStarting={false}
        onCancel={vi.fn()}
        onDismiss={onDismiss}
        task={{
          ...runningTask,
          status: "failed",
          progress: 100,
          error: {
            code: "verification_failed",
            message: "검증에 실패했습니다.",
          },
        }}
      />,
    );

    expect(screen.getByRole("alert").textContent).toContain("검증에 실패했습니다.");
    fireEvent.click(
      screen.getByRole("button", { name: "심층 작업 알림 닫기" }),
    );
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("renders verified official material cards", () => {
    render(
      <DeepTaskTray
        error={null}
        isCancelling={false}
        isStarting={false}
        onCancel={vi.fn()}
        onDismiss={vi.fn()}
        task={{
          id: "deep_research",
          status: "completed",
          kind: "research_materials",
          progress: 100,
          message: "검증된 공식 학습자료를 찾았습니다.",
          result: {
            answer: "공식 문서를 학습 순서에 맞춰 골랐습니다.",
            voice_summary: "공식 문서를 찾았습니다.",
            generation_mode: "openai_web_search",
            model_name: "gpt-5.6-terra",
            sources: [{
              title: "FastAPI Tutorial",
              publisher: "FastAPI",
              url: "https://fastapi.tiangolo.com/tutorial/",
              difficulty: "beginner",
              estimated_minutes: 30,
              recommendation_reason: "현재 API 구조를 이해하기 좋습니다.",
              checked_at: "2026-07-13T00:00:00Z",
            }],
          },
        }}
      />,
    );

    const link = screen.getByRole("link", { name: "FastAPI Tutorial" });
    expect(link.getAttribute("href")).toBe("https://fastapi.tiangolo.com/tutorial/");
    expect(screen.getByText("약 30분")).toBeTruthy();
    expect(screen.getByText("입문")).toBeTruthy();
  });
});
