import { getSupabaseBrowserClient } from "@/lib/supabase/client";

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
  analysis_fingerprint: string | null;
  base_snapshot_id: string | null;
  reuse_mode: "full" | "incremental" | "exact";
  manifest_hash: string | null;
  change_summary: Record<string, unknown>;
  resolved_at: string | null;
  ready_at: string | null;
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
  reuse: {
    mode: "exact_snapshot" | "incremental" | "full";
    cache_hit: boolean;
    base_snapshot_id: string | null;
    reason: string;
  };
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

export type ProjectMapConfidence = "verified" | "inferred" | "unknown";

export type ArchitectureLayer =
  | "client"
  | "server"
  | "domain"
  | "data"
  | "external"
  | "configuration"
  | "shared";

export type ProjectMapEvidence = {
  file_id: string;
  path: string;
  start_line: number;
  end_line: number;
  reason: string;
};

export type ProjectMapTechnology = {
  name: string;
  category: string;
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type ProjectMapCapability = {
  id: string;
  name: string;
  description: string;
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type ProjectMapSystemArea = {
  id: string;
  name: string;
  description: string;
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type ProjectMapExternalService = {
  name: string;
  description: string;
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type ProjectMapEnvironmentVariable = {
  name: string;
  description: string;
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type ProjectMapReadFirst = ProjectMapEvidence & {
  confidence: ProjectMapConfidence;
};

export type ProjectMap = {
  repository_name: string;
  snapshot_id: string;
  commit_sha: string;
  summary: string;
  summary_confidence: ProjectMapConfidence;
  tech_stack: ProjectMapTechnology[];
  capabilities: ProjectMapCapability[];
  system_areas: ProjectMapSystemArea[];
  external_services: ProjectMapExternalService[];
  environment_variables: ProjectMapEnvironmentVariable[];
  read_first: ProjectMapReadFirst[];
  limitations: string[];
};

export type ArchitectureGraphGroup = {
  id: string;
  label: string;
  description: string;
  layer: ArchitectureLayer;
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type ArchitectureGraphNode = {
  id: string;
  label: string;
  responsibility: string;
  node_type: string;
  group_id: string | null;
  confidence: ProjectMapConfidence;
  inputs: string[];
  outputs: string[];
  capability_ids: string[];
  feature_flow_ids: string[];
  evidence: ProjectMapEvidence[];
};

export type ArchitectureGraphEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
  label: string;
  description: string;
  confidence: ProjectMapConfidence;
  feature_flow_ids: string[];
  evidence: ProjectMapEvidence[];
};

export type ArchitectureGraph = {
  repository_name: string;
  snapshot_id: string;
  commit_sha: string;
  analysis_version: string;
  summary: string;
  groups: ArchitectureGraphGroup[];
  nodes: ArchitectureGraphNode[];
  edges: ArchitectureGraphEdge[];
  limitations: string[];
};

export type RepositoryStoryPurpose = {
  one_liner: string;
  primary_audience: string;
  primary_outcome: string;
  how_it_works: string[];
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type RepositoryStoryRole = {
  id: string;
  display_name: string;
  role_summary: string;
  why_it_exists: string;
  contribution_to_goal: string;
  receives: string[];
  produces: string[];
  member_node_ids: string[];
  member_file_ids: string[];
  capability_ids: string[];
  feature_flow_ids: string[];
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type RepositoryStoryConnection = {
  id: string;
  source: string;
  target: string;
  label: string;
  description: string;
  relation_types: string[];
  feature_flow_ids: string[];
  confidence: ProjectMapConfidence;
  evidence: ProjectMapEvidence[];
};

export type RepositoryStory = {
  repository_name: string;
  snapshot_id: string;
  commit_sha: string;
  analysis_version: string;
  purpose: RepositoryStoryPurpose;
  roles: RepositoryStoryRole[];
  connections: RepositoryStoryConnection[];
  features: FeatureFlowSummary[];
  implementation_graph: ArchitectureGraph;
  limitations: string[];
};

export type ArchitectureGraphDiff = {
  repository_name: string;
  base_snapshot_id: string;
  target_snapshot_id: string;
  base_commit_sha: string;
  target_commit_sha: string;
  nodes: Array<{
    path: string;
    status: "added" | "removed" | "changed";
    before_label: string | null;
    after_label: string | null;
    before_responsibility: string | null;
    after_responsibility: string | null;
  }>;
  edges: Array<{
    source_path: string;
    target_path: string;
    relation: string;
    status: "added" | "removed";
  }>;
  summary: {
    nodes_added: number;
    nodes_removed: number;
    nodes_changed: number;
    edges_added: number;
    edges_removed: number;
  };
};

export type FeatureFlowEvidence = ProjectMapEvidence;

export type FeatureFlowSummary = {
  id: string;
  title: string;
  user_goal: string;
  trigger: string;
  outcome: string;
  step_count: number;
  involved_areas: string[];
  confidence: ProjectMapConfidence;
  evidence_coverage: number;
  entry_evidence: FeatureFlowEvidence;
};

export type FeatureFlowCatalog = {
  repository_name: string;
  snapshot_id: string;
  commit_sha: string;
  analysis_version: string;
  flows: FeatureFlowSummary[];
  limitations: string[];
};

export type FeatureFlowStep = {
  id: string;
  ordinal: number;
  title: string;
  role: string;
  executes_when: string;
  input: string;
  output_or_side_effect: string;
  previous_step_id: string | null;
  next_step_id: string | null;
  relation_type: string;
  confidence: ProjectMapConfidence;
  evidence: FeatureFlowEvidence[];
};

export type FeatureFlowDetail = {
  id: string;
  title: string;
  user_goal: string;
  trigger: string;
  outcome: string;
  normal_steps: FeatureFlowStep[];
  failure_steps: FeatureFlowStep[];
  involved_areas: string[];
  confidence: ProjectMapConfidence;
  limitations: string[];
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

export type CodeExplanationDepth = "minimum" | "behavior" | "syntax" | "analogy" | "change";

export type CodeExplanationEvidence = {
  file_id: string;
  path: string;
  start_line: number;
  end_line: number;
  reason: string;
};

export type CodeExplanationRelatedStep = {
  relation_type: string;
  title: string;
  target: string;
  confidence: ProjectMapConfidence;
  evidence: CodeExplanationEvidence;
};

export type CodeExplanationSyntaxSegment = {
  node_type: string;
  start_line: number;
  end_line: number;
  explanation: string;
};

export type CodeExplanation = {
  id: string;
  snapshot_id: string;
  analysis_version: string;
  depth: CodeExplanationDepth;
  selection: CodeSelection;
  purpose: string;
  executes_when: string;
  input: string;
  output_or_side_effect: string;
  project_role: string;
  change_impact: string;
  required_concepts: string[];
  related_steps: CodeExplanationRelatedStep[];
  syntax_segments: CodeExplanationSyntaxSegment[];
  analogy: string | null;
  confidence: ProjectMapConfidence;
  evidence: CodeExplanationEvidence[];
  limitations: string[];
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
  navigation_context: NavigationContext;
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
  navigation_context?: NavigationContext | null;
  modality: "text" | "voice";
};

export type NavigationContext = {
  feature_key?: string | null;
  flow_step_id?: string | null;
  selection?: CodeSelection | null;
  explanation_depth?: CodeExplanationDepth | null;
};

export type ChangeBriefRisk = "low" | "medium" | "high" | "unknown";

export type ChangeBriefCandidateLocation = {
  title: string;
  reason: string;
  confidence: ProjectMapConfidence;
  evidence: CodeExplanationEvidence;
};

export type ChangeBriefImpact = {
  title: string;
  description: string;
  relation_type: string;
  confidence: ProjectMapConfidence;
  evidence: CodeExplanationEvidence[];
};

export type ChangeBrief = {
  id: string;
  snapshot_id: string;
  analysis_version: string;
  request_summary: string;
  selection: CodeSelection;
  candidate_locations: ChangeBriefCandidateLocation[];
  confirmed_direct_impacts: ChangeBriefImpact[];
  possible_impacts_to_verify: ChangeBriefImpact[];
  unknown_boundaries: string[];
  risk_level: ChangeBriefRisk;
  risk_rationale: string;
  verification_steps: string[];
  rollback_guidance: string[];
  evidence: CodeExplanationEvidence[];
  limitations: string[];
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

export type DeepTaskResult = ChatAnswer | ResearchMaterials | ChangeBrief;

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

export type Organization = { id: string; name: string; slug: string; kind: string; role: string | null };
export type Me = { user: { id: string; email: string | null; display_name: string | null }; active_organization: Organization; organizations: Organization[] };
export type UsageCurrent = { organization_id: string; period_start: string; period_end: string; allowance_micro_usd: number; bonus_available_micro_usd: number; reserved_micro_usd: number; consumed_micro_usd: number; remaining_micro_usd: number };
export type FeatureLimit = { feature: string; request_limit: number | null; token_limit: number | null; duration_limit_seconds: number | null; concurrent_limit: number | null; max_input_size: number | null; max_output_tokens: number | null };
export type UsageEvent = { id: string; feature: string; provider: string | null; model: string | null; usage_json: Record<string, number>; settled_cost_micro_usd: number; cache_status: string; created_at: string };
export type BonusCredit = { id: string; organization_id: string; amount_micro_usd: number; remaining_micro_usd: number; reason: string; reference: string; expires_at: string | null; cancelled_at: string | null; created_at: string };
export type UsageReconciliation = { pending_reconciliation: number; stale_reservations: number; internal_settled_micro_usd: number; invalid_cache_entries: number; checked_at: string };
class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function authenticatedFetch(path: string, init?: RequestInit) {
  const client = getSupabaseBrowserClient();
  const buildHeaders = async () => {
    const headers: Record<string, string> = {};
    if (init?.headers instanceof Headers) {
      init.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(init?.headers)) {
      for (const [key, value] of init.headers) headers[key] = value;
    } else if (init?.headers) {
      Object.assign(headers, init.headers);
    }
    if (!Object.keys(headers).some((key) => key.toLowerCase() === "content-type")) {
      headers["Content-Type"] = "application/json";
    }
    const session = client ? (await client.auth.getSession()).data.session : null;
    if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`;
    const organizationId =
      typeof window !== "undefined" ? localStorage.getItem("repowise.organization") : null;
    if (organizationId) headers["X-Organization-Id"] = organizationId;
    return headers;
  };
  const url = /^https?:\/\//.test(path) ? path : `${API_URL}${path}`;
  let response = await fetch(url, { ...init, headers: await buildHeaders() });
  if (response.status === 401 && client) {
    const { data } = await client.auth.refreshSession();
    if (data.session) response = await fetch(url, { ...init, headers: await buildHeaders() });
  }
  return response;
}

async function errorMessage(response: Response) {
  const message = `Request failed with HTTP ${response.status}`;
  try {
    const payload = (await response.json()) as { detail?: string | { code?: string; message?: string } };
    if (typeof payload.detail === "string") return payload.detail;
    if (payload.detail?.message) return payload.detail.message;
    if (payload.detail?.code) {
      const messages: Record<string, string> = {
        authentication_required: "로그인이 필요합니다.",
        invalid_access_token: "로그인 세션이 만료되었습니다. 다시 로그인해 주세요.",
        organization_access_denied: "이 조직의 자원에 접근할 권한이 없습니다.",
        monthly_quota_exceeded: "이번 달 사용 한도를 초과했습니다.",
        feature_limit_exceeded: "이 기능의 사용 한도를 초과했습니다.",
        feature_concurrency_exceeded: "이 기능의 동시 실행 한도를 초과했습니다.",
      };
      return messages[payload.detail.code] ?? payload.detail.code;
    }
  } catch {
    // Preserve the HTTP fallback when the response is not JSON.
  }
  if (response.status === 401) return "로그인이 필요합니다.";
  if (response.status === 403) return "이 작업을 수행할 권한이 없습니다.";
  if (response.status === 429) return "사용 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.";
  return message;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(path, init);
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return (await response.json()) as T;
}

async function requestText(path: string, init?: RequestInit): Promise<string> {
  const response = await authenticatedFetch(path, init);
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return response.text();
}
export const api = {
  health: () => request<Health>("/health"),
  me: () => request<Me>("/me"),
  organizations: () => request<Organization[]>("/organizations"),
  currentUsage: (organizationId: string) =>
    request<UsageCurrent>(`/organizations/${encodeURIComponent(organizationId)}/usage/current`),
  usageEvents: (organizationId: string) =>
    request<UsageEvent[]>(`/organizations/${encodeURIComponent(organizationId)}/usage/events`),
  featureLimits: (organizationId: string) =>
    request<FeatureLimit[]>(`/organizations/${encodeURIComponent(organizationId)}/limits`),
  grantBonusCredit: (
    organizationId: string,
    payload: { amount_micro_usd: number; reason: string; reference: string; expires_at?: string },
  ) =>
    request<BonusCredit>(
      `/admin/organizations/${encodeURIComponent(organizationId)}/bonus-credits`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  usageReconciliation: () =>
    request<UsageReconciliation>("/admin/usage/reconciliation"),
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
  getArchitectureGraph: (snapshotId: string, featureFlowId?: string | null) =>
    request<ArchitectureGraph>(
      `/snapshots/${snapshotId}/architecture-graph${
        featureFlowId ? `?feature_flow_id=${encodeURIComponent(featureFlowId)}` : ""
      }`,
    ),
  getRepositoryStory: (snapshotId: string) =>
    request<RepositoryStory>(`/snapshots/${snapshotId}/repository-story`),
  getArchitectureGraphDiff: (snapshotId: string, baseSnapshotId: string) =>
    request<ArchitectureGraphDiff>(
      `/snapshots/${snapshotId}/architecture-graph/diff?base_snapshot_id=${encodeURIComponent(
        baseSnapshotId,
      )}`,
    ),
  enhanceArchitectureGraphLabels: (snapshotId: string) =>
    request<ArchitectureGraph>(
      `/snapshots/${snapshotId}/architecture-graph/enhance-labels`,
      { method: "POST" },
    ),
  getStartHere: (snapshotId: string) =>
    request<StartHere>(`/snapshots/${snapshotId}/start-here`),
  getProjectMap: (snapshotId: string) =>
    request<ProjectMap>(`/snapshots/${snapshotId}/project-map`),
  getFeatureFlows: (snapshotId: string) =>
    request<FeatureFlowCatalog>(`/snapshots/${snapshotId}/feature-flows`),
  getFeatureFlow: (snapshotId: string, flowId: string) =>
    request<FeatureFlowDetail>(
      `/snapshots/${snapshotId}/feature-flows/${encodeURIComponent(flowId)}`,
    ),
  createCodeExplanation: (
    snapshotId: string,
    selection: CodeSelection,
    depth: CodeExplanationDepth = "minimum",
    context?: { featureFlowId?: string | null; flowStepId?: string | null },
  ) =>
    request<CodeExplanation>(`/snapshots/${snapshotId}/code-explanations`, {
      method: "POST",
      body: JSON.stringify({
        selection,
        depth,
        feature_flow_id: context?.featureFlowId ?? null,
        flow_step_id: context?.flowStepId ?? null,
      }),
    }),
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
  createNavigationDeepTask: (
    chatSessionId: string,
    input: DeepTaskRequest,
    idempotencyKey: string,
  ) =>
    request<DeepTask>(
      `/chat/sessions/${encodeURIComponent(chatSessionId)}/deep-tasks`,
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
