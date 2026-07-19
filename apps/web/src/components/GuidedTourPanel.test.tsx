import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Citation, GuidedPath, GuidedTourSession } from "@/lib/api";

import { GuidedTourPanel } from "./GuidedTourPanel";

const evidence: Citation = {
  evidence_id: "ev_1",
  source_type: "repository_code",
  snapshot_id: "snap_1",
  file_id: "file_1",
  path: "src/index.ts",
  language: "typescript",
  title: "src/index.ts#main",
  chunk_type: "symbol",
  start_line: 10,
  end_line: 20,
  preview: "export function main() {}",
  score: 1,
  retrievers: ["guided_path"],
};

const path: GuidedPath = {
  id: "path_1",
  snapshot_id: "snap_1",
  title: "핵심 코드 Tour",
  goal: "진입점부터 읽습니다.",
  difficulty: "beginner",
  path_version: "guided-tour-v1",
  generation_method: "deterministic-structure-v1",
  total_minutes: 6,
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
  steps: [
    {
      id: "step_1",
      ordinal: 1,
      step_type: "core_flow",
      title: "main 핵심 흐름",
      learning_objective: "입력과 반환을 찾습니다.",
      summary: "main을 읽습니다.",
      concept_ids: ["function"],
      checkpoint: { type: "self_check", prompt: "찾았나요?" },
      estimated_minutes: 3,
      evidence,
    },
    {
      id: "step_2",
      ordinal: 2,
      step_type: "test",
      title: "테스트 근거",
      learning_objective: "기대 동작을 확인합니다.",
      summary: "테스트를 읽습니다.",
      concept_ids: [],
      checkpoint: { type: "self_check", prompt: "확인했나요?" },
      estimated_minutes: 3,
      evidence: { ...evidence, evidence_id: "ev_2", path: "test/index.test.ts" },
    },
  ],
};

const session: GuidedTourSession = {
  id: "tour_1",
  path_id: "path_1",
  preferred_style: "beginner",
  status: "active",
  current_step_ordinal: 1,
  completed_step_ids: [],
  needs_help_step_ids: [],
  completed_count: 0,
  total_steps: 2,
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
};

describe("GuidedTourPanel", () => {
  it("shows the current step and sends grounded progress actions", () => {
    const onOpenStep = vi.fn();
    const onFeedback = vi.fn();
    const { container } = render(
      <GuidedTourPanel
        path={path}
        session={session}
        busy={false}
        onOpenStep={onOpenStep}
        onFeedback={onFeedback}
      />,
    );

    expect(container.textContent).toContain("0/2 단계");
    expect(container.textContent).toContain("src/index.ts");
    fireEvent.click(screen.getByRole("button", { name: "코드 열기" }));
    fireEvent.click(screen.getByRole("button", { name: "이해했어요" }));

    expect(onOpenStep).toHaveBeenCalledWith(path.steps[0]);
    expect(onFeedback).toHaveBeenCalledWith(path.steps[0], "understood");
  });
});
