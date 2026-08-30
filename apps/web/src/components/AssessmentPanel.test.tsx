import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AssessmentSession, Snapshot } from "@/lib/api";

import { AssessmentPanel } from "./AssessmentPanel";

const snapshot: Snapshot = {
  id: "snap_1",
  repository_id: "repo_1",
  branch: "main",
  commit_sha: null,
  status: "analyzing",
  parser_version: "tree-sitter-v1",
  index_version: "structure-v1",
  file_count: 0,
  symbol_count: 0,
  edge_count: 0,
  chunk_count: 0,
  total_bytes: 0,
  embedding_model: "local-hash-v1",
  error_message: null,
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
  job: null,
};

const assessment: AssessmentSession = {
  id: "asm_1",
  snapshot_id: "snap_1",
  learner_profile_id: "learner_1",
  status: "active",
  detected_stack: ["TypeScript", "React"],
  assessment_version: "stack-diagnostic-v1",
  questions: [
    {
      id: "goal",
      category: "goal",
      prompt: "가장 큰 목표는 무엇인가요?",
      choices: [{ value: "learn", label: "코드를 배우고 싶어요" }],
      concept_id: null,
      stack_requirement: null,
    },
  ],
  answers: {},
  answered_count: 0,
  total_count: 1,
  created_at: "2026-07-12T00:00:00Z",
  expires_at: "2026-07-12T00:15:00Z",
  submitted_at: null,
  skipped_at: null,
  timed_out_at: null,
  profile: {
    id: "learner_1",
    anonymous_key: "learner-key",
    goal: "understand_whole_project",
    preferred_explanation: ["line_by_line"],
    pace: "careful",
    background: {},
    concept_mastery: {},
    assessment_version: "stack-diagnostic-v1",
    created_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
  },
};

describe("AssessmentPanel", () => {
  it("shows detected stack and records a selected answer", () => {
    const onAnswer = vi.fn();
    render(
      <AssessmentPanel
        assessment={assessment}
        busy={false}
        onAnswer={onAnswer}
        onSkip={vi.fn()}
        onSubmit={vi.fn()}
        snapshot={snapshot}
      />,
    );

    expect(screen.getByText("TypeScript")).toBeTruthy();
    expect(screen.getByText("React")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "코드를 배우고 싶어요" }));

    expect(onAnswer).toHaveBeenCalledWith("goal", "learn");
  });
});
