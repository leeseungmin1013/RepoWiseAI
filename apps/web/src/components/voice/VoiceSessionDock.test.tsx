import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RealtimeLearningSession } from "@/hooks/useRealtimeLearningSession";

import { VoiceSessionDock } from "./VoiceSessionDock";

afterEach(cleanup);

function session(
  overrides: Partial<RealtimeLearningSession> = {},
): RealtimeLearningSession {
  return {
    status: "idle",
    connectionState: "new",
    error: null,
    interimTranscript: "",
    isSupported: true,
    isConnected: false,
    isTalking: false,
    start: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn(),
    startTalking: vi.fn(),
    endTalking: vi.fn(),
    sendEvent: vi.fn().mockReturnValue(true),
    speakVerifiedText: vi.fn().mockReturnValue(true),
    remoteAudioRef: vi.fn(),
    ...overrides,
  };
}

describe("VoiceSessionDock", () => {
  it("starts and stops a voice session", () => {
    const controller = session();
    const { rerender } = render(
      <VoiceSessionDock
        currentLessonLabel="비동기 함수 이해하기"
        session={controller}
      />,
    );

    expect(screen.getByText("현재 학습: 비동기 함수 이해하기")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "음성 대화 시작" }));
    expect(controller.start).toHaveBeenCalledOnce();

    const activeController = session({
      status: "ready",
      connectionState: "connected",
      isConnected: true,
    });
    rerender(<VoiceSessionDock session={activeController} />);
    fireEvent.click(screen.getByRole("button", { name: "음성 대화 종료" }));
    expect(activeController.stop).toHaveBeenCalledOnce();
  });

  it("supports pointer and keyboard push-to-talk", () => {
    const readyController = session({
      status: "ready",
      connectionState: "connected",
      isConnected: true,
    });
    const { rerender } = render(
      <VoiceSessionDock session={readyController} />,
    );

    const readyButton = screen.getByRole("button", { name: "누르고 말하기" });
    fireEvent.pointerDown(readyButton, { pointerId: 1 });
    expect(readyController.startTalking).toHaveBeenCalledOnce();

    const talkingController = session({
      status: "talking",
      connectionState: "connected",
      isConnected: true,
      isTalking: true,
    });
    rerender(<VoiceSessionDock session={talkingController} />);
    const talkingButton = screen.getByRole("button", {
      name: "말하기 종료: 버튼을 놓으세요",
    });
    fireEvent.pointerUp(talkingButton, { pointerId: 1 });
    expect(talkingController.endTalking).toHaveBeenCalledOnce();

    const keyboardController = session({
      status: "ready",
      connectionState: "connected",
      isConnected: true,
    });
    rerender(<VoiceSessionDock session={keyboardController} />);
    const keyboardButton = screen.getByRole("button", { name: "누르고 말하기" });
    fireEvent.keyDown(keyboardButton, { key: " ", repeat: false });
    expect(keyboardController.startTalking).toHaveBeenCalledOnce();
  });

  it("announces interim transcripts and connection errors", () => {
    render(
      <VoiceSessionDock
        session={
          session({
            status: "error",
            connectionState: "failed",
            error: new Error("연결 실패"),
            interimTranscript: "현재 코드가 하는 일은",
          })
        }
      />,
    );

    expect(screen.getByText("현재 코드가 하는 일은")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("연결 실패");
  });
});
