"use client";

import {
  Braces,
  CheckCircle2,
  CircleAlert,
  Gauge,
  History,
  LoaderCircle,
} from "lucide-react";
import { useState } from "react";

import type {
  Citation,
  ConceptMasteryState,
  MasteryEvent,
  MasteryOverview,
} from "@/lib/api";

type Props = {
  overview: MasteryOverview | null;
  loading: boolean;
  onOpenEvidence: (citation: Citation) => void;
};

type Filter = "active" | "needs_review" | "all";

const STATE_LABELS: Record<ConceptMasteryState["state"], string> = {
  ready: "안정",
  developing: "학습 중",
  needs_review: "보충 필요",
  unknown: "미확인",
};

const EVENT_LABELS: Record<string, string> = {
  assessment_result: "초기 진단",
  activity_correct: "확인 활동 정답",
  activity_incorrect: "확인 활동 오답",
  lesson_understood: "레슨 이해",
  lesson_needs_help: "도움 요청",
};

export function MasteryPanel({ overview, loading, onOpenEvidence }: Props) {
  const [filter, setFilter] = useState<Filter>("active");
  if (!overview) {
    return (
      <div className="mastery-loading">
        <LoaderCircle className={loading ? "spin" : ""} aria-hidden size={17} />
        <span>이해도 근거를 준비하고 있습니다.</span>
      </div>
    );
  }

  const concepts = overview.concepts.filter((concept) => {
    if (filter === "all") return true;
    if (filter === "needs_review") {
      return concept.state === "needs_review" || concept.state === "developing";
    }
    return concept.event_count > 0 || concept.state !== "unknown";
  });

  return (
    <div className="mastery-scroll">
      <section className="mastery-overview">
        <div className="mastery-kicker">
          <Gauge aria-hidden size={16} />
          <span>Learner Mastery</span>
        </div>
        <h2>개념별 이해도</h2>
        <div className="mastery-summary">
          <SummaryItem label="안정" value={overview.summary.ready} tone="ready" />
          <SummaryItem label="학습 중" value={overview.summary.developing} tone="developing" />
          <SummaryItem label="보충" value={overview.summary.needs_review} tone="review" />
          <SummaryItem label="미확인" value={overview.summary.unknown} tone="unknown" />
        </div>
      </section>

      <div className="mastery-filters" aria-label="이해도 필터">
        {([
          ["active", "학습 기록"],
          ["needs_review", "보충 필요"],
          ["all", "전체"],
        ] as const).map(([value, label]) => (
          <button
            className={filter === value ? "is-active" : ""}
            key={value}
            onClick={() => setFilter(value)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      <section className="mastery-concepts">
        {concepts.length ? (
          concepts.map((concept) => <ConceptRow concept={concept} key={concept.concept_id} />)
        ) : (
          <div className="mastery-empty">아직 이 필터에 해당하는 학습 기록이 없습니다.</div>
        )}
      </section>

      <section className="mastery-history">
        <div className="mastery-history-heading">
          <History aria-hidden size={14} />
          <strong>최근 변화 근거</strong>
        </div>
        {overview.recent_events.length ? (
          overview.recent_events.slice(0, 20).map((event) => {
            const citation = eventCitation(event);
            const delta = event.new_score - event.previous_score;
            return (
              <div className="mastery-event" key={event.id}>
                <span className={delta >= 0 ? "is-positive" : "is-negative"}>
                  {delta >= 0 ? "+" : ""}
                  {Math.round(delta * 100)}
                </span>
                <div>
                  <strong>{event.concept_id.replaceAll("_", " ")}</strong>
                  <small>
                    {EVENT_LABELS[event.event_type] ?? event.event_type.replaceAll("_", " ")} ·{" "}
                    {formatEventTime(event.created_at)}
                  </small>
                </div>
                {citation ? (
                  <button
                    aria-label={`${event.concept_id} 근거 코드 열기`}
                    onClick={() => onOpenEvidence(citation)}
                    title="근거 코드 열기"
                    type="button"
                  >
                    <Braces aria-hidden size={13} />
                  </button>
                ) : null}
              </div>
            );
          })
        ) : (
          <div className="mastery-empty">확인 활동이나 레슨 피드백 후 변화가 기록됩니다.</div>
        )}
      </section>
    </div>
  );
}

function SummaryItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: string;
}) {
  return (
    <div className={`mastery-summary-item is-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function ConceptRow({ concept }: { concept: ConceptMasteryState }) {
  const score = Math.round(concept.score * 100);
  const confidence = Math.round(concept.confidence * 100);
  return (
    <div className={`mastery-concept is-${concept.state}`}>
      <div className="mastery-concept-heading">
        <div>
          {concept.state === "ready" ? (
            <CheckCircle2 aria-hidden size={13} />
          ) : (
            <CircleAlert aria-hidden size={13} />
          )}
          <strong>{concept.display_name}</strong>
        </div>
        <span>{STATE_LABELS[concept.state]}</span>
      </div>
      <p>{concept.description}</p>
      <div className="mastery-score-copy">
        <span>이해도 {score}</span>
        <small>근거 신뢰도 {confidence}</small>
      </div>
      <div className="mastery-score-track">
        <span style={{ width: `${score}%` }} />
      </div>
      {concept.prerequisite_ids.length ? (
        <div className="mastery-prerequisites">
          <small>선수 개념</small>
          {concept.prerequisite_ids.map((item) => (
            <span key={item}>{item.replaceAll("_", " ")}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function eventCitation(event: MasteryEvent): Citation | null {
  const evidence = event.evidence;
  const chunkType = evidence.chunk_type;
  if (
    typeof evidence.evidence_id !== "string" ||
    typeof evidence.snapshot_id !== "string" ||
    typeof evidence.file_id !== "string" ||
    typeof evidence.path !== "string" ||
    typeof evidence.language !== "string" ||
    typeof evidence.title !== "string" ||
    !["file", "symbol", "block"].includes(String(chunkType)) ||
    typeof evidence.start_line !== "number" ||
    typeof evidence.end_line !== "number"
  ) {
    return null;
  }
  return {
    evidence_id: evidence.evidence_id,
    source_type: "repository_code",
    snapshot_id: evidence.snapshot_id,
    file_id: evidence.file_id,
    path: evidence.path,
    language: evidence.language,
    title: evidence.title,
    chunk_type: chunkType as Citation["chunk_type"],
    start_line: evidence.start_line,
    end_line: evidence.end_line,
    preview: typeof evidence.preview === "string" ? evidence.preview : "",
    score: 1,
    retrievers: ["mastery_event"],
  };
}

function formatEventTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}
