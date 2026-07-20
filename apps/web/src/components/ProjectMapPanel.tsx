"use client";

import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Box,
  CheckCircle,
  Circle,
  Code2,
  Compass,
  FileText,
  GraduationCap,
  Key,
  Layers,
  Loader2,
  Map,
  Plug,
  Route,
} from "lucide-react";

import type {
  FeatureFlowSummary,
  ProjectMap,
  ProjectMapEvidence,
  Snapshot,
} from "@/lib/api";

import styles from "./ProjectMapPanel.module.css";

type Props = {
  map: ProjectMap | null;
  snapshot: Snapshot | null;
  loading: boolean;
  featureFlows: FeatureFlowSummary[];
  onOpenEvidence: (evidence: ProjectMapEvidence) => void;
  onOpenExplorer: () => void;
  onOpenFeatureFlows: (flowId?: string) => void;
  onStartLearning: () => void;
};

type Confidence = "verified" | "inferred" | "unknown";
type Intent = "overview" | "feature" | "change" | "problem";

const intentOptions: Array<{
  id: Intent;
  label: string;
  guidance: string;
}> = [
  {
    id: "overview",
    label: "전체 구조 파악",
    guidance: "대표 기능과 시스템 영역을 훑으며 프로젝트의 큰 그림부터 잡아보세요.",
  },
  {
    id: "feature",
    label: "특정 기능 따라가기",
    guidance: "대표 기능 카드에서 사용자 행동과 관련 시스템을 먼저 확인해보세요.",
  },
  {
    id: "change",
    label: "작은 수정 준비",
    guidance: "먼저 읽을 코드에서 시작해 수정 범위를 좁혀보세요.",
  },
  {
    id: "problem",
    label: "문제 범위 찾기",
    guidance: "시스템 영역과 외부 연결을 기준으로 문제가 생길 수 있는 경계를 찾아보세요.",
  },
];

const confidenceCopy: Record<Confidence, string> = {
  verified: "코드로 확인",
  inferred: "근거로 추정",
  unknown: "확인 필요",
};

function ConfidenceBadge({ value }: { value: Confidence }) {
  const Icon = value === "verified" ? CheckCircle : value === "inferred" ? Circle : AlertTriangle;

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

function environmentVariableName(name: string) {
  return name.split("=", 1)[0].trim();
}

type MapEvidence = ProjectMap["capabilities"][number]["evidence"][number];

function EvidenceButton({
  evidence,
  context,
  compact = false,
  onOpenEvidence,
}: {
  evidence: MapEvidence;
  context: string;
  compact?: boolean;
  onOpenEvidence: (evidence: MapEvidence) => void;
}) {
  return (
    <button
      className={`${styles.evidenceLink} ${compact ? styles.compactEvidenceLink : ""}`}
      type="button"
      aria-label={`근거 코드 열기: ${context}, ${evidence.path}`}
      onClick={() => onOpenEvidence(evidence)}
    >
      <FileText aria-hidden size={13} />
      <span>{evidence.path}</span>
      <ArrowRight aria-hidden size={13} />
    </button>
  );
}

export function ProjectMapPanel({
  map,
  snapshot,
  loading,
  featureFlows,
  onOpenEvidence,
  onOpenExplorer,
  onOpenFeatureFlows,
  onStartLearning,
}: Props) {
  const [intent, setIntent] = useState<Intent>("overview");
  const selectedIntent = intentOptions.find((option) => option.id === intent) ?? intentOptions[0];

  if (loading) {
    return (
      <section className={styles.statePanel} aria-live="polite" aria-busy="true">
        <span className={styles.loadingIcon}>
          <Loader2 aria-hidden size={22} />
        </span>
        <div>
          <strong>프로젝트 지도를 만들고 있어요</strong>
          <p>파일 목록을 기능과 시스템 영역 중심으로 다시 정리하는 중입니다.</p>
        </div>
      </section>
    );
  }

  if (!map) {
    return (
      <section className={styles.statePanel}>
        <span className={styles.emptyIcon}>
          <Map aria-hidden size={22} />
        </span>
        <div>
          <strong>아직 프로젝트 지도가 없습니다</strong>
          <p>저장소 분석이 끝나면 코드보다 먼저 전체 구조를 보여드릴게요.</p>
          <button className={styles.secondaryButton} type="button" onClick={onOpenExplorer}>
            <Code2 aria-hidden size={15} />
            원본 코드 탐색
          </button>
        </div>
      </section>
    );
  }

  const prominentCapabilities = map.capabilities.slice(0, 3);
  const hiddenCapabilityCount = Math.max(0, map.capabilities.length - prominentCapabilities.length);

  return (
    <section className={styles.panel} aria-labelledby="project-map-title">
      <header className={styles.hero}>
        <div className={styles.heroCopy}>
          <div className={styles.eyebrow}>
            <Compass aria-hidden size={15} />
            <span>PROJECT MAP</span>
            <ConfidenceBadge value={map.summary_confidence} />
          </div>
          <h1 id="project-map-title">{map.summary}</h1>
          <div className={styles.repositoryMeta}>
            <strong>{map.repository_name}</strong>
            {snapshot?.branch ? <span>{snapshot.branch}</span> : null}
            {map.commit_sha ? <code title={map.commit_sha}>{map.commit_sha.slice(0, 10)}</code> : null}
          </div>
        </div>

        <div className={styles.heroActions} aria-label="다른 탐색 방식">
          <button className={styles.flowButton} type="button" onClick={() => onOpenFeatureFlows()}>
            <Route aria-hidden size={16} />
            기능 흐름 보기
          </button>
          <button className={styles.explorerButton} type="button" onClick={onOpenExplorer}>
            <Code2 aria-hidden size={16} />
            원본 코드 탐색
          </button>
          <button className={styles.learningButton} type="button" onClick={onStartLearning}>
            <GraduationCap aria-hidden size={16} />
            깊이 배우기 <span>선택</span>
          </button>
        </div>
      </header>

      <section className={styles.intentSection} aria-labelledby="map-intent-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.sectionNumber}>01</span>
          <div>
            <h2 id="map-intent-heading">오늘 이 저장소에서 무엇을 하려 하나요?</h2>
            <p>실력 진단 없이, 지금 필요한 목적부터 선택하세요.</p>
          </div>
        </div>
        <div className={styles.intentGrid}>
          {intentOptions.map((option) => (
            <button
              className={styles.intentButton}
              data-selected={intent === option.id}
              key={option.id}
              type="button"
              aria-pressed={intent === option.id}
              onClick={() => setIntent(option.id)}
            >
              <span>{option.label}</span>
              <ArrowRight aria-hidden size={15} />
            </button>
          ))}
        </div>
        <p className={styles.intentGuidance} role="status">
          <Compass aria-hidden size={14} />
          {selectedIntent.guidance}
        </p>
      </section>

      <section className={styles.contentSection} aria-labelledby="capabilities-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.sectionNumber}>02</span>
          <div>
            <h2 id="capabilities-heading">이 저장소가 하는 일</h2>
            <p>파일명이 아니라 사용자가 얻는 결과를 기준으로 묶었습니다.</p>
          </div>
        </div>

        {prominentCapabilities.length ? (
          <div className={styles.capabilityGrid}>
            {prominentCapabilities.map((capability, index) => (
              <article className={styles.capabilityCard} key={capability.id}>
                <div className={styles.cardTopline}>
                  <span className={styles.capabilityIndex}>{String(index + 1).padStart(2, "0")}</span>
                  <ConfidenceBadge value={capability.confidence} />
                </div>
                <h3>{capability.name}</h3>
                <p>{capability.description}</p>
                {capability.evidence[0] ? (
                  <EvidenceButton
                    context={capability.name}
                    evidence={capability.evidence[0]}
                    onOpenEvidence={onOpenEvidence}
                  />
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.inlineEmpty}>대표 기능을 확인할 근거가 아직 충분하지 않습니다.</p>
        )}
        {hiddenCapabilityCount ? (
          <p className={styles.moreNotice}>나머지 기능 {hiddenCapabilityCount}개는 이후 탐색 단계에서 볼 수 있어요.</p>
        ) : null}

        <aside className={styles.flowEntry} aria-labelledby="map-flow-entry-heading">
          <div>
            <span className={styles.flowEntryIcon}><Route aria-hidden size={18} /></span>
            <div>
              <h3 id="map-flow-entry-heading">기능이 실제로 실행되는 순서를 보고 싶나요?</h3>
              <p>프로젝트 지도의 기능 ID를 억지로 연결하지 않고, 코드 진입점에서 확인된 실행 흐름만 따로 보여드립니다.</p>
            </div>
          </div>
          {featureFlows.length ? (
            <div className={styles.flowChoices} aria-label="확인된 기능 흐름">
              {featureFlows.slice(0, 3).map((flow) => (
                <button key={flow.id} type="button" onClick={() => onOpenFeatureFlows(flow.id)}>
                  <span>
                    <strong>{flow.title}</strong>
                    <small>{flow.trigger} → {flow.outcome}</small>
                  </span>
                  <ArrowRight aria-hidden size={14} />
                </button>
              ))}
            </div>
          ) : (
            <button className={styles.openFlowsButton} type="button" onClick={() => onOpenFeatureFlows()}>
              확인된 기능 흐름 보기 <ArrowRight aria-hidden size={14} />
            </button>
          )}
        </aside>
      </section>

      <section className={styles.contentSection} aria-labelledby="areas-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.sectionNumber}>03</span>
          <div>
            <h2 id="areas-heading">시스템은 이렇게 나뉩니다</h2>
            <p>코드가 맡은 책임과 외부 경계를 한눈에 확인하세요.</p>
          </div>
        </div>

        <div className={styles.areaGrid}>
          {map.system_areas.map((area) => (
            <article className={styles.areaCard} key={area.id}>
              <div className={styles.areaIcon}>
                <Layers aria-hidden size={17} />
              </div>
              <div>
                <div className={styles.areaHeading}>
                  <h3>{area.name}</h3>
                  <ConfidenceBadge value={area.confidence} />
                </div>
                <p>{area.description}</p>
                {area.evidence[0] ? (
                  <EvidenceButton
                    compact
                    context={area.name}
                    evidence={area.evidence[0]}
                    onOpenEvidence={onOpenEvidence}
                  />
                ) : null}
              </div>
            </article>
          ))}
          {!map.system_areas.length ? (
            <p className={styles.inlineEmpty}>시스템 영역을 분리할 근거가 아직 충분하지 않습니다.</p>
          ) : null}
        </div>

        <div className={styles.boundaryGrid}>
          <article className={styles.boundaryCard}>
            <div className={styles.boundaryHeading}>
              <Plug aria-hidden size={16} />
              <h3>외부 서비스</h3>
              <span>{map.external_services.length}</span>
            </div>
            {map.external_services.length ? (
              <ul>
                {map.external_services.map((service) => (
                  <li key={service.name}>
                    <div>
                      <strong>{service.name}</strong>
                      <p>{service.description}</p>
                      {service.evidence[0] ? (
                        <EvidenceButton
                          compact
                          context={service.name}
                          evidence={service.evidence[0]}
                          onOpenEvidence={onOpenEvidence}
                        />
                      ) : null}
                    </div>
                    <ConfidenceBadge value={service.confidence} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.inlineEmpty}>확인된 외부 서비스가 없습니다.</p>
            )}
          </article>

          <article className={styles.boundaryCard}>
            <div className={styles.boundaryHeading}>
              <Key aria-hidden size={16} />
              <h3>필요한 환경 변수</h3>
              <span>{map.environment_variables.length}</span>
            </div>
            {map.environment_variables.length ? (
              <ul className={styles.environmentList}>
                {map.environment_variables.map((variable) => (
                  <li key={variable.name}>
                    <div>
                      <code>{environmentVariableName(variable.name)}</code>
                      <p>{variable.description}</p>
                      {variable.evidence[0] ? (
                        <EvidenceButton
                          compact
                          context={environmentVariableName(variable.name)}
                          evidence={variable.evidence[0]}
                          onOpenEvidence={onOpenEvidence}
                        />
                      ) : null}
                    </div>
                    <ConfidenceBadge value={variable.confidence} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.inlineEmpty}>확인된 환경 변수 이름이 없습니다.</p>
            )}
            <p className={styles.securityNote}>보안을 위해 변수 이름과 역할만 표시합니다.</p>
          </article>
        </div>
      </section>

      <section className={styles.contentSection} aria-labelledby="read-first-heading">
        <div className={styles.sectionIntro}>
          <span className={styles.sectionNumber}>04</span>
          <div>
            <h2 id="read-first-heading">코드는 여기부터 읽어보세요</h2>
            <p>전체 파일이 아니라 큰 그림을 이해하는 데 필요한 근거만 골랐습니다.</p>
          </div>
        </div>

        {map.read_first.length ? (
          <ol className={styles.readFirstList}>
            {map.read_first.map((item, index) => (
              <li key={`${item.file_id}:${item.start_line}:${item.end_line}`}>
                <button
                  type="button"
                  aria-label={`코드 열기: ${item.path}`}
                  onClick={() => onOpenEvidence(item)}
                >
                  <span className={styles.readFirstNumber}>{index + 1}</span>
                  <span className={styles.readFirstCopy}>
                    <span>
                      <code>{item.path}</code>
                      <small>{formatLines(item.start_line, item.end_line)}</small>
                      <ConfidenceBadge value={item.confidence} />
                    </span>
                    <strong>{item.reason}</strong>
                  </span>
                  <span className={styles.openCode}>
                    코드 열기
                    <ArrowRight aria-hidden size={14} />
                  </span>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p className={styles.inlineEmpty}>먼저 읽을 코드를 고를 근거가 아직 충분하지 않습니다.</p>
        )}
      </section>

      <section className={styles.limitations} aria-labelledby="limitations-heading">
        <div className={styles.limitationsHeading}>
          <AlertTriangle aria-hidden size={17} />
          <div>
            <h2 id="limitations-heading">이 지도를 읽을 때 알아둘 점</h2>
            <p>코드 근거와 추정을 구분해 과신하지 않도록 표시했습니다.</p>
          </div>
        </div>
        {map.limitations.length ? (
          <ul>
            {map.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.noLimitations}>현재 분석에서 별도로 확인된 제한 사항은 없습니다.</p>
        )}
        <div className={styles.legend} aria-label="분석 신뢰도 범례">
          <ConfidenceBadge value="verified" />
          <ConfidenceBadge value="inferred" />
          <ConfidenceBadge value="unknown" />
        </div>
      </section>

      {map.tech_stack.length ? (
        <footer className={styles.techFooter}>
          <Box aria-hidden size={14} />
          <strong>확인한 기술</strong>
          <div>
            {map.tech_stack.map((tech) => (
              <span key={`${tech.category}:${tech.name}`}>{tech.name}</span>
            ))}
          </div>
        </footer>
      ) : null}
    </section>
  );
}
