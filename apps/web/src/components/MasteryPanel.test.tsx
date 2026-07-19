import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MasteryOverview } from "@/lib/api";

import { MasteryPanel } from "./MasteryPanel";

const overview: MasteryOverview = {
  profile_id: "learn_1",
  graph_version: "ts-web-concepts-v1",
  summary: {
    ready: 0,
    developing: 1,
    needs_review: 0,
    unknown: 16,
    total: 17,
  },
  concepts: [
    {
      concept_id: "function",
      display_name: "함수",
      description: "입력과 출력을 하나의 호출 단위로 묶습니다.",
      domain: "syntax",
      difficulty: "beginner",
      score: 0.62,
      confidence: 0.7,
      state: "developing",
      source: "activity_attempt:attempt_1",
      prerequisite_ids: ["variable"],
      event_count: 1,
      last_event_at: "2026-07-12T10:00:00Z",
    },
  ],
  recent_events: [
    {
      id: "event_1",
      learner_profile_id: "learn_1",
      learning_session_id: "session_1",
      concept_id: "function",
      event_type: "activity_correct",
      source_type: "activity_attempt",
      source_id: "attempt_1",
      previous_score: 0.5,
      new_score: 0.62,
      previous_confidence: 0.5,
      new_confidence: 0.65,
      evidence: {
        evidence_id: "ev_1",
        snapshot_id: "snap_1",
        file_id: "file_1",
        path: "src/index.ts",
        language: "typescript",
        title: "src/index.ts#main",
        chunk_type: "symbol",
        start_line: 10,
        end_line: 12,
        preview: "return main();",
      },
      policy_version: "mastery-policy-v1",
      created_at: "2026-07-12T10:00:00Z",
    },
  ],
};

describe("MasteryPanel", () => {
  it("shows concept state and opens event evidence", () => {
    const onOpenEvidence = vi.fn();
    render(
      <MasteryPanel
        loading={false}
        onOpenEvidence={onOpenEvidence}
        overview={overview}
      />,
    );

    expect(screen.getByText("함수")).toBeTruthy();
    expect(screen.getAllByText("학습 중")).toHaveLength(2);
    expect(screen.getByText("이해도 62")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "function 근거 코드 열기" }));

    expect(onOpenEvidence).toHaveBeenCalledWith(
      expect.objectContaining({ path: "src/index.ts", start_line: 10 }),
    );
  });
});
