"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  FileCode2,
  GraduationCap,
  Loader2,
  Map,
  Play,
  RotateCcw,
  Route,
  ShieldAlert,
} from "lucide-react";

import type {
  FeatureFlowCatalog,
  FeatureFlowDetail,
  FeatureFlowEvidence,
  FeatureFlowStep,
  ProjectMapConfidence,
} from "@/lib/api";

import styles from "./FeatureFlowPanel.module.css";

type Props = {
  catalog: FeatureFlowCatalog | null;
  flow: FeatureFlowDetail | null;
  loading: boolean;
  detailLoading: boolean;
  error: string | null;
  onBackToMap: () => void;
  onBackToCatalog: () => void;
  onOpenEvidence: (
    evidence: FeatureFlowEvidence,
    context?: { featureFlowId: string; flowStepId?: string },
  ) => void;
  onRetry: () => void;
  onSelectFlow: (flowId: string) => void;
  onStartLearning: () => void;
};

const confidenceCopy: Record<ProjectMapConfidence, string> = {
  verified: "코드로 확인",
  inferred: "근거로 추정",
  unknown: "확인 필요",
};

const relationCopy: Record<string, string> = {
  TRIGGERS: "다음 동작 시작",
  REQUESTS: "서버에 요청",
  HANDLED_BY: "요청 처리",
  READS: "저장된 값 읽기",
  WRITES: "결과 저장",
  NAVIGATES_TO: "화면 이동",
  USES_EXTERNAL: "외부 서비스 사용",
};

const roleCopy: Record<string, string> = {
  user_trigger: "사용자 행동",
  client_handler: "화면 동작 처리",
  request: "네트워크 요청",
  server_handler: "서버 처리",
  storage_read: "저장값 읽기",
  storage_write: "저장값 변경",
  state_write: "화면 상태 변경",
  navigation: "화면 이동",
  external_service: "외부 서비스",
};

function ConfidenceBadge({ value }: { value: ProjectMapConfidence }) {
  const Icon =
    value === "verified"
      ? CheckCircle2
      : value === "inferred"
        ? CircleDashed
        : AlertTriangle;

  return (
    <span className={`${styles.confidence} ${styles[value]}`}>
      <Icon aria-hidden size={13} />
      {confidenceCopy[value]}
    </span>
  );
}

function formatLines(startLine: number, endLine: number) {
  return startLine === endLine ? `L${startLine}` : `L${startLine}–${endLine}`;
}

function StatePanel({
  kind,
  title,
  description,
  onBackToMap,
  onRetry,
  limitations = [],
}: {
  kind: "loading" | "empty" | "error";
  title: string;
  description: string;
  onBackToMap?: () => void;
  onRetry?: () => void;
  limitations?: string[];
}) {
  const Icon = kind === "loading" ? Loader2 : kind === "error" ? ShieldAlert : Route;

  return (
    <section
      aria-busy={kind === "loading"}
      aria-live="polite"
      className={styles.statePanel}
    >
      <span className={kind === "loading" ? styles.spinning : undefined}>
        <Icon aria-hidden size={23} />
      </span>
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
        {limitations.length ? (
          <ul className={styles.stateLimitations} aria-label="기능 흐름 분석 안내">
            {limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        ) : null}
        {onRetry || onBackToMap ? (
          <div className={styles.stateActions}>
            {onRetry ? (
              <button type="button" onClick={onRetry}>
                <RotateCcw aria-hidden size={14} /> 다시 시도
              </button>
            ) : null}
            {onBackToMap ? (
              <button type="button" onClick={onBackToMap}>
                <Map aria-hidden size={14} /> 프로젝트 지도
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function EvidenceButton({
  evidence,
  context,
  navigationContext,
  onOpenEvidence,
}: {
  evidence: FeatureFlowEvidence;
  context: string;
  navigationContext?: { featureFlowId: string; flowStepId?: string };
  onOpenEvidence: Props["onOpenEvidence"];
}) {
  return (
    <button
      aria-label={`근거 코드 열기: ${context}, ${evidence.path} ${formatLines(evidence.start_line, evidence.end_line)}`}
      className={styles.evidenceButton}
      onClick={() => onOpenEvidence(evidence, navigationContext)}
      type="button"
    >
      <FileCode2 aria-hidden size={14} />
      <span>
        <code>{evidence.path}</code>
        <small>{formatLines(evidence.start_line, evidence.end_line)}</small>
      </span>
      <ArrowRight aria-hidden size={14} />
    </button>
  );
}

function StepCard({
  step,
  kind,
  flowId,
  onOpenEvidence,
}: {
  step: FeatureFlowStep;
  kind: "normal" | "failure";
  flowId: string;
  onOpenEvidence: Props["onOpenEvidence"];
}) {
  return (
    <li className={styles.stepItem}>
      <span className={`${styles.stepNumber} ${kind === "failure" ? styles.failureNumber : ""}`}>
        {step.ordinal}
      </span>
      <article className={styles.stepCard}>
        <div className={styles.stepTopline}>
          <span className={styles.stepRole}>{roleCopy[step.role] ?? step.role}</span>
          <span className={styles.relation} title={step.relation_type}>
            관계 · {relationCopy[step.relation_type] ?? step.relation_type}
          </span>
          <ConfidenceBadge value={step.confidence} />
        </div>
        <h3>{step.title}</h3>
        <dl className={styles.stepFacts}>
          <div>
            <dt>실행 조건</dt>
            <dd>{step.executes_when}</dd>
          </div>
          <div>
            <dt>입력</dt>
            <dd>{step.input}</dd>
          </div>
          <div>
            <dt>결과·부수 효과</dt>
            <dd>{step.output_or_side_effect}</dd>
          </div>
        </dl>
        {step.evidence.length ? (
          <div className={styles.evidenceList} aria-label={`${step.title} 코드 근거`}>
            {step.evidence.map((evidence) => (
              <EvidenceButton
                context={step.title}
                evidence={evidence}
                key={`${evidence.file_id}:${evidence.start_line}:${evidence.end_line}`}
                navigationContext={{ featureFlowId: flowId, flowStepId: step.id }}
                onOpenEvidence={onOpenEvidence}
              />
            ))}
          </div>
        ) : (
          <p className={styles.unknownEvidence}>
            <AlertTriangle aria-hidden size={13} /> 이 단계의 정확한 코드 위치는 아직 확인하지 못했습니다.
          </p>
        )}
      </article>
    </li>
  );
}

function sortedSteps(steps: FeatureFlowStep[]) {
  return [...steps].sort((left, right) => left.ordinal - right.ordinal);
}

export function FeatureFlowPanel({
  catalog,
  flow,
  loading,
  detailLoading,
  error,
  onBackToMap,
  onBackToCatalog,
  onOpenEvidence,
  onRetry,
  onSelectFlow,
  onStartLearning,
}: Props) {
  if (loading) {
    return (
      <StatePanel
        description="진입점과 파일 사이의 연결을 사용자 행동 순서로 정리하는 중입니다."
        kind="loading"
        title="기능 흐름을 찾고 있어요"
      />
    );
  }

  if (error) {
    return (
      <StatePanel
        description={error}
        kind="error"
        onBackToMap={onBackToMap}
        onRetry={onRetry}
        title="기능 흐름을 불러오지 못했습니다"
      />
    );
  }

  if (detailLoading) {
    return (
      <StatePanel
        description="선택한 기능의 정상 경로와 실패 경로를 코드 근거로 연결하고 있습니다."
        kind="loading"
        title="선택한 흐름을 펼치고 있어요"
      />
    );
  }

  if (flow) {
    const normalSteps = sortedSteps(flow.normal_steps);
    const failureSteps = sortedSteps(flow.failure_steps);
    const hasUnknown =
      flow.confidence === "unknown" ||
      [...normalSteps, ...failureSteps].some(
        (step) => step.confidence === "unknown" || !step.evidence.length,
      );

    return (
      <section className={styles.panel} aria-labelledby="feature-flow-title">
        <nav aria-label="기능 흐름 위치" className={styles.breadcrumbs}>
          <button type="button" onClick={onBackToMap}>프로젝트 지도</button>
          <ChevronRight aria-hidden size={13} />
          <button type="button" onClick={onBackToCatalog}>기능 흐름</button>
          <ChevronRight aria-hidden size={13} />
          <span aria-current="page">{flow.title}</span>
        </nav>

        <header className={styles.detailHero}>
          <div>
            <div className={styles.eyebrow}>
              <Route aria-hidden size={15} /> FEATURE FLOW
              <ConfidenceBadge value={flow.confidence} />
            </div>
            <h1 id="feature-flow-title">{flow.title}</h1>
            <p>{flow.user_goal}</p>
            {flow.involved_areas.length ? (
              <div className={styles.areaTags} aria-label="관련 시스템 영역">
                {flow.involved_areas.map((area) => <span key={area}>{area}</span>)}
              </div>
            ) : null}
          </div>
          <button className={styles.learningButton} type="button" onClick={onStartLearning}>
            <GraduationCap aria-hidden size={15} /> 깊이 배우기 <span>선택</span>
          </button>
        </header>

        <div className={styles.flowBoundary}>
          <div>
            <span><Play aria-hidden size={13} /> 시작</span>
            <strong>{flow.trigger}</strong>
          </div>
          <ArrowRight aria-hidden size={18} />
          <div>
            <span><CheckCircle2 aria-hidden size={13} /> 사용자 결과</span>
            <strong>{flow.outcome}</strong>
          </div>
        </div>

        <section className={styles.stepsSection} aria-labelledby="normal-flow-heading">
          <div className={styles.sectionHeading}>
            <div>
              <span>01</span>
              <h2 id="normal-flow-heading">정상 흐름</h2>
            </div>
            <p>위에서 아래로, 실제 실행 순서대로 읽어보세요.</p>
          </div>
          {normalSteps.length ? (
            <ol className={styles.stepList}>
              {normalSteps.map((step) => (
                <StepCard
                  flowId={flow.id}
                  kind="normal"
                  key={step.id}
                  onOpenEvidence={onOpenEvidence}
                  step={step}
                />
              ))}
            </ol>
          ) : (
            <p className={styles.inlineEmpty}>정상 실행 순서를 확정할 근거가 아직 없습니다.</p>
          )}
        </section>

        {failureSteps.length ? (
          <section className={`${styles.stepsSection} ${styles.failureSection}`} aria-labelledby="failure-flow-heading">
            <div className={styles.sectionHeading}>
              <div>
                <span>02</span>
                <h2 id="failure-flow-heading">실패·예외 흐름</h2>
              </div>
              <p>정상 경로에서 벗어날 때 어떤 코드가 대응하는지 보여줍니다.</p>
            </div>
            <ol className={styles.stepList}>
              {failureSteps.map((step) => (
                <StepCard
                  flowId={flow.id}
                  kind="failure"
                  key={step.id}
                  onOpenEvidence={onOpenEvidence}
                  step={step}
                />
              ))}
            </ol>
          </section>
        ) : null}

        <section className={styles.limitations} aria-labelledby="flow-limitations-heading">
          <div>
            <AlertTriangle aria-hidden size={17} />
            <h2 id="flow-limitations-heading">확인 범위와 제한</h2>
          </div>
          {hasUnknown ? (
            <p className={styles.unknownNotice}>
              ‘확인 필요’ 단계는 정적 코드만으로 실행 순서나 위치를 확정하지 못한 부분입니다.
            </p>
          ) : null}
          {flow.limitations.length ? (
            <ul>{flow.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p>현재 분석에서 별도로 확인된 제한 사항은 없습니다.</p>
          )}
        </section>
      </section>
    );
  }

  if (!catalog || !catalog.flows.length) {
    return (
      <StatePanel
        description="정적 분석으로 연결할 수 있는 진입점과 실행 단계가 아직 충분하지 않습니다. 원본 코드 탐색은 계속 사용할 수 있습니다."
        kind="empty"
        limitations={catalog?.limitations ?? []}
        onBackToMap={onBackToMap}
        title="확인된 기능 흐름이 없습니다"
      />
    );
  }

  return (
    <section className={styles.panel} aria-labelledby="feature-flow-catalog-title">
      <nav aria-label="기능 흐름 위치" className={styles.breadcrumbs}>
        <button type="button" onClick={onBackToMap}>프로젝트 지도</button>
        <ChevronRight aria-hidden size={13} />
        <span aria-current="page">기능 흐름</span>
      </nav>

      <header className={styles.catalogHero}>
        <div className={styles.eyebrow}><Route aria-hidden size={15} /> FEATURE FLOWS</div>
        <h1 id="feature-flow-catalog-title">어떤 사용자 행동을 따라가 볼까요?</h1>
        <p>파일부터 고르지 않아도 됩니다. 궁금한 결과를 선택하면 관련 코드가 실행되는 순서를 보여드릴게요.</p>
        <small>{catalog.repository_name} · {catalog.analysis_version}</small>
      </header>

      <div className={styles.catalogGrid}>
        {catalog.flows.map((item, index) => {
          const coverage = Math.round(Math.max(0, Math.min(1, item.evidence_coverage)) * 100);
          return (
            <article className={styles.flowCard} key={item.id}>
              <div className={styles.flowCardTopline}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <ConfidenceBadge value={item.confidence} />
              </div>
              <h2>{item.title}</h2>
              <p>{item.user_goal}</p>
              <dl>
                <div><dt>시작</dt><dd>{item.trigger}</dd></div>
                <div><dt>결과</dt><dd>{item.outcome}</dd></div>
              </dl>
              <div className={styles.flowMetrics}>
                <span>{item.step_count}단계</span>
                <span>코드 근거 {coverage}%</span>
              </div>
              {item.involved_areas.length ? (
                <div className={styles.areaTags}>
                  {item.involved_areas.map((area) => <span key={area}>{area}</span>)}
                </div>
              ) : null}
              <button
                aria-label={`${item.title} 흐름 따라가기`}
                className={styles.selectFlowButton}
                type="button"
                onClick={() => onSelectFlow(item.id)}
              >
                이 흐름 따라가기 <ArrowRight aria-hidden size={14} />
              </button>
              {item.entry_evidence ? (
                <EvidenceButton
                  context={`${item.title} 진입점`}
                  evidence={item.entry_evidence}
                  navigationContext={{ featureFlowId: item.id }}
                  onOpenEvidence={onOpenEvidence}
                />
              ) : null}
            </article>
          );
        })}
      </div>

      <section className={styles.catalogLimitations} aria-labelledby="catalog-limitations-heading">
        <AlertTriangle aria-hidden size={16} />
        <div>
          <h2 id="catalog-limitations-heading">분석 범위</h2>
          {catalog.limitations.length ? (
            <ul>{catalog.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p>현재 분석에서 별도로 확인된 제한 사항은 없습니다.</p>
          )}
        </div>
      </section>

      <button className={styles.backButton} type="button" onClick={onBackToMap}>
        <ArrowLeft aria-hidden size={14} /> 프로젝트 지도로 돌아가기
      </button>
    </section>
  );
}
