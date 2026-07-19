import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  Citation,
  LearningActivity,
  LearningPath,
  LearningSession,
} from "@/lib/api";

import { LearningJourneyPanel } from "./LearningJourneyPanel";

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
  retrievers: ["adaptive_curriculum"],
};

const path: LearningPath = {
  id: "path_1",
  snapshot_id: "snap_1",
  learner_profile_id: "learner_1",
  title: "sample 전체 이해 경로",
  goal: "understand_whole_project",
  status: "ready",
  path_version: "adaptive-curriculum-v1",
  generation_method: "verified-structure-v1",
  coverage: { feature_flow: "covered" },
  model_metadata: {},
  estimated_minutes: 20,
  total_modules: 1,
  total_lessons: 1,
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
  modules: [
    {
      id: "module_1",
      ordinal: 1,
      module_type: "feature_flow",
      title: "핵심 기능 흐름",
      objective: "입력과 결과를 따라갑니다.",
      required: true,
      estimated_minutes: 20,
      coverage_keys: ["feature_flow"],
      lessons: [
        {
          id: "lesson_1",
          ordinal: 1,
          lesson_type: "code_flow",
          title: "main 실행 흐름",
          objective: "main의 실행 순서를 설명합니다.",
          required_concept_ids: ["function"],
          checkpoint: { prompt: "실행 순서를 설명할 수 있나요?" },
          estimated_minutes: 5,
          optional: false,
          steps: [
            {
              id: "step_1",
              ordinal: 1,
              step_type: "code",
              title: "main",
              instruction: "위에서 아래로 호출을 따라가세요.",
              concept_id: null,
              evidence,
              metadata: {},
            },
          ],
        },
      ],
    },
  ],
};

const session: LearningSession = {
  id: "session_1",
  snapshot_id: "snap_1",
  learner_profile_id: "learner_1",
  path_id: "path_1",
  chat_session_id: "chat_1",
  current_module_id: "module_1",
  current_lesson_id: "lesson_1",
  current_step_id: "step_1",
  completed_lesson_ids: [],
  return_stack: [],
  current_selection: { file_id: "file_1", start_line: 10, end_line: 20 },
  focus_concept_ids: ["function"],
  status: "active",
  completed_count: 0,
  total_lessons: 1,
  created_at: "2026-07-12T00:00:00Z",
  updated_at: "2026-07-12T00:00:00Z",
};

const activity: LearningActivity = {
  id: "activity_1",
  step_id: "step_1",
  activity_type: "predict_next_call",
  prompt: "가장 먼저 호출되는 함수는 무엇인가요?",
  choices: [
    { id: "choice_1", label: "loadData" },
    { id: "choice_2", label: "saveData" },
  ],
  concept_ids: ["function", "call"],
  evidence,
  generator_version: "grounded-checkpoint-v1",
  latest_attempt: null,
};

describe("LearningJourneyPanel", () => {
  it("keeps lesson help, progress, and grounded questions in one view", () => {
    const onHelp = vi.fn();
    const onFeedback = vi.fn();
    const onSubmitActivity = vi.fn();
    render(
      <LearningJourneyPanel
        activity={activity}
        activityAttempt={null}
        activityBusy={false}
        answers={[]}
        asking={false}
        busy={false}
        file={null}
        onAsk={vi.fn()}
        onCompleteHelp={vi.fn()}
        onFeedback={onFeedback}
        onHelp={onHelp}
        onOpenEvidence={vi.fn()}
        onOpenLesson={vi.fn()}
        onOpenLines={vi.fn()}
        onReplan={vi.fn()}
        onTeachingStyleChange={vi.fn()}
        onSubmitActivity={onSubmitActivity}
        path={path}
        remediation={null}
        selection={null}
        session={session}
        teachingStyle="beginner"
      />,
    );

    expect(screen.getByText("0/1 레슨")).toBeTruthy();
    expect(screen.getByText("현재 레슨에 질문")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "배경지식" }));
    fireEvent.click(screen.getByRole("button", { name: "loadData" }));
    fireEvent.click(screen.getByRole("button", { name: "이해했어요" }));

    expect(onHelp).toHaveBeenCalledWith("prerequisite");
    expect(onSubmitActivity).toHaveBeenCalledWith("choice_1");
    expect(onFeedback).toHaveBeenCalledWith(path.modules[0].lessons[0], "understood");
  });
});
