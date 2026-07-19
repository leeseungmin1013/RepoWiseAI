"use client";

import type { DeepTask, DeepTaskKind, DeepTaskStatus } from "@/lib/api";

import styles from "./DeepTaskTray.module.css";

type DeepTaskTrayProps = {
  task: DeepTask | null;
  error: string | null;
  isStarting: boolean;
  isCancelling: boolean;
  onCancel: () => void;
  onDismiss: () => void;
};

const kindLabels: Record<DeepTaskKind, string> = {
  deep_explanation: "심층 설명",
  impact_analysis: "영향 분석",
  roadmap_proposal: "학습 로드맵",
  research_materials: "학습 자료 조사",
};

const statusLabels: Record<DeepTaskStatus, string> = {
  queued: "대기 중",
  running: "심층 작업 중",
  retrieving: "근거 탐색 중",
  reasoning: "심층 추론 중",
  verifying: "답변 검증 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
};

export function DeepTaskTray({
  task,
  error,
  isStarting,
  isCancelling,
  onCancel,
  onDismiss,
}: DeepTaskTrayProps) {
  if (!task && !error && !isStarting) return null;

  const progress = Math.max(0, Math.min(100, Math.round(task?.progress ?? 0)));
  const terminal =
    task?.status === "completed" ||
    task?.status === "failed" ||
    task?.status === "cancelled";
  const displayError = task?.error?.message ?? error;
  const researchResult =
    task?.kind === "research_materials" &&
    task.result &&
    "sources" in task.result
      ? task.result
      : null;

  return (
    <section aria-label="심층 학습 작업" className={styles.tray}>
      <div className={styles.heading}>
        <div>
          <strong>{task ? kindLabels[task.kind] : "심층 작업"}</strong>
          <span>{task ? statusLabels[task.status] : "작업 요청 중"}</span>
        </div>
        {task && !terminal ? (
          <button disabled={isCancelling} onClick={onCancel} type="button">
            {isCancelling ? "취소 중" : "작업 취소"}
          </button>
        ) : terminal || (!task && error) ? (
          <button aria-label="심층 작업 알림 닫기" onClick={onDismiss} type="button">
            닫기
          </button>
        ) : null}
      </div>

      {task ? (
        <>
          <div
            aria-label="심층 작업 진행률"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={progress}
            className={styles.progressTrack}
            role="progressbar"
          >
            <span style={{ width: `${progress}%` }} />
          </div>
          <div aria-live="polite" className={styles.message} role="status">
            <span>{task.message || statusLabels[task.status]}</span>
            <small>{progress}%</small>
          </div>
        </>
      ) : isStarting ? (
        <div aria-live="polite" className={styles.message} role="status">
          심층 작업을 준비하고 있어요.
        </div>
      ) : null}

      {displayError ? (
        <div className={styles.error} role="alert">
          {displayError}
        </div>
      ) : null}

      {researchResult ? (
        <div className={styles.researchResults}>
          <p>{researchResult.answer}</p>
          <ul aria-label="공식 학습자료 목록">
            {researchResult.sources.map((source) => (
              <li key={source.url}>
                <a href={source.url} rel="noreferrer" target="_blank">
                  {source.title}
                </a>
                <div>
                  <span>{source.publisher}</span>
                  <span>{difficultyLabel(source.difficulty)}</span>
                  <span>약 {source.estimated_minutes}분</span>
                </div>
                <p>{source.recommendation_reason}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function difficultyLabel(value: "beginner" | "intermediate" | "advanced") {
  return { beginner: "입문", intermediate: "중급", advanced: "고급" }[value];
}
