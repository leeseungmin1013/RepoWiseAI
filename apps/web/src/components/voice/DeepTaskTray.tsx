"use client";

import type {
  Citation,
  ChatAnswer,
  DeepTask,
  DeepTaskKind,
  DeepTaskStatus,
  ResearchMaterials,
} from "@/lib/api";

import styles from "./DeepTaskTray.module.css";

type DeepTaskTrayProps = {
  task: DeepTask | null;
  error: string | null;
  isStarting: boolean;
  isCancelling: boolean;
  onOpenEvidence?: (citation: Citation) => void;
  onCancel: () => void;
  onDismiss: () => void;
};

const kindLabels: Record<DeepTaskKind, string> = {
  deep_explanation: "코드 설명",
  impact_analysis: "영향 분석",
  roadmap_proposal: "학습 로드맵",
  research_materials: "학습 자료 조사",
};

const statusLabels: Record<DeepTaskStatus, string> = {
  queued: "대기 중",
  running: "작업 중",
  retrieving: "검색 중",
  reasoning: "추론 중",
  verifying: "검증 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
};

function isResearchMaterialsResult(
  result: DeepTask["result"],
): result is ResearchMaterials {
  return Boolean(result && typeof result === "object" && "sources" in result);
}

function isChatAnswerResult(result: DeepTask["result"]): result is ChatAnswer {
  return Boolean(result && typeof result === "object" && "citations" in result);
}

function generationModeLabel(
  value: ChatAnswer["generation_mode"] | ResearchMaterials["generation_mode"],
) {
  if (value === "openai") return "OpenAI 확인";
  if (value === "retrieval_only") return "내장 검색";
  return "웹 검색";
}

export function DeepTaskTray({
  task,
  error,
  isStarting,
  isCancelling,
  onOpenEvidence,
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
  const completedResult = task?.status === "completed" ? task.result : null;
  const researchResult =
    task?.kind === "research_materials" &&
    isResearchMaterialsResult(completedResult)
      ? completedResult
      : null;
  const answerResult =
    task?.kind !== "research_materials" &&
    isChatAnswerResult(completedResult)
      ? completedResult
      : null;
  const visibleResult = researchResult ?? answerResult;

  return (
    <section aria-label="심층 작업 패널" className={styles.tray}>
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
          <button aria-label="심층 작업 닫기" onClick={onDismiss} type="button">
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

      {visibleResult ? (
        <div className={styles.resultBlock}>
          <div className={styles.resultHeading}>
            <div>
              <strong>
                {task?.kind === "research_materials" ? "검증된 자료" : "분석 결과"}
              </strong>
              <span>{generationModeLabel(visibleResult.generation_mode)}</span>
            </div>
            {visibleResult.voice_summary ? <small>{visibleResult.voice_summary}</small> : null}
          </div>

          <p className={styles.resultAnswer}>{visibleResult.answer}</p>

          {answerResult?.citations.length ? (
            <div className={styles.citationList}>
              {answerResult.citations.map((citation) => (
                <button
                  disabled={!onOpenEvidence}
                  aria-label={`${citation.path} L${citation.start_line}${
                    citation.end_line !== citation.start_line
                      ? `-${citation.end_line}`
                      : ""
                  }`}
                  key={citation.evidence_id}
                  onClick={() => onOpenEvidence?.(citation)}
                  title={citation.preview}
                  type="button"
                >
                  <span>{citation.path}</span>
                  <small>
                    L{citation.start_line}
                    {citation.end_line !== citation.start_line
                      ? `-${citation.end_line}`
                      : ""}
                  </small>
                </button>
              ))}
            </div>
          ) : null}

          {answerResult?.follow_up ? (
            <div className={styles.followUp}>
              <span>다음 질문</span>
              <p>{answerResult.follow_up}</p>
            </div>
          ) : null}

          {researchResult?.sources.length ? (
            <ul aria-label="공식 학습자료 목록" className={styles.researchResults}>
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
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function difficultyLabel(value: "beginner" | "intermediate" | "advanced") {
  return { beginner: "입문", intermediate: "중급", advanced: "고급" }[value];
}
