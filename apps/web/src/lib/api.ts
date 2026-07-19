const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export type AnalysisJob = {
  id: string;
  snapshot_id: string;
  stage: string;
  status: string;
  progress_current: number;
  progress_total: number;
  error_code: string | null;
  error_detail: string | null;
};

export type Snapshot = {
  id: string;
  repository_id: string;
  branch: string | null;
  commit_sha: string | null;
  status: "pending" | "analyzing" | "ready" | "failed";
  parser_version: string;
  index_version: string;
  file_count: number;
  symbol_count: number;
  edge_count: number;
  chunk_count: number;
  total_bytes: number;
  embedding_model: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  job: AnalysisJob | null;
};

export type Repository = {
  id: string;
  provider: string;
  owner: string;
  name: string;
  url: string;
  created_at: string;
};

export type CreateRepositoryResponse = {
  repository: Repository;
  snapshot: Snapshot;
};

export type TreeNode = {
  id: string;
  name: string;
  path: string;
  type: "directory" | "file";
  file_id: string | null;
  language: string | null;
  children: TreeNode[];
};

export type SourceFile = {
  id: string;
  snapshot_id: string;
  path: string;
  language: string;
  content: string;
  content_hash: string;
  byte_size: number;
  line_count: number;
};

export type SymbolRecord = {
  id: string;
  file_id: string;
  qualified_name: string;
  display_name: string;
  kind: string;
  signature: string | null;
  start_line: number;
  end_line: number;
};

export type GraphData = {
  nodes: Array<{
    id: string;
    label: string;
    kind: string;
    file_id: string | null;
    path: string | null;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    relation: string;
    confidence: number;
  }>;
};

export type StartHere = {
  repository_name: string;
  snapshot_id: string;
  commit_sha: string;
  summary: string;
  tech_stack: string[];
  entry_points: Array<{
    file_id: string;
    path: string;
    reason: string;
  }>;
  top_directories: string[];
  suggested_goals: string[];
};

export type Health = {
  status: "ready" | "degraded";
  version: string;
  checks: Record<string, string>;
};

export type CodeSelection = {
  file_id: string;
  start_line: number;
  end_line: number;
};

export type Citation = {
  evidence_id: string;
  source_type: "repository_code";
  snapshot_id: string;
  file_id: string;
  path: string;
  language: string;
  title: string;
  chunk_type: "file" | "symbol" | "block";
  start_line: number;
  end_line: number;
  preview: string;
  score: number;
  retrievers: string[];
};

export type ChatSession = {
  id: string;
  snapshot_id: string;
  goal: string | null;
  preferred_style: string;
  learning_session_id: string | null;
  created_at: string;
  updated_at: string;
};

export type TeachingStyle = "beginner" | "standard" | "advanced";

export type ChatAnswer = {
  id: string;
  session_id: string;
  question: string;
  answer: string;
  status: "grounded" | "insufficient_evidence";
  intent: "location" | "flow" | "impact" | "concept" | "explain";
  retrieval_run_id: string;
  citations: Citation[];
  follow_up: string | null;
  voice_summary: string | null;
  generation_mode: "openai" | "retrieval_only";
  model_name: string | null;
  created_at: string;
};

export type DeepTaskKind =
  | "deep_explanation"
  | "impact_analysis"
  | "roadmap_proposal"
  | "research_materials";

export type DeepTaskStatus =
  | "queued"
  | "running"
  | "retrieving"
  | "reasoning"
  | "verifying"
  | "completed"
  | "failed"
  | "cancelled";

export type DeepTaskRequest = {
  kind: DeepTaskKind;
  prompt: string;
  selection?: CodeSelection | null;
  modality: "text" | "voice";
};

export type DeepTaskError = {
  code: string;
  message: string;
};

export type ResearchSource = {
  title: string;
  publisher: string;
  url: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  estimated_minutes: number;
  recommendation_reason: string;
  checked_at: string;
};

export type ResearchMaterials = {
  answer: string;
  voice_summary: string | null;
  sources: ResearchSource[];
  generation_mode: "openai_web_search";
  model_name: string;
};

export type DeepTaskResult = ChatAnswer | ResearchMaterials;

export type DeepTask = {
  id: string;
  status: DeepTaskStatus;
  kind: DeepTaskKind;
  progress: number;
  message: string;
  result?: DeepTaskResult | null;
  error?: DeepTaskError | null;
};

export type GuidedStep = {
  id: string;
  ordinal: number;
  step_type: "orientation" | "core_flow" | "supporting_flow" | "error_path" | "test";
  title: string;
  learning_objective: string;
  summary: string;
  concept_ids: string[];
  checkpoint: { type?: string; prompt?: string };
  estimated_minutes: number;
  evidence: Citation;
};

export type GuidedPath = {
  id: string;
  snapshot_id: string;
  title: string;
  goal: string;
  difficulty: string;
  path_version: string;
  generation_method: string;
  total_minutes: number;
  steps: GuidedStep[];
  created_at: string;
  updated_at: string;
};

export type GuidedTourSession = {
  id: string;
  path_id: string;
  preferred_style: TeachingStyle;
  status: "active" | "completed";
  current_step_ordinal: number;
  completed_step_ids: string[];
  needs_help_step_ids: string[];
  completed_count: number;
  total_steps: number;
  created_at: string;
  updated_at: string;
};

export type GuidedFeedbackType = "opened" | "understood" | "needs_help";

export type LearnerProfile = {
  id: string;
  anonymous_key: string;
  goal: string;
  preferred_explanation: string[];
  pace: string;
  background: Record<string, unknown>;
  concept_mastery: Record<
    string,
    { score?: number; confidence?: number; source?: string }
  >;
  assessment_version: string;
  created_at: string;
  updated_at: string;
};

export type AssessmentQuestion = {
  id: string;
  category: string;
  prompt: string;
  choices: Array<{ value: string; label: string }>;
  concept_id: string | null;
  stack_requirement: string | null;
};

export type AssessmentSession = {
  id: string;
  snapshot_id: string;
  learner_profile_id: string;
  status: "active" | "completed" | "skipped";
  detected_stack: string[];
  assessment_version: string;
  questions: AssessmentQuestion[];
  answers: Record<string, string>;
  answered_count: number;
  total_count: number;
  created_at: string;
  submitted_at: string | null;
  skipped_at: string | null;
  profile: LearnerProfile;
};

export type LearningStep = {
  id: string;
  ordinal: number;
  step_type: string;
  title: string;
  instruction: string;
  concept_id: string | null;
  evidence: Citation | null;
  metadata: Record<string, unknown>;
};

export type LearningLesson = {
  id: string;
  ordinal: number;
  lesson_type: string;
  title: string;
  objective: string;
  required_concept_ids: string[];
  checkpoint: { type?: string; prompt?: string };
  estimated_minutes: number;
  optional: boolean;
  steps: LearningStep[];
};

export type LearningModule = {
  id: string;
  ordinal: number;
  module_type: string;
  title: string;
  objective: string;
  required: boolean;
  estimated_minutes: number;
  coverage_keys: string[];
  lessons: LearningLesson[];
};

export type LearningPath = {
  id: string;
  snapshot_id: string;
  learner_profile_id: string;
  title: string;
  goal: string;
  status: string;
  path_version: string;
  generation_method: string;
  coverage: Record<string, string>;
  model_metadata: Record<string, unknown>;
  estimated_minutes: number;
  total_modules: number;
  total_lessons: number;
  modules: LearningModule[];
  created_at: string;
  updated_at: string;
};

export type LearningSession = {
  id: string;
  snapshot_id: string;
  learner_profile_id: string;
  path_id: string;
  chat_session_id: string;
  current_module_id: string | null;
  current_lesson_id: string | null;
  current_step_id: string | null;
  completed_lesson_ids: string[];
  return_stack: Array<Record<string, unknown>>;
  current_selection: Partial<CodeSelection>;
  focus_concept_ids: string[];
  status: "active" | "completed";
  completed_count: number;
  total_lessons: number;
  created_at: string;
  updated_at: string;
};

export type LearningReplanResult = {
  path: LearningPath;
  session: LearningSession;
  preserved_lesson_ids: string[];
  added_lesson_count: number;
  revision: number;
};

export type LearningFeedbackType = "opened" | "understood" | "needs_help" | "skip";
export type RemediationMode =
  | "line_by_line"
  | "prerequisite"
  | "small_example"
  | "learning_sources";

export type ExplanationSegment = {
  segment_id: string;
  start_line: number;
  end_line: number;
  source: string;
  what: string;
  why: string;
  syntax_concepts: string[];
  evidence_id: string;
};

export type LineExplanation = {
  artifact_id: string;
  step_id: string;
  file_id: string;
  path: string;
  segments: ExplanationSegment[];
  generation_mode: string;
};

export type LearningSource = {
  id: string;
  concept_id: string;
  title: string;
  publisher: string;
  canonical_url: string;
  source_tier: string;
  difficulty: string;
  language: string;
  estimated_minutes: number;
  recommendation_reason?: string;
};

export type RemediationBranch = {
  id: string;
  learning_session_id: string;
  source_lesson_id: string;
  source_step_id: string | null;
  mode: RemediationMode;
  status: "active" | "completed";
  concept_ids: string[];
  content: {
    type?: RemediationMode;
    path?: string;
    file_id?: string;
    generation_mode?: string;
    segments?: ExplanationSegment[];
    concepts?: Array<{
      concept_id: string;
      title: string;
      definition: string;
      check_question: string;
    }>;
    gap_resolution?: Array<{
      concept_id: string;
      display_name: string;
      required_for: string;
      depth: number;
      score: number;
      confidence: number;
      rationale: string;
      relation_confidence: number;
    }>;
    examples?: Array<{ concept_id: string; code: string }>;
    sources?: LearningSource[];
  };
  return_lesson_id: string;
  return_step_id: string | null;
  created_at: string;
  completed_at: string | null;
};

export type ActivityAttemptSummary = {
  id: string;
  selected_choice_id: string;
  is_correct: boolean;
  score_delta: number;
  feedback: {
    message?: string;
    explanation?: string;
    selected_label?: string;
    correct_label?: string;
  };
  created_at: string;
};

export type LearningActivity = {
  id: string;
  step_id: string;
  activity_type: string;
  prompt: string;
  choices: Array<{ id: string; label: string }>;
  concept_ids: string[];
  evidence: Citation;
  generator_version: string;
  latest_attempt: ActivityAttemptSummary | null;
};

export type MasteryUpdate = {
  concept_id: string;
  previous_score: number;
  new_score: number;
  previous_confidence: number;
  new_confidence: number;
};

export type ActivityAttempt = ActivityAttemptSummary & {
  activity_id: string;
  learning_session_id: string;
  correct_choice_id: string;
  evidence: Citation;
  mastery_updates: MasteryUpdate[];
};

export type MasteryEvent = {
  id: string;
  learner_profile_id: string;
  learning_session_id: string | null;
  concept_id: string;
  event_type: string;
  source_type: string;
  source_id: string | null;
  previous_score: number;
  new_score: number;
  previous_confidence: number;
  new_confidence: number;
  evidence: Record<string, unknown>;
  policy_version: string;
  created_at: string;
};

export type ConceptMasteryState = {
  concept_id: string;
  display_name: string;
  description: string;
  domain: string;
  difficulty: string;
  score: number;
  confidence: number;
  state: "unknown" | "needs_review" | "developing" | "ready";
  source: string | null;
  prerequisite_ids: string[];
  event_count: number;
  last_event_at: string | null;
};

export type MasteryOverview = {
  profile_id: string;
  graph_version: string;
  summary: {
    ready: number;
    developing: number;
    needs_review: number;
    unknown: number;
    total: number;
  };
  concepts: ConceptMasteryState[];
  recent_events: MasteryEvent[];
};

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // Preserve the HTTP fallback when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

async function requestText(path: string, init?: RequestInit): Promise<string> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // Preserve the HTTP fallback when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return response.text();
}

export const api = {
  health: () => request<Health>("/health"),
  createRepository: (url: string, branch?: string) =>
    request<CreateRepositoryResponse>("/repositories", {
      method: "POST",
      body: JSON.stringify({ url, branch: branch || null }),
    }),
  listSnapshots: () => request<Snapshot[]>("/snapshots?limit=10"),
  getSnapshot: (snapshotId: string) => request<Snapshot>(`/snapshots/${snapshotId}`),
  getTree: (snapshotId: string) => request<TreeNode[]>(`/snapshots/${snapshotId}/tree`),
  getFile: (snapshotId: string, fileId: string) =>
    request<SourceFile>(`/snapshots/${snapshotId}/files/${fileId}`),
  getSymbols: (snapshotId: string, fileId: string) =>
    request<SymbolRecord[]>(
      `/snapshots/${snapshotId}/symbols?file_id=${encodeURIComponent(fileId)}`,
    ),
  getGraph: (snapshotId: string) => request<GraphData>(`/snapshots/${snapshotId}/graph`),
  getStartHere: (snapshotId: string) =>
    request<StartHere>(`/snapshots/${snapshotId}/start-here`),
  createLearnerProfile: (anonymousKey: string) =>
    request<LearnerProfile>("/learner-profiles", {
      method: "POST",
      body: JSON.stringify({ anonymous_key: anonymousKey }),
    }),
  createAssessmentSession: (snapshotId: string, learnerProfileId: string) =>
    request<AssessmentSession>(`/snapshots/${snapshotId}/assessment-sessions`, {
      method: "POST",
      body: JSON.stringify({ learner_profile_id: learnerProfileId }),
    }),
  getAssessmentSession: (assessmentId: string) =>
    request<AssessmentSession>(`/assessment-sessions/${assessmentId}`),
  answerAssessment: (assessmentId: string, itemId: string, answer: string) =>
    request<AssessmentSession>(`/assessment-sessions/${assessmentId}/responses`, {
      method: "POST",
      body: JSON.stringify({ item_id: itemId, answer }),
    }),
  submitAssessment: (assessmentId: string) =>
    request<AssessmentSession>(`/assessment-sessions/${assessmentId}/submit`, {
      method: "POST",
    }),
  skipAssessment: (assessmentId: string) =>
    request<AssessmentSession>(`/assessment-sessions/${assessmentId}/skip`, {
      method: "POST",
    }),
  createLearningPath: (snapshotId: string, learnerProfileId: string) =>
    request<LearningPath>(`/snapshots/${snapshotId}/learning-paths`, {
      method: "POST",
      body: JSON.stringify({ learner_profile_id: learnerProfileId }),
    }),
  getLearningPath: (pathId: string) =>
    request<LearningPath>(`/learning-paths/${pathId}`),
  createLearningSession: (pathId: string, preferredStyle: TeachingStyle) =>
    request<LearningSession>(`/learning-paths/${pathId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ preferred_style: preferredStyle }),
    }),
  getLearningSession: (sessionId: string) =>
    request<LearningSession>(`/learning-sessions/${sessionId}`),
  exchangeVoiceOffer: (sessionId: string, sdp: string, signal?: AbortSignal) =>
    requestText(`/learning-sessions/${sessionId}/voice/offer`, {
      method: "POST",
      body: sdp,
      headers: { "Content-Type": "application/sdp" },
      signal,
    }),
  replanLearningSession: (sessionId: string) =>
    request<LearningReplanResult>(`/learning-sessions/${sessionId}/replan`, {
      method: "POST",
    }),
  recordLearningFeedback: (
    sessionId: string,
    lessonId: string,
    eventType: LearningFeedbackType,
  ) =>
    request<LearningSession>(
      `/learning-sessions/${sessionId}/lessons/${lessonId}/feedback`,
      {
        method: "POST",
        body: JSON.stringify({ event_type: eventType }),
      },
    ),
  createLearningActivity: (sessionId: string, stepId: string) =>
    request<LearningActivity>(
      `/learning-sessions/${sessionId}/steps/${stepId}/activity`,
      { method: "POST" },
    ),
  submitActivityAttempt: (
    sessionId: string,
    activityId: string,
    selectedChoiceId: string,
  ) =>
    request<ActivityAttempt>(
      `/learning-sessions/${sessionId}/activities/${activityId}/attempts`,
      {
        method: "POST",
        body: JSON.stringify({ selected_choice_id: selectedChoiceId }),
      },
    ),
  getMasteryEvents: (learnerProfileId: string, limit = 50) =>
    request<MasteryEvent[]>(
      `/learner-profiles/${learnerProfileId}/mastery-events?limit=${limit}`,
    ),
  getMasteryOverview: (learnerProfileId: string) =>
    request<MasteryOverview>(
      `/learner-profiles/${learnerProfileId}/mastery-overview`,
    ),
  updateLearningSelection: (sessionId: string, selection: CodeSelection) =>
    request<LearningSession>(`/learning-sessions/${sessionId}/selection`, {
      method: "PATCH",
      body: JSON.stringify({ selection }),
    }),
  getLineExplanation: (stepId: string, depth: TeachingStyle) =>
    request<LineExplanation>(
      `/learning-steps/${stepId}/explanations?depth=${encodeURIComponent(depth)}`,
    ),
  getLearningSources: (stepId: string, learnerProfileId: string) =>
    request<LearningSource[]>(
      `/learning-steps/${stepId}/sources?learner_profile_id=${encodeURIComponent(learnerProfileId)}`,
    ),
  createRemediation: (
    sessionId: string,
    lessonId: string,
    stepId: string | null,
    mode: RemediationMode,
  ) =>
    request<RemediationBranch>(`/learning-sessions/${sessionId}/remediation`, {
      method: "POST",
      body: JSON.stringify({ mode, lesson_id: lessonId, step_id: stepId }),
    }),
  completeRemediation: (branchId: string) =>
    request<RemediationBranch>(`/remediation-branches/${branchId}/complete`, {
      method: "POST",
    }),
  getGuidedPath: (snapshotId: string) =>
    request<GuidedPath>(`/snapshots/${snapshotId}/guided-path`),
  createGuidedTourSession: (pathId: string, preferredStyle: TeachingStyle) =>
    request<GuidedTourSession>(`/guided-paths/${pathId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ preferred_style: preferredStyle }),
    }),
  getGuidedTourSession: (sessionId: string) =>
    request<GuidedTourSession>(`/guided-tour-sessions/${sessionId}`),
  recordGuidedFeedback: (
    sessionId: string,
    stepId: string,
    eventType: GuidedFeedbackType,
  ) =>
    request<GuidedTourSession>(
      `/guided-tour-sessions/${sessionId}/steps/${stepId}/feedback`,
      {
        method: "POST",
        body: JSON.stringify({ event_type: eventType, payload: {} }),
      },
    ),
  createChatSession: (snapshotId: string, preferredStyle: TeachingStyle) =>
    request<ChatSession>("/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ snapshot_id: snapshotId, preferred_style: preferredStyle }),
    }),
  updateChatSession: (sessionId: string, preferredStyle: TeachingStyle) =>
    request<ChatSession>(`/chat/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ preferred_style: preferredStyle }),
    }),
  ask: (
    sessionId: string,
    content: string,
    selection?: CodeSelection | null,
    modality: "text" | "voice" = "text",
  ) =>
    request<ChatAnswer>(`/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, selection: selection ?? null, modality }),
    }),
  createDeepTask: (
    learningSessionId: string,
    input: DeepTaskRequest,
    idempotencyKey: string,
  ) =>
    request<DeepTask>(
      `/learning-sessions/${encodeURIComponent(learningSessionId)}/deep-tasks`,
      {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(input),
      },
    ),
  getDeepTask: (taskId: string) =>
    request<DeepTask>(`/deep-tasks/${encodeURIComponent(taskId)}`),
  cancelDeepTask: (taskId: string) =>
    request<DeepTask>(`/deep-tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: "POST",
    }),
  deepTaskEventsUrl: (taskId: string) =>
    `${API_URL}/deep-tasks/${encodeURIComponent(taskId)}/events`,
};
