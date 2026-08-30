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

  it("renders completed analysis results with citations", () => {
    const onOpenEvidence = vi.fn();

    render(
      <DeepTaskTray
        error={null}
        isCancelling={false}
        isStarting={false}
        onCancel={vi.fn()}
        onDismiss={vi.fn()}
        onOpenEvidence={onOpenEvidence}
        task={{
          id: "deep_done",
          status: "completed",
          kind: "deep_explanation",
          progress: 100,
          message: "심층 답변이 준비되었습니다.",
          result: {
            id: "msg_1",
            session_id: "chat_1",
            question: "이 함수가 뭘 하나요?",
            answer: "이 함수는 입력을 검증하고 결과를 정리합니다.",
            status: "grounded",
            intent: "explain",
            retrieval_run_id: "run_1",
            citations: [
              {
                evidence_id: "ev_1",
                source_type: "repository_code",
                snapshot_id: "snap_1",
                file_id: "file_1",
                path: "src/app.ts",
                language: "ts",
                title: "app.ts",
                chunk_type: "symbol",
                start_line: 10,
                end_line: 24,
                preview: "핵심 처리 로직",
                score: 0.91,
                retrievers: ["hybrid"],
              },
            ],
            follow_up: "이 함수의 예외 처리도 볼까요?",
            voice_summary: "입력 검증과 결과 정리를 담당합니다.",
            generation_mode: "openai",
            model_name: "gpt-5.6-terra",
            created_at: "2026-07-19T00:00:00Z",
          },
        }}
      />,
    );

    expect(screen.getByText("분석 결과")).toBeTruthy();
    expect(screen.getByText("이 함수는 입력을 검증하고 결과를 정리합니다.")).toBeTruthy();
    expect(screen.getByText("입력 검증과 결과 정리를 담당합니다.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "src/app.ts L10-24" }));
    expect(onOpenEvidence).toHaveBeenCalledOnce();
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
            answer: "공식 문서를 최신 기준에 맞춰 정리했습니다.",
            voice_summary: "공식 문서를 찾았습니다.",
            generation_mode: "openai_web_search",
            model_name: "gpt-5.6-terra",
            sources: [
              {
                title: "FastAPI Tutorial",
                publisher: "FastAPI",
                url: "https://fastapi.tiangolo.com/tutorial/",
                difficulty: "beginner",
                estimated_minutes: 30,
                recommendation_reason: "현재 API 구조를 이해하기 좋습니다.",
                checked_at: "2026-07-13T00:00:00Z",
              },
            ],
          },
        }}
      />,
    );

    const link = screen.getByRole("link", { name: "FastAPI Tutorial" });
    expect(link.getAttribute("href")).toBe("https://fastapi.tiangolo.com/tutorial/");
    expect(screen.getByText("약 30분")).toBeTruthy();
    expect(screen.getByText("입문")).toBeTruthy();
  });

  it("shows a support trace for a failed task", () => {
    render(
      <DeepTaskTray
        error={null}
        isCancelling={false}
        isStarting={false}
        onCancel={vi.fn()}
        onDismiss={vi.fn()}
        task={{
          id: "deep_failed",
          status: "failed",
          kind: "deep_explanation",
          progress: 100,
          message: "심층 작업을 완료하지 못했습니다.",
          trace_id: "request-support-123",
          error: {
            code: "worker_terminated",
            message: "작업 처리 중 연결이 종료되었습니다.",
          },
        }}
      />,
    );

    expect(screen.getByRole("alert").textContent).toContain(
      "작업 처리 중 연결이 종료되었습니다.",
    );
    expect(screen.getByText("지원 ID: request-support-123")).toBeTruthy();
  });});
