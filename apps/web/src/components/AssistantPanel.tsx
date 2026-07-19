"use client";

import { BookOpenText, Gauge, GraduationCap } from "lucide-react";
import { useState } from "react";

import type {
  ActivityAttemptSummary,
  AssessmentSession,
  ChatAnswer,
  Citation,
  CodeSelection,
  DeepTask,
  LearningFeedbackType,
  LearningActivity,
  LearningLesson,
  LearningModule,
  LearningPath,
  LearningSession,
  MasteryOverview,
  RemediationBranch,
  RemediationMode,
  Snapshot,
  SourceFile,
  StartHere,
  TeachingStyle,
} from "@/lib/api";
import type { RealtimeLearningSession } from "@/hooks/useRealtimeLearningSession";

import { AssessmentPanel } from "./AssessmentPanel";
import { LearningJourneyPanel } from "./LearningJourneyPanel";
import { MasteryPanel } from "./MasteryPanel";
import { StartHereContent } from "./StartHerePanel";
import { VoiceSessionDock } from "./voice/VoiceSessionDock";
import { DeepTaskTray } from "./voice/DeepTaskTray";

type Props = {
  snapshot: Snapshot | null;
  assessment: AssessmentSession | null;
  assessmentBusy: boolean;
  startHere: StartHere | null;
  file: SourceFile | null;
  selection: CodeSelection | null;
  answers: ChatAnswer[];
  asking: boolean;
  teachingStyle: TeachingStyle;
  learningPath: LearningPath | null;
  learningSession: LearningSession | null;
  remediation: RemediationBranch | null;
  journeyBusy: boolean;
  activity: LearningActivity | null;
  activityAttempt: ActivityAttemptSummary | null;
  activityBusy: boolean;
  masteryOverview: MasteryOverview | null;
  masteryLoading: boolean;
  voiceSession: RealtimeLearningSession;
  deepTask: DeepTask | null;
  deepTaskError: string | null;
  deepTaskStarting: boolean;
  deepTaskCancelling: boolean;
  onAssessmentAnswer: (itemId: string, answer: string) => void;
  onAssessmentSubmit: () => void;
  onAssessmentSkip: () => void;
  onTeachingStyleChange: (style: TeachingStyle) => void;
  onAsk: (question: string) => Promise<void>;
  onOpenFile: (fileId: string) => void;
  onOpenEvidence: (citation: Citation) => void;
  onOpenLines: (fileId: string, startLine: number, endLine: number) => void;
  onOpenLesson: (learningModule: LearningModule, lesson: LearningLesson) => void;
  onLearningFeedback: (
    lesson: LearningLesson,
    eventType: LearningFeedbackType,
  ) => void;
  onHelp: (mode: RemediationMode) => void;
  onCompleteHelp: () => void;
  onReplan: () => void;
  onSubmitActivity: (selectedChoiceId: string) => void;
  onDismissDeepTask: () => void;
  onCancelDeepTask: () => void;
};

export function AssistantPanel({
  snapshot,
  assessment,
  assessmentBusy,
  startHere,
  file,
  selection,
  answers,
  asking,
  teachingStyle,
  learningPath,
  learningSession,
  remediation,
  journeyBusy,
  activity,
  activityAttempt,
  activityBusy,
  masteryOverview,
  masteryLoading,
  voiceSession,
  deepTask,
  deepTaskError,
  deepTaskStarting,
  deepTaskCancelling,
  onAssessmentAnswer,
  onAssessmentSubmit,
  onAssessmentSkip,
  onTeachingStyleChange,
  onAsk,
  onOpenFile,
  onOpenEvidence,
  onOpenLines,
  onOpenLesson,
  onLearningFeedback,
  onHelp,
  onCompleteHelp,
  onReplan,
  onSubmitActivity,
  onDismissDeepTask,
  onCancelDeepTask,
}: Props) {
  const [mode, setMode] = useState<"journey" | "mastery" | "overview">("journey");
  const assessmentActive = Boolean(
    snapshot && (!assessment || assessment.status === "active"),
  );
  const currentLessonLabel = learningPath?.modules
    .flatMap((learningModule) => learningModule.lessons)
    .find((lesson) => lesson.id === learningSession?.current_lesson_id)?.title;

  return (
    <aside className="guide-panel assistant-panel">
      {assessmentActive ? (
        <AssessmentPanel
          assessment={assessment}
          busy={assessmentBusy}
          onAnswer={onAssessmentAnswer}
          onSkip={onAssessmentSkip}
          onSubmit={onAssessmentSubmit}
          snapshot={snapshot}
        />
      ) : snapshot ? (
        <>
          <div className="panel-toolbar assistant-toolbar">
            <div className="assistant-tabs" aria-label="학습 보기">
              <button
                className={mode === "journey" ? "is-active" : ""}
                onClick={() => setMode("journey")}
                type="button"
              >
                <GraduationCap aria-hidden size={14} /> 학습 여정
              </button>
              <button
                className={mode === "mastery" ? "is-active" : ""}
                onClick={() => setMode("mastery")}
                type="button"
              >
                <Gauge aria-hidden size={14} /> 이해도
              </button>
              <button
                className={mode === "overview" ? "is-active" : ""}
                onClick={() => setMode("overview")}
                type="button"
              >
                <BookOpenText aria-hidden size={14} /> 프로젝트 개요
              </button>
            </div>
          </div>
          <VoiceSessionDock
            currentLessonLabel={currentLessonLabel}
            disabled={!learningSession || asking}
            session={voiceSession}
          />
          <DeepTaskTray
            error={deepTaskError}
            isStarting={deepTaskStarting}
            isCancelling={deepTaskCancelling}
            onCancel={onCancelDeepTask}
            onDismiss={onDismissDeepTask}
            task={deepTask}
          />
          {mode === "journey" ? (
            <LearningJourneyPanel
              activity={activity}
              activityAttempt={activityAttempt}
              activityBusy={activityBusy}
              answers={answers}
              asking={asking}
              busy={journeyBusy}
              file={file}
              onAsk={onAsk}
              onCompleteHelp={onCompleteHelp}
              onFeedback={onLearningFeedback}
              onHelp={onHelp}
              onOpenEvidence={onOpenEvidence}
              onOpenLesson={onOpenLesson}
              onOpenLines={onOpenLines}
              onReplan={onReplan}
              onTeachingStyleChange={onTeachingStyleChange}
              onSubmitActivity={onSubmitActivity}
              path={learningPath}
              remediation={remediation}
              selection={selection}
              session={learningSession}
              teachingStyle={teachingStyle}
            />
          ) : mode === "mastery" ? (
            <MasteryPanel
              loading={masteryLoading}
              onOpenEvidence={onOpenEvidence}
              overview={masteryOverview}
            />
          ) : (
            <StartHereContent
              onOpenFile={onOpenFile}
              snapshot={snapshot}
              startHere={startHere}
            />
          )}
        </>
      ) : (
        <div className="panel-empty compact-empty">
          <span>분석할 GitHub 저장소를 입력하세요.</span>
        </div>
      )}
    </aside>
  );
}
