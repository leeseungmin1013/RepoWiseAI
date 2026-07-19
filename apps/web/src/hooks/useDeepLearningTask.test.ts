import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatAnswer, DeepTask, DeepTaskRequest } from "@/lib/api";

import {
  type DeepTaskEventSource,
  useDeepLearningTask,
} from "./useDeepLearningTask";

class FakeEventSource implements DeepTaskEventSource {
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();
  private listeners = new Map<string, Set<EventListener>>();

  addEventListener(type: string, listener: EventListener) {
    const listeners = this.listeners.get(type) ?? new Set<EventListener>();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: EventListener) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string, task: DeepTask) {
    const event = new MessageEvent(type, { data: JSON.stringify(task) });
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }

  emitHeartbeat() {
    const event = new MessageEvent("heartbeat", { data: "{}" });
    this.listeners.get("heartbeat")?.forEach((listener) => listener(event));
  }
}

const request: DeepTaskRequest = {
  kind: "impact_analysis",
  prompt: "이 변경의 전체 영향을 분석해 줘",
  selection: null,
  modality: "voice",
};

const answer: ChatAnswer = {
  id: "answer_1",
  session_id: "chat_1",
  question: request.prompt,
  answer: "두 소비자가 이 계약을 사용합니다.",
  status: "grounded",
  intent: "impact",
  retrieval_run_id: "run_1",
  citations: [],
  follow_up: null,
  voice_summary: "계약 소비자 두 곳에 영향이 있습니다.",
  generation_mode: "openai",
  model_name: "configured-deep-model",
  created_at: "2026-07-13T00:00:00Z",
};

const queuedTask: DeepTask = {
  id: "deep_1",
  status: "queued",
  kind: request.kind,
  progress: 0,
  message: "대기 중",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useDeepLearningTask", () => {
  it("consumes custom SSE progress events and completes exactly once", async () => {
    const source = new FakeEventSource();
    const createTask = vi.fn().mockResolvedValue(queuedTask);
    const onCompleted = vi.fn();
    const { result } = renderHook(() =>
      useDeepLearningTask({
        createTask,
        createEventSource: () => source,
        eventsUrl: (taskId) => `/api/deep-tasks/${taskId}/events`,
        getTask: vi.fn(),
        onCompleted,
      }),
    );

    await act(async () => {
      await Promise.all([
        result.current.start("learning_1", request),
        result.current.start("learning_1", request),
      ]);
    });

    expect(createTask).toHaveBeenCalledOnce();
    expect(createTask).toHaveBeenCalledWith(
      "learning_1",
      request,
      expect.any(String),
    );

    act(() => {
      source.emit("running", {
        ...queuedTask,
        status: "running",
        progress: 45,
        message: "영향 범위를 분석 중",
      });
      source.emitHeartbeat();
    });
    expect(result.current.task?.status).toBe("running");
    expect(result.current.task?.progress).toBe(45);

    const completedTask: DeepTask = {
      ...queuedTask,
      status: "completed",
      progress: 100,
      message: "분석 완료",
      result: answer,
    };
    act(() => source.emit("completed", completedTask));
    act(() => source.emit("completed", completedTask));

    expect(result.current.task?.status).toBe("completed");
    expect(onCompleted).toHaveBeenCalledOnce();
    expect(onCompleted).toHaveBeenCalledWith(answer, completedTask, request);
    expect(source.close).toHaveBeenCalledOnce();
  });

  it("falls back to polling when EventSource cannot be created", async () => {
    const completedTask: DeepTask = {
      ...queuedTask,
      status: "completed",
      progress: 100,
      message: "완료",
      result: answer,
    };
    const getTask = vi.fn().mockResolvedValue(completedTask);
    const onCompleted = vi.fn();
    const { result } = renderHook(() =>
      useDeepLearningTask({
        createTask: vi.fn().mockResolvedValue(queuedTask),
        createEventSource: () => {
          throw new Error("SSE unavailable");
        },
        eventsUrl: (taskId) => `/api/deep-tasks/${taskId}/events`,
        getTask,
        onCompleted,
        pollIntervalMs: 5,
      }),
    );

    await act(async () => {
      await result.current.start("learning_1", request);
    });

    await waitFor(() => expect(result.current.task?.status).toBe("completed"));
    expect(getTask).toHaveBeenCalledWith("deep_1");
    expect(onCompleted).toHaveBeenCalledOnce();
  });

  it("closes an active SSE connection on unmount", async () => {
    const source = new FakeEventSource();
    const { result, unmount } = renderHook(() =>
      useDeepLearningTask({
        createTask: vi.fn().mockResolvedValue(queuedTask),
        createEventSource: () => source,
        eventsUrl: (taskId) => `/api/deep-tasks/${taskId}/events`,
        getTask: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.start("learning_1", request);
    });
    unmount();

    expect(source.close).toHaveBeenCalledOnce();
  });

  it("reuses the idempotency key when a create response is lost", async () => {
    const source = new FakeEventSource();
    const createTask = vi
      .fn()
      .mockRejectedValueOnce(new Error("network interrupted"))
      .mockResolvedValueOnce(queuedTask);
    const { result } = renderHook(() =>
      useDeepLearningTask({
        createTask,
        createEventSource: () => source,
        eventsUrl: (taskId) => `/api/deep-tasks/${taskId}/events`,
        getTask: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.start("learning_1", request);
    });
    await act(async () => {
      await result.current.start("learning_1", request);
    });

    expect(createTask).toHaveBeenCalledTimes(2);
    expect(createTask.mock.calls[0][2]).toBe(createTask.mock.calls[1][2]);
  });

  it("cancels the active task and closes its progress transport", async () => {
    const source = new FakeEventSource();
    const cancelledTask: DeepTask = {
      ...queuedTask,
      status: "cancelled",
      progress: 100,
      message: "심층 작업을 취소했습니다.",
    };
    const cancelTask = vi.fn().mockResolvedValue(cancelledTask);
    const { result } = renderHook(() =>
      useDeepLearningTask({
        createTask: vi.fn().mockResolvedValue(queuedTask),
        cancelTask,
        createEventSource: () => source,
        eventsUrl: (taskId) => `/api/deep-tasks/${taskId}/events`,
        getTask: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.start("learning_1", request);
    });
    await act(async () => {
      await result.current.cancel();
    });

    expect(cancelTask).toHaveBeenCalledWith("deep_1");
    expect(result.current.task?.status).toBe("cancelled");
    expect(source.close).toHaveBeenCalledOnce();
  });
});
