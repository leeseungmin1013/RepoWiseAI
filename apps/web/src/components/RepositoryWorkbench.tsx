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
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  type ActivityAttemptSummary,
  type AssessmentSession,
  type ChatAnswer,
  type Citation,
  type CodeSelection,
  type DeepTask,
  type DeepTaskRequest,
  type GraphData,
  type Health,
  type LearnerProfile,
  type LearningActivity,
  type LearningFeedbackType,
  type LearningLesson,
  type LearningModule,
  type LearningPath,
  type LearningSession,
  type MasteryOverview,
  type RemediationBranch,
  type RemediationMode,
  type Snapshot,
  type SourceFile,
  type StartHere,
  type SymbolRecord,
  type TeachingStyle,
  type TreeNode,
} from "@/lib/api";
import { findFirstFile } from "@/lib/tree";
import { useRealtimeLearningSession } from "@/hooks/useRealtimeLearningSession";
import { useDeepLearningTask } from "@/hooks/useDeepLearningTask";
import { routeQuestionToDeepTask } from "@/lib/deep-tasks";

import { AssistantPanel } from "./AssistantPanel";
import { CodePanel, type CodeHighlight } from "./CodePanel";
import { FileTree } from "./FileTree";

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
  guidance: "학습 근거 구성",
  ready: "분석 완료",
};

type MobilePane = "tree" | "code" | "guide";

export function RepositoryWorkbench() {
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [assessment, setAssessment] = useState<AssessmentSession | null>(null);
  const [assessmentBusy, setAssessmentBusy] = useState(false);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [file, setFile] = useState<SourceFile | null>(null);
  const [symbols, setSymbols] = useState<SymbolRecord[]>([]);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [startHere, setStartHere] = useState<StartHere | null>(null);
  const [learningPath, setLearningPath] = useState<LearningPath | null>(null);
  const [learningSession, setLearningSession] = useState<LearningSession | null>(null);
  const [learningActivity, setLearningActivity] = useState<LearningActivity | null>(null);
  const [activityAttempt, setActivityAttempt] = useState<ActivityAttemptSummary | null>(null);
  const [activityBusy, setActivityBusy] = useState(false);
  const [masteryOverview, setMasteryOverview] = useState<MasteryOverview | null>(null);
  const [masteryLoading, setMasteryLoading] = useState(false);
  const [remediation, setRemediation] = useState<RemediationBranch | null>(null);
  const [journeyBusy, setJourneyBusy] = useState(false);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [sessionTeachingStyle, setSessionTeachingStyle] = useState<TeachingStyle | null>(null);
  const [teachingStyle, setTeachingStyle] = useState<TeachingStyle>("beginner");
  const [answers, setAnswers] = useState<ChatAnswer[]>([]);
  const [asking, setAsking] = useState(false);
  const [selection, setSelection] = useState<CodeSelection | null>(null);
  const [highlight, setHighlight] = useState<CodeHighlight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [view, setView] = useState<"code" | "graph">("code");
  const [mobilePane, setMobilePane] = useState<MobilePane>("code");
  const loadedSnapshot = useRef<string | null>(null);
  const assessmentRequest = useRef<string | null>(null);
  const voiceQuestionHandler = useRef<(transcript: string) => void>(() => undefined);
  const voiceLearningSessionId = useRef<string | null>(null);
  const deepLearningSessionId = useRef<string | null>(null);
  const activeAssessmentId =
    assessment?.status === "active" ? assessment.id : null;
  const masteryProfileId =
    assessment && assessment.status !== "active" ? profile?.id ?? null : null;
  const exchangeVoiceSdp = useCallback(
    (sdp: string, signal: AbortSignal) => {
      if (!learningSession) {
        return Promise.reject(new Error("먼저 학습 세션을 시작해 주세요."));
      }
      return api.exchangeVoiceOffer(learningSession.id, sdp, signal);
    },
    [learningSession],
  );
  const handleFinalVoiceTranscript = useCallback((transcript: string) => {
    voiceQuestionHandler.current(transcript);
  }, []);
  const voiceSession = useRealtimeLearningSession({
    exchangeSdp: exchangeVoiceSdp,
    onFinalTranscript: handleFinalVoiceTranscript,
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
      if ("id" in answer) {
        setAnswers((current) =>
          current.some((item) => item.id === answer.id)
            ? current
            : [...current, answer],
        );
      }
      if (request?.modality === "voice") {
        speakVerifiedText(
          "id" in answer
            ? answerForVoice(answer)
            : answer.voice_summary || answer.answer,
        );
      }
    },
    [speakVerifiedText],
  );
  const deepLearningTask = useDeepLearningTask({
    onCompleted: handleDeepTaskCompleted,
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

  useEffect(() => {
    if (!snapshot || !["pending", "analyzing"].includes(snapshot.status)) return;
    const snapshotId = snapshot.id;
    const interval = window.setInterval(() => {
      api
        .getSnapshot(snapshotId)
        .then(setSnapshot)
        .catch((reason: unknown) => setError(errorMessage(reason)));
    }, 1_200);
    return () => window.clearInterval(interval);
  }, [snapshot]);

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
    if (!snapshot || !profile || assessment?.snapshot_id === snapshot.id) return;
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
  }, [assessment, profile, snapshot]);

  useEffect(() => {
    const assessmentFinished = assessment && assessment.status !== "active";
    if (
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

    Promise.all([
      api.getTree(snapshotId),
      api.getStartHere(snapshotId),
      api.getGraph(snapshotId),
      api.createLearningPath(snapshotId, profile.id),
    ])
      .then(async ([nextTree, nextStartHere, nextGraph, nextPath]) => {
        const nextSession = await api.createLearningSession(nextPath.id, style);
        setTree(nextTree);
        setStartHere(nextStartHere);
        setGraph(nextGraph);
        setLearningPath(nextPath);
        setLearningSession(nextSession);
        setChatSessionId(nextSession.chat_session_id);
        setSessionTeachingStyle(style);

        const current = findCurrentLesson(nextPath, nextSession);
        const evidence = current?.lesson.steps[0]?.evidence;
        const firstEntry = nextStartHere.entry_points[0]?.file_id;
        const firstFile = findFirstFile(nextTree)?.file_id;
        const fileId = evidence?.file_id ?? firstEntry ?? firstFile;
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
  }, [assessment, profile, snapshot]);

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
      setSnapshot(response.snapshot);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  function resetRepositoryState() {
    resetDeepTask();
    setAssessment(null);
    setTree([]);
    setFile(null);
    setSymbols([]);
    setGraph(null);
    setStartHere(null);
    setLearningPath(null);
    setLearningSession(null);
    setLearningActivity(null);
    setActivityAttempt(null);
    setActivityBusy(false);
    setMasteryOverview(null);
    setMasteryLoading(false);
    setRemediation(null);
    setJourneyBusy(false);
    setChatSessionId(null);
    setSessionTeachingStyle(null);
    setAnswers([]);
    setSelection(null);
    setHighlight(null);
    loadedSnapshot.current = null;
    assessmentRequest.current = null;
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
    setFileLoading(true);
    setError(null);
    setSelection(null);
    try {
      const [nextFile, nextSymbols] = await Promise.all([
        api.getFile(snapshot.id, fileId),
        api.getSymbols(snapshot.id, fileId),
      ]);
      setFile(nextFile);
      setSymbols(nextSymbols);
      setHighlight(nextHighlight);
      setView("code");
      setMobilePane("code");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setFileLoading(false);
    }
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
      const result = await api.replanLearningSession(learningSession.id);
      setLearningPath(result.path);
      setLearningSession(result.session);
      setRemediation(null);
      const current = findCurrentLesson(result.path, result.session);
      const evidence = current?.lesson.steps[0]?.evidence;
      if (evidence) openEvidence(evidence);
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

  const handleSelectionChange = useCallback((nextSelection: CodeSelection | null) => {
    setSelection(nextSelection);
  }, []);

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

  const askVoiceQuestion = useCallback(
    async (question: string) => {
      const answer = await requestQuestion(question, "voice");
      if (answer) {
        speakVerifiedText(answerForVoice(answer));
      }
    },
    [requestQuestion, speakVerifiedText],
  );

  useEffect(() => {
    voiceQuestionHandler.current = (transcript) => {
      void askVoiceQuestion(transcript);
    };
    return () => {
      voiceQuestionHandler.current = () => undefined;
    };
  }, [askVoiceQuestion]);

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
  const isAnalyzing = snapshot && ["pending", "analyzing"].includes(snapshot.status);

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark">
            <Waypoints aria-hidden size={19} />
          </span>
          <div>
            <strong>RepoWise AI</strong>
            <span>Codebase learning workspace</span>
          </div>
        </div>
        <div className={`service-status ${health?.status === "ready" ? "is-ready" : ""}`}>
          {health?.status === "ready" ? (
            <Cloud aria-hidden size={14} />
          ) : (
            <CloudOff aria-hidden size={14} />
          )}
          <span>{health?.status === "ready" ? "API online" : "API unavailable"}</span>
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
              {snapshot.status === "ready" ? (
                <CheckCircle2 aria-hidden size={16} />
              ) : snapshot.status === "failed" ? (
                <TriangleAlert aria-hidden size={16} />
              ) : (
                <Activity aria-hidden size={16} />
              )}
              <span>
                {snapshot.status === "failed"
                  ? "분석 실패"
                  : (STAGE_LABELS[stage] ?? stage)}
              </span>
              {snapshot.status === "ready" ? (
                <small>
                  {snapshot.file_count} files · {snapshot.symbol_count} symbols ·{" "}
                  {snapshot.chunk_count} chunks
                </small>
              ) : null}
            </div>
            <div className="progress-track" aria-label={`Analysis progress ${stageProgress}%`}>
              <span style={{ width: `${stageProgress}%` }} />
            </div>
          </div>
        ) : null}
      </section>

      {error || snapshot?.error_message ? (
        <div className="error-banner" role="alert">
          <TriangleAlert aria-hidden size={16} />
          <span>{error ?? snapshot?.error_message}</span>
        </div>
      ) : null}

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
          <PanelRight aria-hidden size={15} /> 학습
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
              <span>{isAnalyzing ? "파일 구조를 분석 중입니다." : "분석할 저장소를 입력하세요."}</span>
            </div>
          )}
        </aside>

        <div className={`center-panel mobile-${mobilePane === "code" ? "visible" : "hidden"}`}>
          <CodePanel
            file={file}
            graph={graph}
            highlight={highlight}
            loading={fileLoading}
            onOpenFile={openFile}
            onSelectionChange={handleSelectionChange}
            onViewChange={setView}
            symbols={symbols}
            view={view}
          />
        </div>

        <div className={`right-panel mobile-${mobilePane === "guide" ? "visible" : "hidden"}`}>
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
            onReplan={replanJourney}
            onSubmitActivity={submitActivity}
            onTeachingStyleChange={setTeachingStyle}
            remediation={remediation}
            selection={selection}
            snapshot={snapshot}
            startHere={startHere}
            teachingStyle={teachingStyle}
            voiceSession={voiceSession}
          />
        </div>
      </section>
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
