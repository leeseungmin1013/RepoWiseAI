"use client";

import {
  Braces,
  Check,
  CheckCircle2,
  CircleHelp,
  Clock3,
  LoaderCircle,
  LockKeyhole,
  Route,
} from "lucide-react";

import type {
  GuidedFeedbackType,
  GuidedPath,
  GuidedStep,
  GuidedTourSession,
} from "@/lib/api";

type Props = {
  path: GuidedPath | null;
  session: GuidedTourSession | null;
  busy: boolean;
  onOpenStep: (step: GuidedStep) => void;
  onFeedback: (step: GuidedStep, eventType: GuidedFeedbackType) => void;
};

const STEP_LABELS: Record<GuidedStep["step_type"], string> = {
  orientation: "시작점",
  core_flow: "핵심 흐름",
  supporting_flow: "연결 흐름",
  error_path: "예외 흐름",
  test: "테스트",
};

export function GuidedTourPanel({ path, session, busy, onOpenStep, onFeedback }: Props) {
  if (!path || !session) {
    return (
      <div className="panel-empty compact-empty">
        <LoaderCircle className={path ? "spin" : ""} aria-hidden size={17} />
        <span>{path ? "학습 진행을 준비 중입니다." : "분석 후 코드 Tour가 생성됩니다."}</span>
      </div>
    );
  }

  const completed = new Set(session.completed_step_ids);
  const needsHelp = new Set(session.needs_help_step_ids);
  const isFinished = session.status === "completed";
  const progress = path.steps.length
    ? Math.round((session.completed_count / path.steps.length) * 100)
    : 0;

  return (
    <div className="tour-scroll">
      <section className="tour-overview">
        <div className="tour-kicker">
          <Route aria-hidden size={15} />
          <span>Guided Code Tour</span>
        </div>
        <h2>{path.title}</h2>
        <p>{path.goal}</p>
        <div className="tour-progress-copy">
          <span>
            {session.completed_count}/{path.steps.length} 단계
          </span>
          <small>
            <Clock3 aria-hidden size={12} /> 약 {path.total_minutes}분
          </small>
        </div>
        <div className="tour-progress-track" aria-label={`Tour progress ${progress}%`}>
          <span style={{ width: `${progress}%` }} />
        </div>
      </section>

      {isFinished ? (
        <div className="tour-complete" role="status">
          <CheckCircle2 aria-hidden size={18} />
          <div>
            <strong>핵심 코드 Tour 완료</strong>
            <span>이제 관심 있는 단계의 코드를 다시 열거나 질문으로 확장할 수 있습니다.</span>
          </div>
        </div>
      ) : null}

      <ol className="tour-step-list">
        {path.steps.map((step) => {
          const isCompleted = completed.has(step.id);
          const isCurrent = !isFinished && step.ordinal === session.current_step_ordinal;
          const isLocked = !isCompleted && !isCurrent && !isFinished;
          const hadDifficulty = needsHelp.has(step.id);
          return (
            <li
              className={`${isCurrent ? "is-current" : ""} ${isCompleted ? "is-completed" : ""}`}
              key={step.id}
            >
              <div className="tour-step-rail" aria-hidden>
                <span>
                  {isCompleted ? (
                    <Check size={13} />
                  ) : isLocked ? (
                    <LockKeyhole size={11} />
                  ) : (
                    step.ordinal
                  )}
                </span>
              </div>
              <div className="tour-step-content">
                <div className="tour-step-heading">
                  <div>
                    <small>{STEP_LABELS[step.step_type]}</small>
                    <strong>{step.title}</strong>
                  </div>
                  <span>{step.estimated_minutes}분</span>
                </div>

                {isCurrent || isFinished ? (
                  <>
                    <p>{step.learning_objective}</p>
                    <div className="tour-evidence-line" title={step.evidence.path}>
                      <Braces aria-hidden size={13} />
                      <span>{step.evidence.path}</span>
                      <small>
                        L{step.evidence.start_line}
                        {step.evidence.end_line !== step.evidence.start_line
                          ? `-${step.evidence.end_line}`
                          : ""}
                      </small>
                    </div>
                    {step.concept_ids.length ? (
                      <div className="tour-concepts">
                        {step.concept_ids.map((concept) => (
                          <span key={concept}>{concept.replaceAll("_", " ")}</span>
                        ))}
                      </div>
                    ) : null}
                    {isCurrent ? (
                      <div className="tour-step-actions">
                        <button
                          className="tour-open-button"
                          disabled={busy}
                          onClick={() => onOpenStep(step)}
                          type="button"
                        >
                          <Braces aria-hidden size={14} /> 코드 열기
                        </button>
                        <button
                          className={hadDifficulty ? "is-selected" : ""}
                          disabled={busy}
                          onClick={() => onFeedback(step, "needs_help")}
                          type="button"
                        >
                          <CircleHelp aria-hidden size={14} /> 어려워요
                        </button>
                        <button
                          className="tour-understood-button"
                          disabled={busy}
                          onClick={() => onFeedback(step, "understood")}
                          type="button"
                        >
                          {busy ? (
                            <LoaderCircle className="spin" aria-hidden size={14} />
                          ) : (
                            <Check aria-hidden size={14} />
                          )}
                          이해했어요
                        </button>
                      </div>
                    ) : (
                      <button
                        className="tour-reopen-button"
                        onClick={() => onOpenStep(step)}
                        type="button"
                      >
                        <Braces aria-hidden size={13} /> 코드 다시 보기
                      </button>
                    )}
                  </>
                ) : (
                  <p className="tour-step-preview">앞 단계를 마치면 이 코드를 함께 읽습니다.</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
