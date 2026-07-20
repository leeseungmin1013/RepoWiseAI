"use client";

import {
  AlertTriangle,
  ArrowRight,
  BookOpenText,
  Braces,
  CheckCircle2,
  CircleDashed,
  FileCode2,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import type {
  CodeExplanation,
  CodeExplanationDepth,
  CodeExplanationEvidence,
  CodeSelection,
  ProjectMapConfidence,
} from "@/lib/api";

import styles from "./CodeFocusPanel.module.css";

type Props = {
  error: string | null;
  explanation: CodeExplanation | null;
  loading: boolean;
  selection: CodeSelection | null;
  onExplain: (depth: CodeExplanationDepth) => void;
  onOpenEvidence: (evidence: CodeExplanationEvidence) => void;
  onRequestChangeBrief: () => void;
};

const confidenceCopy: Record<ProjectMapConfidence, string> = {
  verified: "흐름으로 확인",
  inferred: "코드 근거로 추정",
  unknown: "연결 확인 필요",
};

const depthOptions: Array<{ value: CodeExplanationDepth; label: string }> = [
  { value: "minimum", label: "핵심만" },
  { value: "behavior", label: "동작" },
  { value: "syntax", label: "문법" },
  { value: "analogy", label: "비유" },
  { value: "change", label: "변경 영향" },
];

function lines(startLine: number, endLine: number) {
  return startLine === endLine ? `L${startLine}` : `L${startLine}–L${endLine}`;
}

function Confidence({ value }: { value: ProjectMapConfidence }) {
  const Icon =
    value === "verified" ? CheckCircle2 : value === "inferred" ? CircleDashed : AlertTriangle;
  return (
    <span className={`${styles.confidence} ${styles[value]}`}>
      <Icon aria-hidden size={13} />
      {confidenceCopy[value]}
    </span>
  );
}

export function CodeFocusPanel({
  error,
  explanation,
  loading,
  selection,
  onExplain,
  onOpenEvidence,
  onRequestChangeBrief,
}: Props) {
  const activeSelection = explanation?.selection ?? selection;

  return (
    <aside className="guide-panel">
      <div className="panel-toolbar">
        <Sparkles aria-hidden size={16} />
        <strong>Code Focus</strong>
        {activeSelection ? (
          <span>{lines(activeSelection.start_line, activeSelection.end_line)}</span>
        ) : null}
      </div>

      {loading ? (
        <div aria-live="polite" className={styles.state}>
          <Loader2 aria-hidden className={styles.spin} size={20} />
          <strong>이 범위의 역할을 정리하고 있어요</strong>
          <p>심볼과 기능 관계를 확인해 꼭 필요한 설명만 만듭니다.</p>
        </div>
      ) : error ? (
        <div className={styles.state} role="alert">
          <AlertTriangle aria-hidden size={20} />
          <strong>설명을 만들지 못했습니다</strong>
          <p>{error}</p>
          <button onClick={() => onExplain(explanation?.depth ?? "minimum")} type="button">
            <RefreshCw aria-hidden size={14} /> 다시 시도
          </button>
        </div>
      ) : explanation ? (
        <div className={styles.scroll}>
          <section className={styles.hero}>
            <span className={styles.kicker}>선택 범위의 최소 충분 설명</span>
            <h2>{explanation.purpose}</h2>
            <Confidence value={explanation.confidence} />
            <button
              className={styles.evidenceButton}
              onClick={() => onOpenEvidence(explanation.evidence[0])}
              type="button"
            >
              <FileCode2 aria-hidden size={14} />
              <span>
                <code>{explanation.evidence[0].path}</code>
                <small>
                  {lines(
                    explanation.evidence[0].start_line,
                    explanation.evidence[0].end_line,
                  )}
                </small>
              </span>
              <ArrowRight aria-hidden size={14} />
            </button>
          </section>

          <nav aria-label="설명 깊이" className={styles.depthTabs}>
            {depthOptions.map((option) => (
              <button
                aria-pressed={explanation.depth === option.value}
                className={explanation.depth === option.value ? styles.activeDepth : undefined}
                key={option.value}
                onClick={() => onExplain(option.value)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </nav>

          <section className={styles.section}>
            <h3>언제 실행되나요?</h3>
            <p>{explanation.executes_when}</p>
          </section>
          <section className={styles.factGrid}>
            <div>
              <span>들어오는 것</span>
              <p>{explanation.input}</p>
            </div>
            <div>
              <span>나가는 것·부수 효과</span>
              <p>{explanation.output_or_side_effect}</p>
            </div>
          </section>
          <section className={styles.section}>
            <h3>프로젝트 안에서 맡는 역할</h3>
            <p>{explanation.project_role}</p>
          </section>
          <section className={styles.section}>
            <h3>바꾸면 어디가 달라질까요?</h3>
            <p>{explanation.change_impact}</p>
            <button
              className={styles.changeBriefButton}
              onClick={onRequestChangeBrief}
              type="button"
            >
              <Sparkles aria-hidden size={14} /> 상세 변경 영향 분석
              <ArrowRight aria-hidden size={13} />
            </button>
          </section>

          <section className={styles.section}>
            <h3>먼저 알면 좋은 개념</h3>
            <div className={styles.concepts}>
              {explanation.required_concepts.map((concept) => (
                <span key={concept}>{concept}</span>
              ))}
            </div>
          </section>

          {explanation.syntax_segments.length ? (
            <section className={styles.section}>
              <h3>문법 단위로 보기</h3>
              <ol className={styles.syntaxList}>
                {explanation.syntax_segments.map((segment, index) => (
                  <li key={`${segment.node_type}:${segment.start_line}:${index}`}>
                    <code>{lines(segment.start_line, segment.end_line)}</code>
                    <p>{segment.explanation}</p>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}

          {explanation.analogy ? (
            <section className={styles.analogy}>
              <BookOpenText aria-hidden size={16} />
              <div><h3>비유로 이해하기</h3><p>{explanation.analogy}</p></div>
            </section>
          ) : null}

          {explanation.related_steps.length ? (
            <section className={styles.section}>
              <h3>이 범위에서 확인된 다음 연결</h3>
              <ul className={styles.relatedList}>
                {explanation.related_steps.map((step, index) => (
                  <li key={`${step.relation_type}:${step.evidence.start_line}:${index}`}>
                    <button onClick={() => onOpenEvidence(step.evidence)} type="button">
                      <Braces aria-hidden size={14} />
                      <span><strong>{step.title}</strong><small>{step.target}</small></span>
                      <ArrowRight aria-hidden size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <details className={styles.limitations}>
            <summary>이 설명에서 아직 모르는 것</summary>
            <ul>{explanation.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </details>
        </div>
      ) : selection ? (
        <div className={styles.state}>
          <Braces aria-hidden size={22} />
          <strong>선택한 코드만 이해해 볼까요?</strong>
          <p>{lines(selection.start_line, selection.end_line)} 범위의 역할과 결과부터 설명합니다.</p>
          <button onClick={() => onExplain("minimum")} type="button">
            <Sparkles aria-hidden size={14} /> 선택 범위 설명
          </button>
        </div>
      ) : (
        <div className={styles.state}>
          <Braces aria-hidden size={22} />
          <strong>코드 범위를 선택해 주세요</strong>
          <p>기능 흐름의 근거를 열거나 에디터에서 1~80줄을 선택하면 핵심 역할부터 볼 수 있습니다.</p>
        </div>
      )}
    </aside>
  );
}
