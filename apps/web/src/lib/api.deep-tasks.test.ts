import { afterEach, describe, expect, it, vi } from "vitest";

import type { DeepTask } from "./api";
import { api } from "./api";

const queuedTask: DeepTask = {
  id: "deep/1",
  status: "queued",
  kind: "research_materials",
  progress: 0,
  message: "대기 중",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("deep task API client", () => {
  it("posts the fixed request contract with an idempotency key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(queuedTask), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      kind: "research_materials" as const,
      prompt: "공식 자료를 조사해 줘",
      selection: null,
      modality: "text" as const,
    };

    await api.createDeepTask("learning/session", input, "idem-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/learning-sessions/learning%2Fsession/deep-tasks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(input),
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "Idempotency-Key": "idem-1",
        }),
      }),
    );
  });

  it("builds a header-free EventSource URL with an encoded task id", () => {
    expect(api.deepTaskEventsUrl("deep/1")).toBe(
      "http://localhost:8000/api/deep-tasks/deep%2F1/events",
    );
  });

  it("posts cancellation for an encoded task id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...queuedTask, status: "cancelled" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.cancelDeepTask("deep/1");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/deep-tasks/deep%2F1/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
