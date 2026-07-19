"use client";

import {
  ArrowRight,
  Check,
  ClipboardCheck,
  LoaderCircle,
  SkipForward,
} from "lucide-react";

import type { AssessmentSession, Snapshot } from "@/lib/api";

type Props = {
  snapshot: Snapshot | null;
  assessment: AssessmentSession | null;
  busy: boolean;
  onAnswer: (itemId: string, answer: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
};

const CATEGORY_LABELS: Record<string, string> = {
  goal: "학습 목표",
  preference: "설명 방식",
  self_report: "경험",
  objective: "개념 확인",
  pace: "학습 속도",
};

export function AssessmentPanel({
  snapshot,
  assessment,
  busy,
  onAnswer,
  onSubmit,
  onSkip,
}: Props) {
  if (!assessment) {
    return (
      <div className="assessment-loading">
        <LoaderCircle className="spin" aria-hidden size={18} />
        <div>
          <strong>맞춤 학습 준비 중</strong>
          <span>{snapshot ? "진단 문항을 구성하고 있습니다." : "저장소를 먼저 분석하세요."}</span>
        </div>
      </div>
    );
  }

  const question = assessment.questions.find((item) => !(item.id in assessment.answers));
  const progress = assessment.total_count
    ? Math.round((assessment.answered_count / assessment.total_count) * 100)
    : 0;

  return (
    <div className="assessment-panel">
      <header className="assessment-header">
        <div className="assessment-kicker">
          <ClipboardCheck aria-hidden size={16} />
          <span>맞춤 학습 진단</span>
        </div>
        <h2>내 눈높이에 맞는 코드 학습</h2>
        <div className="assessment-stack" aria-label="감지된 기술 스택">
          {assessment.detected_stack.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
        <div className="assessment-progress-copy">
          <span>
            {assessment.answered_count}/{assessment.total_count}
          </span>
          <small>{progress}%</small>
        </div>
        <div className="assessment-progress-track" aria-label={`진단 진행률 ${progress}%`}>
          <span style={{ width: `${progress}%` }} />
        </div>
      </header>

      {question ? (
        <section className="assessment-question" key={question.id}>
          <small>{CATEGORY_LABELS[question.category] ?? "배경지식"}</small>
          <h3>{question.prompt}</h3>
          <div className="assessment-choices">
            {question.choices.map((choice) => (
              <button
                disabled={busy}
                key={choice.value}
                onClick={() => onAnswer(question.id, choice.value)}
                type="button"
              >
                <span>{choice.label}</span>
                {busy ? (
                  <LoaderCircle className="spin" aria-hidden size={15} />
                ) : (
                  <ArrowRight aria-hidden size={15} />
                )}
              </button>
            ))}
          </div>
        </section>
      ) : (
        <section className="assessment-ready">
          <span className="assessment-ready-icon">
            <Check aria-hidden size={19} />
          </span>
          <h3>진단 응답 완료</h3>
          <p>분석이 끝나면 응답과 실제 코드 구조를 함께 사용해 학습 경로를 만듭니다.</p>
          <button disabled={busy} onClick={onSubmit} type="button">
            {busy ? <LoaderCircle className="spin" aria-hidden size={16} /> : <Check size={16} />}
            학습 경로 만들기
          </button>
        </section>
      )}

      <footer className="assessment-footer">
        <button disabled={busy} onClick={onSkip} type="button">
          <SkipForward aria-hidden size={14} /> 기본 설정으로 건너뛰기
        </button>
        {snapshot && snapshot.status !== "ready" ? (
          <span>저장소 분석과 함께 진행 중</span>
        ) : null}
      </footer>
    </div>
  );
}
