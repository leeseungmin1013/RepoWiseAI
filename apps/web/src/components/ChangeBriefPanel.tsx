"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  FileSearch,
  Loader2,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Square,
} from "lucide-react";
import { FormEvent, useState } from "react";

import type {
  ChangeBrief,
  ChangeBriefImpact,
  CodeExplanationEvidence,
  CodeSelection,
  DeepTask,
  ProjectMapConfidence,
} from "@/lib/api";

import styles from "./ChangeBriefPanel.module.css";

type Props = {
  cancelling: boolean;
  error: string | null;
  selection: CodeSelection | null;
  starting: boolean;
  task: DeepTask | null;
  onCancel: () => void;
  onOpenEvidence: (evidence: CodeExplanationEvidence) => void;
  onReset: () => void;
  onStart: (prompt: string) => void;
};

const confidenceLabel: Record<ProjectMapConfidence, string> = {
  verified: "직접 관계로 확인",
  inferred: "관계 근거로 추정",
  unknown: "추가 확인 필요",
};
const riskLabel = { low: "낮음", medium: "중간", high: "높음", unknown: "판단 보류" };

function isChangeBrief(result: DeepTask["result"]): result is ChangeBrief {
  return Boolean(result && "analysis_version" in result && "candidate_locations" in result);
}

function lineRange(evidence: CodeExplanationEvidence) {
  return evidence.start_line === evidence.end_line
    ? `L${evidence.start_line}`
    : `L${evidence.start_line}–L${evidence.end_line}`;
}

function ImpactList({
  impacts,
  empty,
  onOpenEvidence,
}: {
  impacts: ChangeBriefImpact[];
  empty: string;
  onOpenEvidence: Props["onOpenEvidence"];
}) {
  if (!impacts.length) return <p className={styles.empty}>{empty}</p>;
  return (
    <ul className={styles.impactList}>
      {impacts.map((impact, index) => (
        <li key={`${impact.relation_type}:${index}`}>
          <div className={styles.impactHeading}>
            {impact.confidence === "verified" ? (
              <CheckCircle2 aria-hidden size={15} />
            ) : impact.confidence === "inferred" ? (
              <CircleDashed aria-hidden size={15} />
            ) : (
              <AlertTriangle aria-hidden size={15} />
            )}
            <strong>{impact.title}</strong>
            <span>{confidenceLabel[impact.confidence]}</span>
          </div>
          <p>{impact.description}</p>
          <button onClick={() => onOpenEvidence(impact.evidence[0])} type="button">
            {impact.evidence[0].path} {lineRange(impact.evidence[0])}
            <ArrowRight aria-hidden size={13} />
          </button>
        </li>
      ))}
    </ul>
  );
}

export function ChangeBriefPanel({
  cancelling,
  error,
  selection,
  starting,
  task,
  onCancel,
  onOpenEvidence,
  onReset,
  onStart,
}: Props) {
  const [prompt, setPrompt] = useState("");
  const brief = isChangeBrief(task?.result) ? task.result : null;
  const running = starting || Boolean(task && !["completed", "failed", "cancelled"].includes(task.status));

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selection || prompt.trim().length < 2 || running) return;
    onStart(prompt.trim());
  }

  return (
    <aside className="guide-panel">
      <div className="panel-toolbar">
        <ShieldAlert aria-hidden size={16} />
        <strong>Change Brief</strong>
        {selection ? <span>L{selection.start_line}–L{selection.end_line}</span> : null}
      </div>
      <div className={styles.scroll}>
        {!brief ? (
          <section className={styles.requestCard}>
            <span className={styles.kicker}>패치를 만들기 전 영향 경계 확인</span>
            <h2>무엇을 어떻게 바꾸고 싶나요?</h2>
            <p>
              선택한 코드에서 시작해 직접 영향과 아직 확인해야 할 경계를 분리합니다.
              실제 코드는 변경하지 않습니다.
            </p>
            {!selection ? (
              <div className={styles.notice} role="status">
                <FileSearch aria-hidden size={17} />
                기능 흐름의 근거를 열거나 원본 코드에서 범위를 먼저 선택해 주세요.
              </div>
            ) : null}
            <form onSubmit={submit}>
              <label htmlFor="change-brief-request">변경 요청</label>
              <textarea
                disabled={running}
                id="change-brief-request"
                maxLength={4000}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="예: 로그인 성공 후 이동할 화면을 바꾸고 싶어요"
                rows={4}
                value={prompt}
              />
              <button
                disabled={!selection || prompt.trim().length < 2 || running}
                type="submit"
              >
                {running ? <Loader2 aria-hidden className={styles.spin} size={15} /> : <Sparkles aria-hidden size={15} />}
                {running ? task?.message ?? "영향을 분석하고 있습니다" : "변경 영향 분석"}
              </button>
            </form>
            {running ? (
              <button className={styles.cancel} disabled={cancelling} onClick={onCancel} type="button">
                <Square aria-hidden size={12} /> {cancelling ? "취소 중" : "분석 취소"}
              </button>
            ) : null}
            {error || task?.status === "failed" ? (
              <div className={styles.error} role="alert">
                <AlertTriangle aria-hidden size={16} />
                {error ?? task?.error?.message ?? "변경 영향 분석을 완료하지 못했습니다."}
              </div>
            ) : null}
          </section>
        ) : (
          <>
            <section className={styles.hero}>
              <span className={styles.kicker}>요청 요약</span>
              <h2>{brief.request_summary}</h2>
              <div className={`${styles.risk} ${styles[brief.risk_level]}`}>
                <ShieldAlert aria-hidden size={16} />
                <strong>위험도 {riskLabel[brief.risk_level]}</strong>
                <p>{brief.risk_rationale}</p>
              </div>
              <button className={styles.reset} onClick={onReset} type="button">
                <RotateCcw aria-hidden size={13} /> 새 요청 분석
              </button>
            </section>

            <section className={styles.section}>
              <h3>먼저 확인할 위치</h3>
              <ol className={styles.candidates}>
                {brief.candidate_locations.map((candidate, index) => (
                  <li key={`${candidate.evidence.file_id}:${candidate.evidence.start_line}`}>
                    <button onClick={() => onOpenEvidence(candidate.evidence)} type="button">
                      <span>{index + 1}</span>
                      <div><strong>{candidate.title}</strong><small>{candidate.reason}</small><code>{candidate.evidence.path} {lineRange(candidate.evidence)}</code></div>
                      <ArrowRight aria-hidden size={13} />
                    </button>
                  </li>
                ))}
              </ol>
            </section>

            <section className={styles.section}>
              <h3>확정된 직접 영향</h3>
              <ImpactList impacts={brief.confirmed_direct_impacts} empty="현재 정적 관계에서 확정된 직접 영향이 없습니다." onOpenEvidence={onOpenEvidence} />
            </section>
            <section className={styles.section}>
              <h3>확인이 필요한 영향</h3>
              <ImpactList impacts={brief.possible_impacts_to_verify} empty="추가 확인 대상으로 분류된 관계가 없습니다." onOpenEvidence={onOpenEvidence} />
            </section>
            <section className={styles.section}>
              <h3>아직 모르는 경계</h3>
              <ul>{brief.unknown_boundaries.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
            <section className={styles.section}>
              <h3>검증 순서</h3>
              <ol>{brief.verification_steps.map((item) => <li key={item}>{item}</li>)}</ol>
            </section>
            <details className={styles.details}>
              <summary>되돌리기 가이드와 분석 한계</summary>
              <h3>되돌리기</h3>
              <ol>{brief.rollback_guidance.map((item) => <li key={item}>{item}</li>)}</ol>
              <h3>분석 한계</h3>
              <ul>{brief.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
          </>
        )}
      </div>
    </aside>
  );
}
