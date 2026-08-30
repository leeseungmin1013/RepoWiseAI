"use client";

import {
  Activity,
  Braces,
  CheckCircle2,
  Cloud,
  CloudOff,
  FolderTree,
  GitBranch,
  LoaderCircle,
  PanelRight,
  Play,
  ShieldAlert,
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type ActivityAttemptSummary,
  type ArchitectureGraph,
  type ArchitectureGraphDiff,
  type AssessmentSession,
  type ChatAnswer,
  type ChangeBrief,
  type Citation,
  type CodeExplanation,
  type CodeExplanationDepth,
  type CodeSelection,
  type DeepTask,
  type DeepTaskRequest,
  type FeatureFlowCatalog,
  type FeatureFlowDetail,
  type FeatureFlowEvidence,
  type GraphData,
  type Health,
  type LearnerProfile,
  type LearningActivity,
  type LearningFeedbackType,
  type LearningLesson,
  type LearningModule,
  type LearningPath,
  type LearningSession,
  type RoadmapProposal,
  type MasteryOverview,
  type ProjectMapEvidence,
  type RemediationBranch,
  type RemediationMode,
  type RepositoryStory,
  type Snapshot,
  type SourceFile,
  type StartHere,
  type SymbolRecord,
  type TeachingStyle,
  type TreeNode,
} from "@/lib/api";
import { useRealtimeLearningSession } from "@/hooks/useRealtimeLearningSession";
import { useDeepLearningTask } from "@/hooks/useDeepLearningTask";
import { routeQuestionToDeepTask } from "@/lib/deep-tasks";

import { AssistantPanel } from "./AssistantPanel";
import { AuthUserMenu } from "./AuthUserMenu";
import { ChangeBriefPanel } from "./ChangeBriefPanel";
import { CodeFocusPanel } from "./CodeFocusPanel";
import { CodePanel, type CodeHighlight } from "./CodePanel";
import { FeatureFlowPanel } from "./FeatureFlowPanel";
import { FileTree } from "./FileTree";
import { RepositoryStoryPage } from "./RepositoryStoryPage";
import { StartHerePanel } from "./StartHerePanel";

const STAGES = [
  "pending",
  "fetching",
  "filtering",
  "parsing",
  "graph_building",
  "chunking",
  "embedding",
  "guidance",
  "ready",
];
const STAGE_LABELS: Record<string, string> = {
  pending: "대기 중",
  fetching: "저장소 수집",
  filtering: "파일 선별",
  parsing: "심볼 분석",
  graph_building: "관계 생성",
  chunking: "코드 청킹",
  embedding: "검색 인덱싱",
  guidance: "지도 근거 구성",
  ready: "분석 완료",
};

type MobilePane = "tree" | "code" | "guide";
type WorkspaceMode = "map" | "flow" | "explorer" | "change" | "learning";

function summaryMetric(summary: Record<string, unknown> | undefined, key: string) {
  const value = summary?.[key];
  return typeof value === "number" ? value : 0;
}

export function RepositoryWorkbench() {
  const architectureLabelEnhancementEnabled =
    process.env.NEXT_PUBLIC_NAVIGATION_LLM_LABELS_ENABLED === "true";
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [reuseNotice, setReuseNotice] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [assessment, setAssessment] = useState<AssessmentSession | null>(null);
  const [assessmentBusy, setAssessmentBusy] = useState(false);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [file, setFile] = useState<SourceFile | null>(null);
  const [symbols, setSymbols] = useState<SymbolRecord[]>([]);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [startHere, setStartHere] = useState<StartHere | null>(null);
  const [repositoryStory, setRepositoryStory] = useState<RepositoryStory | null>(null);
  const [architectureGraph, setArchitectureGraph] = useState<ArchitectureGraph | null>(null);
  const [architectureGraphLoading, setArchitectureGraphLoading] = useState(false);
  const [architectureGraphError, setArchitectureGraphError] = useState<string | null>(null);
  const [architectureGraphDiff, setArchitectureGraphDiff] =
    useState<ArchitectureGraphDiff | null>(null);
  const [architectureDiffLoading, setArchitectureDiffLoading] = useState(false);
  const [architectureLabelsLoading, setArchitectureLabelsLoading] = useState(false);
  const [featureFlowCatalog, setFeatureFlowCatalog] =
    useState<FeatureFlowCatalog | null>(null);
  const [selectedFeatureFlowId, setSelectedFeatureFlowId] = useState<string | null>(null);
  const [featureFlowDetail, setFeatureFlowDetail] = useState<FeatureFlowDetail | null>(null);
  const [featureFlowLoading, setFeatureFlowLoading] = useState(false);
  const [featureFlowDetailLoading, setFeatureFlowDetailLoading] = useState(false);
  const [featureFlowError, setFeatureFlowError] = useState<string | null>(null);
  const [featureFlowReload, setFeatureFlowReload] = useState(0);
  const [explorerLoading, setExplorerLoading] = useState(false);
  const [learningPath, setLearningPath] = useState<LearningPath | null>(null);
  const [learningSession, setLearningSession] = useState<LearningSession | null>(null);
  const [learningActivity, setLearningActivity] = useState<LearningActivity | null>(null);
  const [activityAttempt, setActivityAttempt] = useState<ActivityAttemptSummary | null>(null);
  const [activityBusy, setActivityBusy] = useState(false);
  const [masteryOverview, setMasteryOverview] = useState<MasteryOverview | null>(null);
  const [masteryLoading, setMasteryLoading] = useState(false);
  const [remediation, setRemediation] = useState<RemediationBranch | null>(null);
  const [journeyBusy, setJourneyBusy] = useState(false);
  const [roadmapProposal, setRoadmapProposal] = useState<RoadmapProposal | null>(null);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [sessionTeachingStyle, setSessionTeachingStyle] = useState<TeachingStyle | null>(null);
  const [teachingStyle, setTeachingStyle] = useState<TeachingStyle>("beginner");
  const [answers, setAnswers] = useState<ChatAnswer[]>([]);
  const [asking, setAsking] = useState(false);
  const [selection, setSelection] = useState<CodeSelection | null>(null);
  const [codeExplanation, setCodeExplanation] = useState<CodeExplanation | null>(null);
  const [codeFocusLoading, setCodeFocusLoading] = useState(false);
  const [codeFocusError, setCodeFocusError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<CodeHighlight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [view, setView] = useState<"code" | "graph">("code");
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("map");
  const [mobilePane, setMobilePane] = useState<MobilePane>("code");
  const loadedRepositoryStory = useRef<string | null>(null);
  const loadedFeatureFlowCatalog = useRef<string | null>(null);
  const loadedFeatureFlowDetail = useRef<string | null>(null);
  const loadedExplorer = useRef<string | null>(null);
  const featureFlowDetailRequestSequence = useRef(0);
  const openFileRequestSequence = useRef(0);
  const codeFocusRequestSequence = useRef(0);
  const codeFocusContext = useRef<{
    featureFlowId?: string | null;
    flowStepId?: string | null;
  } | null>(null);
  const loadedSnapshot = useRef<string | null>(null);
  const assessmentRequest = useRef<string | null>(null);
  const voiceQuestionHandler = useRef<(transcript: string) => void>(() => undefined);
  const voiceLearningSessionId = useRef<string | null>(null);
  const deepLearningSessionId = useRef<string | null>(null);
  const activeAssessmentId =
    workspaceMode === "learning" && assessment?.status === "active"
      ? assessment.id
      : null;
  const masteryProfileId =
    workspaceMode === "learning" && assessment && assessment.status !== "active"
      ? profile?.id ?? null
      : null;
  const exchangeVoiceSdp = useCallback(
    (sdp: string, signal: AbortSignal, vadEnabled: boolean) => {
      if (!learningSession) {
        return Promise.reject(new Error("먼저 학습 세션을 시작해 주세요."));
      }
      return api.exchangeVoiceOffer(
        learningSession.id,
        sdp,
        signal,
        vadEnabled,
      );
    },
    [learningSession],
  );
  const handleFinalVoiceTranscript = useCallback((transcript: string) => {
    voiceQuestionHandler.current(transcript);
  }, []);
  const voiceSession = useRealtimeLearningSession({
    exchangeSdp: exchangeVoiceSdp,
    onFinalTranscript: handleFinalVoiceTranscript,
    stopSession: api.stopVoiceSession,
  });
  const {
    isConnected: isVoiceConnected,
    speakVerifiedText,
    stop: stopVoiceSession,
  } = voiceSession;
  const handleDeepTaskCompleted = useCallback(
    (
      answer: import("@/lib/api").DeepTaskResult,
      _task: DeepTask,
      request: DeepTaskRequest | null,
    ) => {
      if ("session_id" in answer) {
        setAnswers((current) =>
          current.some((item) => item.id === answer.id)
            ? current
            : [...current, answer],
        );
      }
      if (request?.modality === "voice") {
        if ("session_id" in answer) {
          speakVerifiedText(answerForVoice(answer));
        } else if ("voice_summary" in answer) {
          speakVerifiedText(answer.voice_summary || answer.answer);
        }
      }
    },
    [speakVerifiedText],
  );
  const deepLearningTask = useDeepLearningTask({
    onCompleted: handleDeepTaskCompleted,
  });
  const changeBriefTask = useDeepLearningTask({
    createTask: api.createNavigationDeepTask,
  });
  const {
    cancel: cancelDeepTask,
    error: deepTaskError,
    isCancelling: isDeepTaskCancelling,
    isRunning: isDeepTaskRunning,
    isStarting: isDeepTaskStarting,
    reset: resetDeepTask,
    start: startDeepTask,
    task: activeDeepTask,
  } = deepLearningTask;
  const {
    cancel: cancelChangeBrief,
    error: changeBriefError,
    isCancelling: isChangeBriefCancelling,
    isStarting: isChangeBriefStarting,
    reset: resetChangeBrief,
    start: startChangeBriefTask,
    task: activeChangeBriefTask,
  } = changeBriefTask;
  const completedChangeBrief = useMemo<ChangeBrief | null>(() => {
    const result = activeChangeBriefTask?.result;
    return result && "confirmed_direct_impacts" in result ? result : null;
  }, [activeChangeBriefTask?.result]);

  useEffect(() => {
    const nextSessionId = learningSession?.id ?? null;
    if (
      voiceLearningSessionId.current &&
      voiceLearningSessionId.current !== nextSessionId &&
      isVoiceConnected
    ) {
      stopVoiceSession();
    }
    voiceLearningSessionId.current = nextSessionId;
  }, [isVoiceConnected, learningSession?.id, stopVoiceSession]);

  useEffect(() => {
    if (workspaceMode !== "learning" && isVoiceConnected) {
      stopVoiceSession();
    }
  }, [isVoiceConnected, stopVoiceSession, workspaceMode]);

  useEffect(() => {
    const nextSessionId = learningSession?.id ?? null;
    if (
      deepLearningSessionId.current &&
      deepLearningSessionId.current !== nextSessionId
    ) {
      resetDeepTask();
    }
    deepLearningSessionId.current = nextSessionId;
  }, [learningSession?.id, resetDeepTask]);

  useEffect(() => {
    let cancelled = false;
    let anonymousKey = window.localStorage.getItem("repowise-learner-key");
    if (!anonymousKey) {
      anonymousKey = `learner-${window.crypto.randomUUID()}`;
      window.localStorage.setItem("repowise-learner-key", anonymousKey);
    }
    Promise.allSettled([
      api.health(),
      api.listSnapshots(),
      api.createLearnerProfile(anonymousKey),
    ]).then(([healthResult, snapshotsResult, profileResult]) => {
      if (cancelled) return;
      if (healthResult.status === "fulfilled") setHealth(healthResult.value);
      if (snapshotsResult.status === "fulfilled" && snapshotsResult.value.length) {
        setSnapshots(snapshotsResult.value);
        setSnapshot(snapshotsResult.value[0]);
      }
      if (profileResult.status === "fulfilled") {
        setProfile(profileResult.value);
      } else {
        setError(errorMessage(profileResult.reason));
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const polledSnapshotId =
    snapshot &&
    ["pending", "analyzing"].includes(snapshot.status) &&
    snapshot.job?.runtime_state !== "stalled"
      ? snapshot.id
      : null;

  useEffect(() => {
    if (!polledSnapshotId) return;
    const snapshotId = polledSnapshotId;
    const startedAt = Date.now();
    let cancelled = false;
    let timer: number | null = null;
    const poll = async () => {
      try {
        const nextSnapshot = await api.getSnapshot(snapshotId);
        if (!cancelled) {
          setSnapshot(nextSnapshot);
          setSnapshots((current) =>
            current.map((item) => (item.id === nextSnapshot.id ? nextSnapshot : item)),
          );
        }
        if (
          nextSnapshot.status === "ready" ||
          nextSnapshot.status === "failed" ||
          nextSnapshot.job?.runtime_state === "stalled"
        ) {
          return;
        }
      } catch (reason) {
        if (!cancelled) setError(errorMessage(reason));
      }
      if (cancelled) return;
      const elapsed = Date.now() - startedAt;
      const delay = elapsed >= 120_000 ? 10_000 : elapsed >= 30_000 ? 5_000 : 2_000;
      timer = window.setTimeout(() => void poll(), delay);
    };
    timer = window.setTimeout(() => void poll(), 2_000);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [polledSnapshotId]);

  useEffect(() => {
    if (
      !snapshot ||
      snapshot.status !== "ready" ||
      workspaceMode !== "map"
    ) {
      return;
    }
    const snapshotId = snapshot.id;
    if (repositoryStory?.snapshot_id === snapshotId) return;
    if (loadedRepositoryStory.current === snapshotId) return;
    loadedRepositoryStory.current = snapshotId;
    let cancelled = false;
    setArchitectureGraphLoading(true);
    setArchitectureGraphError(null);
    api
      .getRepositoryStory(snapshotId)
      .then((nextStory) => {
        if (cancelled) return;
        setRepositoryStory(nextStory);
        setArchitectureGraph(nextStory.implementation_graph);
        setFeatureFlowCatalog({
          repository_name: nextStory.repository_name,
          snapshot_id: nextStory.snapshot_id,
          commit_sha: nextStory.commit_sha,
          analysis_version: nextStory.analysis_version,
          flows: nextStory.features,
          limitations: nextStory.limitations,
        });
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        loadedRepositoryStory.current = null;
        setArchitectureGraphError(errorMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setArchitectureGraphLoading(false);
      });
    return () => {
      cancelled = true;
      if (loadedRepositoryStory.current === snapshotId) {
        loadedRepositoryStory.current = null;
      }
    };
  }, [repositoryStory?.snapshot_id, snapshot, workspaceMode]);

  useEffect(() => {
    const needsFlows = workspaceMode === "flow";
    if (!snapshot || snapshot.status !== "ready" || !needsFlows) return;
    const snapshotId = snapshot.id;
    if (featureFlowCatalog?.snapshot_id === snapshotId) return;
    if (loadedFeatureFlowCatalog.current === snapshotId) return;
    loadedFeatureFlowCatalog.current = snapshotId;
    let cancelled = false;
    setFeatureFlowLoading(true);
    setFeatureFlowError(null);
    api
      .getFeatureFlows(snapshotId)
      .then((nextCatalog) => {
        if (!cancelled) setFeatureFlowCatalog(nextCatalog);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        loadedFeatureFlowCatalog.current = null;
        setFeatureFlowError(errorMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setFeatureFlowLoading(false);
      });
    return () => {
      cancelled = true;
      if (loadedFeatureFlowCatalog.current === snapshotId) {
        loadedFeatureFlowCatalog.current = null;
      }
    };
  }, [featureFlowCatalog?.snapshot_id, featureFlowReload, snapshot, workspaceMode]);

  useEffect(() => {
    if (
      !snapshot ||
      snapshot.status !== "ready" ||
      (workspaceMode !== "flow" && workspaceMode !== "map") ||
      !selectedFeatureFlowId
    ) {
      return;
    }
    const requestKey = `${snapshot.id}:${selectedFeatureFlowId}`;
    if (
      featureFlowDetail?.id === selectedFeatureFlowId ||
      loadedFeatureFlowDetail.current === requestKey
    ) {
      return;
    }
    loadedFeatureFlowDetail.current = requestKey;
    const requestSequence = ++featureFlowDetailRequestSequence.current;
    let cancelled = false;
    setFeatureFlowDetailLoading(true);
    setFeatureFlowError(null);
    api
      .getFeatureFlow(snapshot.id, selectedFeatureFlowId)
      .then((nextFlow) => {
        if (
          !cancelled &&
          featureFlowDetailRequestSequence.current === requestSequence
        ) {
          setFeatureFlowDetail(nextFlow);
        }
      })
      .catch((reason: unknown) => {
        if (
          cancelled ||
          featureFlowDetailRequestSequence.current !== requestSequence
        ) {
          return;
        }
        loadedFeatureFlowDetail.current = null;
        setFeatureFlowError(errorMessage(reason));
      })
      .finally(() => {
        if (featureFlowDetailRequestSequence.current === requestSequence) {
          setFeatureFlowDetailLoading(false);
        }
      });
    return () => {
      cancelled = true;
      if (featureFlowDetailRequestSequence.current === requestSequence) {
        featureFlowDetailRequestSequence.current += 1;
        setFeatureFlowDetailLoading(false);
      }
      if (loadedFeatureFlowDetail.current === requestKey) {
        loadedFeatureFlowDetail.current = null;
      }
    };
  }, [featureFlowDetail, featureFlowReload, selectedFeatureFlowId, snapshot, workspaceMode]);

  useEffect(() => {
    if (
      !snapshot ||
      snapshot.status !== "ready" ||
      (workspaceMode !== "explorer" &&
        workspaceMode !== "change" &&
        workspaceMode !== "learning")
    ) {
      return;
    }
    const snapshotId = snapshot.id;
    if (loadedExplorer.current === snapshotId) return;
    loadedExplorer.current = snapshotId;
    let cancelled = false;
    setExplorerLoading(true);
    Promise.all([
      api.getTree(snapshotId),
      api.getStartHere(snapshotId),
      api.getGraph(snapshotId),
    ])
      .then(([nextTree, nextStartHere, nextGraph]) => {
        if (cancelled) return;
        setTree(nextTree);
        setStartHere(nextStartHere);
        setGraph(nextGraph);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        loadedExplorer.current = null;
        setError(errorMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setExplorerLoading(false);
      });
    return () => {
      cancelled = true;
      if (loadedExplorer.current === snapshotId) {
        loadedExplorer.current = null;
      }
    };
  }, [snapshot, workspaceMode]);

  useEffect(() => {
    if (!activeAssessmentId) return;
    const interval = window.setInterval(() => {
      api
        .getAssessmentSession(activeAssessmentId)
        .then((next) => {
          setAssessment(next);
          setProfile(next.profile);
        })
        .catch((reason: unknown) => setError(errorMessage(reason)));
    }, 1_500);
    return () => window.clearInterval(interval);
  }, [activeAssessmentId]);

  useEffect(() => {
    if (!masteryProfileId) return;
    let cancelled = false;
    api
      .getMasteryOverview(masteryProfileId)
      .then((next) => {
        if (!cancelled) setMasteryOverview(next);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(errorMessage(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [masteryProfileId]);

  useEffect(() => {
    if (
      workspaceMode !== "learning" ||
      !snapshot ||
      !profile ||
      assessment?.snapshot_id === snapshot.id
    ) {
      return;
    }
    const requestKey = `${snapshot.id}:${profile.id}`;
    if (assessmentRequest.current === requestKey) return;
    assessmentRequest.current = requestKey;
    api
      .createAssessmentSession(snapshot.id, profile.id)
      .then((nextAssessment) => {
        setAssessment(nextAssessment);
        setProfile(nextAssessment.profile);
      })
      .catch((reason: unknown) => {
        assessmentRequest.current = null;
        setError(errorMessage(reason));
      });
  }, [assessment, profile, snapshot, workspaceMode]);

  useEffect(() => {
    const assessmentFinished = assessment && assessment.status !== "active";
    if (
      workspaceMode !== "learning" ||
      !snapshot ||
      snapshot.status !== "ready" ||
      !profile ||
      !assessmentFinished ||
      assessment.snapshot_id !== snapshot.id
    ) {
      return;
    }
    const loadKey = `${snapshot.id}:${profile.id}`;
    if (loadedSnapshot.current === loadKey) return;
    loadedSnapshot.current = loadKey;
    const snapshotId = snapshot.id;
    const style = styleForProfile(profile);
    setTeachingStyle(style);
    setJourneyBusy(true);

    api
      .createLearningPath(snapshotId, profile.id)
      .then(async (nextPath) => {
        const nextSession = await api.createLearningSession(nextPath.id, style);
        setLearningPath(nextPath);
        setLearningSession(nextSession);
        setChatSessionId(nextSession.chat_session_id);
        setSessionTeachingStyle(style);
        const [recentAnswers, activeRemediation] = await Promise.all([
          api.getChatAnswers(nextSession.chat_session_id),
          api.getActiveRemediation(nextSession.id),
        ]);
        setAnswers(recentAnswers);
        setRemediation(activeRemediation);

        const current = findCurrentLesson(nextPath, nextSession);
        const evidence = current?.lesson.steps[0]?.evidence;
        const fileId = evidence?.file_id;
        if (fileId) {
          setFileLoading(true);
          const [nextFile, nextSymbols] = await Promise.all([
            api.getFile(snapshotId, fileId),
            api.getSymbols(snapshotId, fileId),
          ]);
          setFile(nextFile);
          setSymbols(nextSymbols);
          setHighlight(
            evidence
              ? {
                  fileId: evidence.file_id,
                  startLine: evidence.start_line,
                  endLine: evidence.end_line,
                }
              : null,
          );
          setFileLoading(false);
        }
      })
      .catch((reason: unknown) => {
        loadedSnapshot.current = null;
        setFileLoading(false);
        setError(errorMessage(reason));
      })
      .finally(() => setJourneyBusy(false));
  }, [assessment, profile, snapshot, workspaceMode]);

  useEffect(() => {
    if (!selection || !learningSession) return;
    const timer = window.setTimeout(() => {
      api
        .updateLearningSelection(learningSession.id, selection)
        .catch((reason: unknown) => setError(errorMessage(reason)));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [learningSession, selection]);

  useEffect(() => {
    const sessionId = learningSession?.id;
    const stepId = learningSession?.current_step_id;
    if (!sessionId || !stepId) return;
    let cancelled = false;
    api
      .createLearningActivity(sessionId, stepId)
      .then((next) => {
        if (cancelled) return;
        setLearningActivity(next);
        setActivityAttempt(next.latest_attempt);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!cancelled) setActivityBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [learningSession?.current_step_id, learningSession?.id]);

  async function submitRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    resetRepositoryState();
    try {
      const response = await api.createRepository(repositoryUrl, branch);
      setReuseNotice(
        response.reuse?.mode === "exact_snapshot"
          ? "기존 분석을 즉시 재사용했습니다."
          : response.reuse?.mode === "incremental"
            ? "변경 파일 중심으로 증분 분석합니다."
            : response.reuse
              ? "전체 저장소를 분석합니다."
              : null,
      );
      setSnapshot(response.snapshot);
      setSnapshots((current) => [
        response.snapshot,
        ...current.filter((item) => item.id !== response.snapshot.id),
      ]);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  async function retryAnalysis() {
    if (!snapshot || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const nextSnapshot = await api.retrySnapshot(snapshot.id);
      setSnapshot(nextSnapshot);
      setSnapshots((current) =>
        current.map((item) => (item.id === nextSnapshot.id ? nextSnapshot : item)),
      );
      setReuseNotice("분석을 새 작업으로 다시 시작했습니다.");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  function resetRepositoryState() {
    resetDeepTask();
    resetChangeBrief();
    setAssessment(null);
    setTree([]);
    setFile(null);
    setSymbols([]);
    setGraph(null);
    setStartHere(null);
    setRepositoryStory(null);
    setArchitectureGraph(null);
    setArchitectureGraphLoading(false);
    setArchitectureGraphError(null);
    setArchitectureGraphDiff(null);
    setArchitectureDiffLoading(false);
    setArchitectureLabelsLoading(false);
    setFeatureFlowCatalog(null);
    setSelectedFeatureFlowId(null);
    setFeatureFlowDetail(null);
    setFeatureFlowLoading(false);
    setFeatureFlowDetailLoading(false);
    setFeatureFlowError(null);
    setFeatureFlowReload(0);
    featureFlowDetailRequestSequence.current += 1;
    openFileRequestSequence.current += 1;
    codeFocusRequestSequence.current += 1;
    codeFocusContext.current = null;
    setFileLoading(false);
    setExplorerLoading(false);
    setLearningPath(null);
    setLearningSession(null);
    setLearningActivity(null);
    setActivityAttempt(null);
    setActivityBusy(false);
    setMasteryOverview(null);
    setMasteryLoading(false);
    setRemediation(null);
    setJourneyBusy(false);
    setRoadmapProposal(null);
    setChatSessionId(null);
    setSessionTeachingStyle(null);
    setAnswers([]);
    setSelection(null);
    setCodeExplanation(null);
    setCodeFocusLoading(false);
    setCodeFocusError(null);
    setHighlight(null);
    setWorkspaceMode("map");
    setMobilePane("code");
    loadedRepositoryStory.current = null;
    loadedFeatureFlowCatalog.current = null;
    loadedFeatureFlowDetail.current = null;
    loadedExplorer.current = null;
    loadedSnapshot.current = null;
    assessmentRequest.current = null;
  }

  function showProjectMap() {
    setWorkspaceMode("map");
  }

  function openExplorer() {
    setWorkspaceMode("explorer");
    setMobilePane("code");
  }

  function openChangeBrief() {
    setWorkspaceMode("change");
    setMobilePane("guide");
  }

  function openFeatureFlows(flowId?: string) {
    featureFlowDetailRequestSequence.current += 1;
    setWorkspaceMode("flow");
    setFeatureFlowError(null);
    setSelectedFeatureFlowId(flowId ?? null);
    setFeatureFlowDetail(null);
    setFeatureFlowDetailLoading(false);
  }

  function showFeatureFlowCatalog() {
    featureFlowDetailRequestSequence.current += 1;
    setFeatureFlowError(null);
    setSelectedFeatureFlowId(null);
    setFeatureFlowDetail(null);
    setFeatureFlowDetailLoading(false);
    loadedFeatureFlowDetail.current = null;
  }

  function retryFeatureFlow() {
    setFeatureFlowError(null);
    if (selectedFeatureFlowId) {
      setFeatureFlowDetail(null);
      loadedFeatureFlowDetail.current = null;
    } else {
      setFeatureFlowCatalog(null);
      loadedFeatureFlowCatalog.current = null;
    }
    setFeatureFlowReload((current) => current + 1);
  }

  function startLearning() {
    setWorkspaceMode("learning");
    setMobilePane("guide");
  }

  function openNavigationEvidence(
    evidence: ProjectMapEvidence | FeatureFlowEvidence,
    context?: { featureFlowId?: string | null; flowStepId?: string | null },
  ) {
    const nextSelection: CodeSelection = {
      file_id: evidence.file_id,
      start_line: evidence.start_line,
      end_line: evidence.end_line,
    };
    setWorkspaceMode("explorer");
    setMobilePane("code");
    void openFile(evidence.file_id, {
      fileId: evidence.file_id,
      startLine: evidence.start_line,
      endLine: evidence.end_line,
    });
    setSelection(nextSelection);
    codeFocusContext.current = context ?? null;
    void loadCodeFocus(nextSelection, "minimum", context);
  }

  function openMapEvidence(evidence: ProjectMapEvidence) {
    openNavigationEvidence(evidence);
  }

  function openFeatureFlowEvidence(
    evidence: FeatureFlowEvidence,
    context?: { featureFlowId: string; flowStepId?: string },
  ) {
    openNavigationEvidence(evidence, context);
  }

  async function answerAssessment(itemId: string, answer: string) {
    if (!assessment || assessmentBusy) return;
    setAssessmentBusy(true);
    setError(null);
    try {
      const next = await api.answerAssessment(assessment.id, itemId, answer);
      setAssessment(next);
      setProfile(next.profile);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setAssessmentBusy(false);
    }
  }

  async function submitAssessment() {
    if (!assessment || assessmentBusy) return;
    setAssessmentBusy(true);
    setError(null);
    try {
      const next = await api.submitAssessment(assessment.id);
      setAssessment(next);
      setProfile(next.profile);
      loadedSnapshot.current = null;
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setAssessmentBusy(false);
    }
  }

  async function skipAssessment() {
    if (!assessment || assessmentBusy) return;
    setAssessmentBusy(true);
    setError(null);
    try {
      const next = await api.skipAssessment(assessment.id);
      setAssessment(next);
      setProfile(next.profile);
      loadedSnapshot.current = null;
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setAssessmentBusy(false);
    }
  }

  async function openFile(fileId: string, nextHighlight: CodeHighlight | null = null) {
    if (!snapshot) return;
    const requestSequence = ++openFileRequestSequence.current;
    const snapshotId = snapshot.id;
    setFileLoading(true);
    setError(null);
    setSelection(null);
    setCodeExplanation(null);
    setCodeFocusError(null);
    setCodeFocusLoading(false);
    codeFocusRequestSequence.current += 1;
    codeFocusContext.current = null;
    try {
      const [nextFile, nextSymbols] = await Promise.all([
        api.getFile(snapshotId, fileId),
        api.getSymbols(snapshotId, fileId),
      ]);
      if (openFileRequestSequence.current !== requestSequence) return;
      setFile(nextFile);
      setSymbols(nextSymbols);
      setHighlight(nextHighlight);
      setView("code");
      setMobilePane("code");
    } catch (reason) {
      if (openFileRequestSequence.current === requestSequence) {
        setError(errorMessage(reason));
      }
    } finally {
      if (openFileRequestSequence.current === requestSequence) {
        setFileLoading(false);
      }
    }
  }

  async function loadCodeFocus(
    targetSelection: CodeSelection,
    depth: CodeExplanationDepth = "minimum",
    context = codeFocusContext.current ?? undefined,
  ) {
    if (!snapshot) return;
    const requestSequence = ++codeFocusRequestSequence.current;
    const snapshotId = snapshot.id;
    codeFocusContext.current = context ?? null;
    setCodeFocusLoading(true);
    setCodeFocusError(null);
    try {
      const explanation = await api.createCodeExplanation(
        snapshotId,
        targetSelection,
        depth,
        context,
      );
      if (codeFocusRequestSequence.current !== requestSequence) return;
      setCodeExplanation(explanation);
      setSelection(explanation.selection);
    } catch (reason) {
      if (codeFocusRequestSequence.current === requestSequence) {
        setCodeFocusError(errorMessage(reason));
      }
    } finally {
      if (codeFocusRequestSequence.current === requestSequence) {
        setCodeFocusLoading(false);
      }
    }
  }

  function explainCurrentSelection(depth: CodeExplanationDepth) {
    const targetSelection = codeExplanation?.selection ?? selection;
    if (!targetSelection) return;
    void loadCodeFocus(targetSelection, depth);
  }

  async function requestChangeBrief(prompt: string) {
    if (!snapshot || !selection) return;
    try {
      let sessionId = learningSession?.chat_session_id ?? chatSessionId;
      if (!sessionId) {
        const session = await api.createChatSession(snapshot.id, teachingStyle);
        sessionId = session.id;
        setChatSessionId(sessionId);
        setSessionTeachingStyle(session.preferred_style as TeachingStyle);
      }
      await startChangeBriefTask(sessionId, {
        kind: "impact_analysis",
        prompt,
        selection,
        navigation_context: {
          feature_key:
            codeFocusContext.current?.featureFlowId ?? selectedFeatureFlowId,
          flow_step_id: codeFocusContext.current?.flowStepId ?? null,
          selection,
          explanation_depth: codeExplanation?.depth ?? "minimum",
        },
        modality: "text",
      });
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  function openChangeBriefEvidence(evidence: ProjectMapEvidence) {
    void openFile(evidence.file_id, {
      fileId: evidence.file_id,
      startLine: evidence.start_line,
      endLine: evidence.end_line,
    });
    setSelection({
      file_id: evidence.file_id,
      start_line: evidence.start_line,
      end_line: evidence.end_line,
    });
    setWorkspaceMode("change");
  }

  function requestArchitectureChangeBrief(evidence: ProjectMapEvidence) {
    openChangeBriefEvidence(evidence);
    setMobilePane("guide");
  }

  async function compareArchitectureSnapshot(baseSnapshotId: string | null) {
    if (!snapshot || !baseSnapshotId) {
      setArchitectureGraphDiff(null);
      return;
    }
    setArchitectureDiffLoading(true);
    setArchitectureGraphError(null);
    try {
      setArchitectureGraphDiff(
        await api.getArchitectureGraphDiff(snapshot.id, baseSnapshotId),
      );
    } catch (reason) {
      setArchitectureGraphError(errorMessage(reason));
    } finally {
      setArchitectureDiffLoading(false);
    }
  }

  async function enhanceArchitectureLabels() {
    if (!snapshot || architectureLabelsLoading) return;
    setArchitectureLabelsLoading(true);
    setArchitectureGraphError(null);
    try {
      const enhanced = await api.enhanceArchitectureGraphLabels(snapshot.id);
      setArchitectureGraph(enhanced);
      setRepositoryStory((current) =>
        current ? { ...current, implementation_graph: enhanced } : current,
      );
    } catch (reason) {
      setArchitectureGraphError(errorMessage(reason));
    } finally {
      setArchitectureLabelsLoading(false);
    }
  }

  function openCodeFocusEvidence(evidence: ProjectMapEvidence) {
    if (file?.id === evidence.file_id) {
      setHighlight({
        fileId: evidence.file_id,
        startLine: evidence.start_line,
        endLine: evidence.end_line,
      });
      setSelection({
        file_id: evidence.file_id,
        start_line: evidence.start_line,
        end_line: evidence.end_line,
      });
      setMobilePane("code");
      return;
    }
    openNavigationEvidence(evidence);
  }

  function openEvidence(citation: Citation) {
    void openFile(citation.file_id, {
      fileId: citation.file_id,
      startLine: citation.start_line,
      endLine: citation.end_line,
    });
  }

  function openLines(fileId: string, startLine: number, endLine: number) {
    void openFile(fileId, { fileId, startLine, endLine });
  }

  async function openLearningLesson(
    _learningModule: LearningModule,
    lesson: LearningLesson,
  ) {
    if (!learningSession || journeyBusy) return;
    setJourneyBusy(true);
    setError(null);
    setRemediation(null);
    try {
      const next = await api.recordLearningFeedback(
        learningSession.id,
        lesson.id,
        "opened",
      );
      setLearningSession(next);
      const evidence = lesson.steps[0]?.evidence;
      if (evidence) openEvidence(evidence);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setJourneyBusy(false);
    }
  }

  async function updateLearningProgress(
    lesson: LearningLesson,
    eventType: LearningFeedbackType,
  ) {
    if (!learningSession || !learningPath || journeyBusy) return;
    setJourneyBusy(true);
    setError(null);
    try {
      const next = await api.recordLearningFeedback(
        learningSession.id,
        lesson.id,
        eventType,
      );
      setLearningSession(next);
      if (eventType === "needs_help") {
        setRemediation(null);
      } else if (eventType === "understood" || eventType === "skip") {
        setRemediation(null);
        const current = findCurrentLesson(learningPath, next);
        const evidence = current?.lesson.steps[0]?.evidence;
        if (evidence) openEvidence(evidence);
      }
      void refreshMastery();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setJourneyBusy(false);
    }
  }

  async function submitActivity(selectedChoiceId: string) {
    if (!learningSession || !learningActivity || activityBusy) return;
    setActivityBusy(true);
    setError(null);
    try {
      const attempt = await api.submitActivityAttempt(
        learningSession.id,
        learningActivity.id,
        selectedChoiceId,
      );
      setActivityAttempt(attempt);
      await refreshMastery();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setActivityBusy(false);
    }
  }

  async function replanJourney() {
    if (!learningSession || journeyBusy) return;
    setJourneyBusy(true);
    setError(null);
    try {
      setRoadmapProposal(
        await api.createRoadmapProposal(learningSession.id, {
          focusConceptIds: learningSession.focus_concept_ids,
        }),
      );
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setJourneyBusy(false);
    }
  }

  async function applyRoadmapProposal() {
    if (!roadmapProposal || journeyBusy) return;
    setJourneyBusy(true);
    setError(null);
    try {
      const result = await api.applyRoadmapProposal(roadmapProposal.id);
      setLearningPath(result.path);
      setLearningSession(result.session);
      setRoadmapProposal(null);
      setRemediation(null);
      const current = findCurrentLesson(result.path, result.session);
      const evidence = current?.lesson.steps[0]?.evidence;
      if (evidence) openEvidence(evidence);
    } catch (reason) {
      setError(errorMessage(reason));
      const latest = await api.getRoadmapProposal(roadmapProposal.id).catch(() => null);
      if (latest) setRoadmapProposal(latest);
    } finally {
      setJourneyBusy(false);
    }
  }

  async function rejectRoadmapProposal() {
    if (!roadmapProposal || journeyBusy) return;
    setJourneyBusy(true);
    setError(null);
    try {
      await api.rejectRoadmapProposal(roadmapProposal.id);
      setRoadmapProposal(null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setJourneyBusy(false);
    }
  }

  async function refreshMastery() {
    if (!profile) return;
    setMasteryLoading(true);
    try {
      setMasteryOverview(await api.getMasteryOverview(profile.id));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setMasteryLoading(false);
    }
  }

  async function openHelp(mode: RemediationMode) {
    if (!learningSession || !learningPath || journeyBusy) return;
    const current = findCurrentLesson(learningPath, learningSession);
    if (!current) return;
    const step = current.lesson.steps[0] ?? null;
    setJourneyBusy(true);
    setError(null);
    try {
      const branchResponse = await api.createRemediation(
        learningSession.id,
        current.lesson.id,
        step?.id ?? null,
        mode,
      );
      setRemediation(branchResponse);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setJourneyBusy(false);
    }
  }

  async function completeHelp() {
    if (!remediation || journeyBusy) return;
    setJourneyBusy(true);
    setError(null);
    try {
      await api.completeRemediation(remediation.id);
      setRemediation(null);
      if (learningSession) {
        setLearningSession(await api.getLearningSession(learningSession.id));
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setJourneyBusy(false);
    }
  }

  const handleSelectionChange = useCallback(
    (nextSelection: CodeSelection | null) => {
      setSelection(nextSelection);
      if (
        nextSelection &&
        codeExplanation &&
        (codeExplanation.selection.file_id !== nextSelection.file_id ||
          codeExplanation.selection.start_line !== nextSelection.start_line ||
          codeExplanation.selection.end_line !== nextSelection.end_line)
      ) {
        codeFocusRequestSequence.current += 1;
        codeFocusContext.current = null;
        setCodeExplanation(null);
        setCodeFocusLoading(false);
        setCodeFocusError(null);
      }
    },
    [codeExplanation],
  );

  const requestQuestion = useCallback(
    async (
      question: string,
      modality: "text" | "voice",
    ): Promise<ChatAnswer | null> => {
      if (!snapshot) return null;
      const deepKind = routeQuestionToDeepTask(question);
      if (deepKind && learningSession) {
        if (isDeepTaskRunning) {
          setError(
            "이미 심층 작업이 진행 중입니다. 완료를 기다리는 동안 일반 질문은 계속할 수 있어요.",
          );
          return null;
        }
        setError(null);
        await startDeepTask(learningSession.id, {
          kind: deepKind,
          prompt: question,
          selection,
          modality,
        });
        return null;
      }
      if (asking) return null;
      setAsking(true);
      setError(null);
      try {
        let sessionId = learningSession?.chat_session_id ?? chatSessionId;
        if (!sessionId) {
          const session = await api.createChatSession(snapshot.id, teachingStyle);
          sessionId = session.id;
          setChatSessionId(sessionId);
          setSessionTeachingStyle(session.preferred_style as TeachingStyle);
        } else if (sessionTeachingStyle !== teachingStyle) {
          const session = await api.updateChatSession(sessionId, teachingStyle);
          setSessionTeachingStyle(session.preferred_style as TeachingStyle);
        }
        const answer = await api.ask(sessionId, question, selection, modality);
        setAnswers((current) => [...current, answer]);
        return answer;
      } catch (reason) {
        setError(errorMessage(reason));
        return null;
      } finally {
        setAsking(false);
      }
    },
    [
      asking,
      chatSessionId,
      isDeepTaskRunning,
      learningSession,
      selection,
      sessionTeachingStyle,
      snapshot,
      startDeepTask,
      teachingStyle,
    ],
  );

  const askQuestion = useCallback(
    async (question: string) => {
      await requestQuestion(question, "text");
    },
    [requestQuestion],
  );

  const synchronizeVoiceTurn = useCallback(async () => {
    const sessionId = learningSession?.chat_session_id ?? chatSessionId;
    if (!sessionId || !learningSession) return;
    const knownAnswerIds = new Set(answers.map((answer) => answer.id));
    const baselineLessonId = learningSession.current_lesson_id;
    for (let attempt = 0; attempt < 12; attempt += 1) {
      if (attempt > 0) {
        await new Promise((resolve) => setTimeout(resolve, 750));
      }
      try {
        const [recentAnswers, refreshedSession] = await Promise.all([
          api.listChatAnswers(sessionId),
          api.getLearningSession(learningSession.id),
        ]);
        setAnswers((current) => {
          const merged = new Map(current.map((answer) => [answer.id, answer]));
          recentAnswers.forEach((answer) => merged.set(answer.id, answer));
          return [...merged.values()];
        });
        setLearningSession(refreshedSession);
        if (
          recentAnswers.some((answer) => !knownAnswerIds.has(answer.id)) ||
          refreshedSession.current_lesson_id !== baselineLessonId
        ) {
          return;
        }
      } catch {
        // The sideband owns execution. A later poll or normal session restore
        // will reconcile transient API failures without replaying the utterance.
      }
    }
  }, [answers, chatSessionId, learningSession]);

  useEffect(() => {
    voiceQuestionHandler.current = () => {
      void synchronizeVoiceTurn();
    };
    return () => {
      voiceQuestionHandler.current = () => undefined;
    };
  }, [synchronizeVoiceTurn]);

  const stage = snapshot?.job?.stage ?? snapshot?.status ?? "pending";
  const stageIndex = Math.max(0, STAGES.indexOf(stage));
  const stageProgress = useMemo(() => {
    if (snapshot?.status === "ready") return 100;
    const job = snapshot?.job;
    if (job?.progress_total) {
      return Math.min(95, Math.round((job.progress_current / job.progress_total) * 100));
    }
    return Math.round((stageIndex / (STAGES.length - 1)) * 100);
  }, [snapshot, stageIndex]);
  const analysisStalled = snapshot?.job?.runtime_state === "stalled";
  const analysisFailed = snapshot?.status === "failed";
  const canRetryAnalysis = analysisStalled || analysisFailed;
  const isAnalyzing =
    snapshot &&
    !analysisStalled &&
    ["pending", "analyzing"].includes(snapshot.status);
  const stalledMessage =
    snapshot?.job?.stalled_reason === "worker_unavailable"
      ? "분석 worker가 응답하지 않습니다. 잠시 후 다시 시도해 주세요."
      : snapshot?.job?.stalled_reason === "analysis_deadline_exceeded"
        ? "분석 제한 시간을 초과했습니다. 새 작업으로 다시 시도할 수 있습니다."
        : "분석 진행이 멈췄습니다. 새 작업으로 다시 시도할 수 있습니다.";
  const failedMessage =
    "분석 작업이 중단되었습니다. 아래에서 새 작업으로 다시 시도할 수 있습니다.";

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark">
            <Waypoints aria-hidden size={19} />
          </span>
          <div>
            <strong>RepoWise AI</strong>
            <span>Repository navigation workspace</span>
          </div>
        </div>
        <div className="header-actions">
          <div className={`service-status ${health?.status === "ready" ? "is-ready" : ""}`}>
            {health?.status === "ready" ? (
              <Cloud aria-hidden size={14} />
            ) : (
              <CloudOff aria-hidden size={14} />
            )}
            <span>{health?.status === "ready" ? "API online" : "API unavailable"}</span>
          </div>
          <AuthUserMenu />
        </div>
      </header>

      <section className="repository-bar">
        <form onSubmit={submitRepository}>
          <div className="repo-input-wrap">
            <Waypoints aria-hidden size={17} />
            <input
              aria-label="GitHub repository URL"
              onChange={(event) => setRepositoryUrl(event.target.value)}
              placeholder="https://github.com/owner/repository"
              required
              type="url"
              value={repositoryUrl}
            />
          </div>
          <div className="branch-input-wrap">
            <GitBranch aria-hidden size={15} />
            <input
              aria-label="Git branch"
              onChange={(event) => setBranch(event.target.value)}
              placeholder="default branch"
              value={branch}
            />
          </div>
          <button
            className="analyze-button"
            disabled={submitting || Boolean(isAnalyzing)}
            type="submit"
          >
            {submitting || isAnalyzing ? (
              <LoaderCircle className="spin" aria-hidden size={16} />
            ) : (
              <Play aria-hidden fill="currentColor" size={16} />
            )}
            분석 시작
          </button>
        </form>

        {snapshot ? (
          <div className="analysis-progress" aria-live="polite">
            <div className="progress-copy">
              {reuseNotice ? <small>{reuseNotice}</small> : null}
              {snapshot.status === "ready" ? (
                <CheckCircle2 aria-hidden size={16} />
              ) : snapshot.status === "failed" ? (
                <TriangleAlert aria-hidden size={16} />
              ) : (
                <Activity aria-hidden size={16} />
              )}
              <span>
                {analysisStalled
                  ? "분석 정체"
                  : snapshot.status === "failed"
                  ? "분석 실패"
                  : (STAGE_LABELS[stage] ?? stage)}
              </span>
              {analysisStalled ? <small>{stalledMessage}</small> : null}
              {analysisFailed ? <small>{failedMessage}</small> : null}
              {canRetryAnalysis ? (
                <button
                  className="analysis-retry"
                  disabled={submitting}
                  onClick={() => void retryAnalysis()}
                  type="button"
                >
                  {submitting ? "재시도 중" : "분석 다시 시도"}
                </button>
              ) : null}
              {snapshot.status === "ready" ? (
                <small>
                  {snapshot.file_count} files · {snapshot.symbol_count} symbols ·{" "}
                  {snapshot.chunk_count} chunks
                  {snapshot.reuse_mode !== "full" ? (
                    <>
                      {" "}· 변경 {summaryMetric(snapshot.change_summary, "direct_changed_files")}
                      개 · parse 재사용 {summaryMetric(snapshot.change_summary, "parse_reused")}
                      개 · embedding 재사용 {summaryMetric(
                        snapshot.change_summary,
                        "embedding_reused",
                      )}
                      개
                    </>
                  ) : null}
                </small>
              ) : null}
            </div>
            <div className="progress-track" aria-label={`Analysis progress ${stageProgress}%`}>
              <span style={{ width: `${stageProgress}%` }} />
            </div>
          </div>
        ) : null}
      </section>

      {error || snapshot?.error_message || snapshot?.job?.error_detail ? (
        <div className="error-banner" role="alert">
          <TriangleAlert aria-hidden size={16} />
          <span>{error ?? snapshot?.error_message ?? snapshot?.job?.error_detail}</span>
        </div>
      ) : null}

      {snapshot?.status === "ready" ? (
        <nav aria-label="저장소 보기 방식" className="workspace-mode-switcher">
          <button
            aria-current={workspaceMode === "map" ? "page" : undefined}
            aria-pressed={workspaceMode === "map"}
            className={workspaceMode === "map" ? "is-active" : ""}
            onClick={showProjectMap}
            type="button"
          >
            <Waypoints aria-hidden size={14} /> Repository Structure
          </button>
          <button
            aria-current={workspaceMode === "explorer" ? "page" : undefined}
            aria-pressed={workspaceMode === "explorer"}
            className={workspaceMode === "explorer" ? "is-active" : ""}
            onClick={openExplorer}
            type="button"
          >
            <Braces aria-hidden size={14} /> 원본 코드 탐색
          </button>
          <button
            aria-current={workspaceMode === "change" ? "page" : undefined}
            aria-pressed={workspaceMode === "change"}
            className={workspaceMode === "change" ? "is-active" : ""}
            onClick={openChangeBrief}
            type="button"
          >
            <ShieldAlert aria-hidden size={14} /> 변경 영향
          </button>
          <button
            aria-current={workspaceMode === "learning" ? "page" : undefined}
            aria-pressed={workspaceMode === "learning"}
            className={workspaceMode === "learning" ? "is-active" : ""}
            onClick={startLearning}
            type="button"
          >
            <PanelRight aria-hidden size={14} /> 깊이 배우기
          </button>
        </nav>
      ) : null}

      {workspaceMode === "map" ? (
        <div className="map-workspace">
          <RepositoryStoryPage
            canEnhanceLabels={architectureLabelEnhancementEnabled}
            changeBrief={completedChangeBrief}
            comparisonSnapshots={snapshots.filter(
              (item) =>
                item.id !== snapshot?.id &&
                item.repository_id === snapshot?.repository_id &&
                item.status === "ready" &&
                item.parser_version === "semantic-ts-v2",
            )}
            diff={architectureGraphDiff}
            diffLoading={architectureDiffLoading}
            enhancingLabels={architectureLabelsLoading}
            error={architectureGraphError}
            flow={featureFlowDetail}
            loading={architectureGraphLoading || Boolean(isAnalyzing)}
            onCompareSnapshot={(snapshotId) => void compareArchitectureSnapshot(snapshotId)}
            onEnhanceLabels={() => void enhanceArchitectureLabels()}
            onOpenDependencyGraph={openExplorer}
            onOpenEvidence={openMapEvidence}
            onRequestChangeBrief={requestArchitectureChangeBrief}
            onSelectFlow={(flowId) => {
              featureFlowDetailRequestSequence.current += 1;
              setSelectedFeatureFlowId(flowId);
              setFeatureFlowDetail(null);
              loadedFeatureFlowDetail.current = null;
            }}
            onStartLearning={startLearning}
            selectedFlowId={selectedFeatureFlowId}
            story={
              repositoryStory && architectureGraph
                ? { ...repositoryStory, implementation_graph: architectureGraph }
                : repositoryStory
            }
          />
        </div>
      ) : workspaceMode === "flow" ? (
        <FeatureFlowPanel
          catalog={featureFlowCatalog}
          detailLoading={featureFlowDetailLoading}
          error={featureFlowError}
          flow={featureFlowDetail}
          loading={featureFlowLoading}
          onBackToCatalog={showFeatureFlowCatalog}
          onBackToMap={showProjectMap}
          onOpenEvidence={openFeatureFlowEvidence}
          onRetry={retryFeatureFlow}
          onSelectFlow={(flowId) => openFeatureFlows(flowId)}
          onStartLearning={startLearning}
        />
      ) : (
        <>

      <div className="mobile-pane-tabs" aria-label="Workspace panes">
        <button
          className={mobilePane === "tree" ? "is-active" : ""}
          onClick={() => setMobilePane("tree")}
          type="button"
        >
          <FolderTree aria-hidden size={15} /> 파일
        </button>
        <button
          className={mobilePane === "code" ? "is-active" : ""}
          onClick={() => setMobilePane("code")}
          type="button"
        >
          <Braces aria-hidden size={15} /> 코드
        </button>
        <button
          className={mobilePane === "guide" ? "is-active" : ""}
          onClick={() => setMobilePane("guide")}
          type="button"
        >
          <PanelRight aria-hidden size={15} />
          {workspaceMode === "learning"
            ? "학습"
            : workspaceMode === "change"
              ? "영향"
            : codeExplanation || codeFocusLoading || selection
              ? "설명"
              : "개요"}
        </button>
      </div>

      <section className="workspace-grid">
        <aside className={`tree-panel mobile-${mobilePane === "tree" ? "visible" : "hidden"}`}>
          <div className="panel-toolbar">
            <FolderTree aria-hidden size={16} />
            <strong>Files</strong>
            <span>{snapshot?.file_count ?? 0}</span>
          </div>
          {tree.length ? (
            <FileTree
              key={snapshot?.id}
              nodes={tree}
              onSelectFile={openFile}
              selectedFileId={file?.id ?? null}
            />
          ) : (
            <div className="panel-empty compact-empty">
              <span>
                {explorerLoading
                  ? "원본 파일 구조를 불러오는 중입니다."
                  : "파일을 선택해 원본 코드를 확인하세요."}
              </span>
            </div>
          )}
        </aside>

        <div className={`center-panel mobile-${mobilePane === "code" ? "visible" : "hidden"}`}>
          <CodePanel
            file={file}
            graph={graph}
            highlight={highlight}
            loading={fileLoading || explorerLoading}
            onOpenFile={openFile}
            onSelectionChange={handleSelectionChange}
            onViewChange={setView}
            symbols={symbols}
            view={view}
          />
        </div>

        <div className={`right-panel mobile-${mobilePane === "guide" ? "visible" : "hidden"}`}>
          {workspaceMode === "learning" ? (
            <AssistantPanel
            activity={
              learningActivity?.step_id === learningSession?.current_step_id
                ? learningActivity
                : null
            }
            activityAttempt={
              learningActivity?.step_id === learningSession?.current_step_id
                ? activityAttempt
                : null
            }
            activityBusy={
              activityBusy ||
              Boolean(
                learningSession?.current_step_id &&
                  learningActivity?.step_id !== learningSession.current_step_id,
              )
            }
            answers={answers}
            asking={asking}
            deepTask={activeDeepTask}
            deepTaskError={deepTaskError}
            deepTaskStarting={isDeepTaskStarting}
            deepTaskCancelling={isDeepTaskCancelling}
            assessment={assessment}
            assessmentBusy={assessmentBusy}
            file={file}
            journeyBusy={journeyBusy}
            learningPath={learningPath}
            learningSession={learningSession}
            masteryLoading={
              masteryLoading || Boolean(masteryProfileId && !masteryOverview)
            }
            masteryOverview={masteryOverview}
            onAsk={askQuestion}
            onAssessmentAnswer={answerAssessment}
            onAssessmentSkip={skipAssessment}
            onAssessmentSubmit={submitAssessment}
            onCompleteHelp={completeHelp}
            onDismissDeepTask={resetDeepTask}
            onCancelDeepTask={() => void cancelDeepTask()}
            onHelp={openHelp}
            onLearningFeedback={updateLearningProgress}
            onOpenEvidence={openEvidence}
            onOpenFile={openFile}
            onOpenLesson={openLearningLesson}
            onOpenLines={openLines}
            onApplyRoadmap={applyRoadmapProposal}
            onRejectRoadmap={rejectRoadmapProposal}
            onReplan={replanJourney}
            onSubmitActivity={submitActivity}
            onTeachingStyleChange={setTeachingStyle}
            remediation={remediation}
            roadmapProposal={roadmapProposal}
            selection={selection}
            snapshot={snapshot}
            startHere={startHere}
            teachingStyle={teachingStyle}
            voiceSession={voiceSession}
            />
          ) : workspaceMode === "change" ? (
            <ChangeBriefPanel
              cancelling={isChangeBriefCancelling}
              error={changeBriefError}
              onCancel={() => void cancelChangeBrief()}
              onOpenEvidence={openChangeBriefEvidence}
              onReset={resetChangeBrief}
              onStart={(prompt) => void requestChangeBrief(prompt)}
              selection={selection}
              starting={isChangeBriefStarting}
              task={activeChangeBriefTask}
            />
          ) : codeExplanation || codeFocusLoading || codeFocusError || selection ? (
            <CodeFocusPanel
              error={codeFocusError}
              explanation={codeExplanation}
              loading={codeFocusLoading}
              onExplain={explainCurrentSelection}
              onOpenEvidence={openCodeFocusEvidence}
              onRequestChangeBrief={openChangeBrief}
              selection={selection}
            />
          ) : (
            <StartHerePanel
              onOpenFile={openFile}
              snapshot={snapshot}
              startHere={startHere}
            />
          )}
        </div>
      </section>
        </>
      )}
    </main>
  );
}

function answerForVoice(answer: ChatAnswer) {
  if (answer.voice_summary?.trim()) return answer.voice_summary.trim();
  const compact = answer.answer
    .replace(/`[^`]*`/g, "코드")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (compact.length <= 600) return compact;
  return `${compact.slice(0, 520)}. 자세한 내용과 코드 근거는 화면에서 확인해 주세요.`;
}

function findCurrentLesson(path: LearningPath, session: LearningSession) {
  for (const learningModule of path.modules) {
    const lesson = learningModule.lessons.find(
      (item) => item.id === session.current_lesson_id,
    );
    if (lesson) return { learningModule, lesson };
  }
  return null;
}

function styleForProfile(profile: LearnerProfile): TeachingStyle {
  if (profile.preferred_explanation.includes("line_by_line") || profile.pace === "careful") {
    return "beginner";
  }
  if (profile.pace === "fast") return "advanced";
  return "standard";
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "요청을 처리하지 못했습니다.";
}
