from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RepositoryCreate(BaseModel):
    url: HttpUrl
    branch: str | None = Field(default=None, max_length=255)


class RepositorySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    owner: str
    name: str
    url: str
    created_at: datetime


class AnalysisJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    snapshot_id: str
    stage: str
    status: str
    progress_current: int
    progress_total: int
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ReuseSummary(BaseModel):
    mode: Literal["exact_snapshot", "incremental", "full"]
    cache_hit: bool
    base_snapshot_id: str | None = None
    reason: str


class CacheSummary(BaseModel):
    retrieval: Literal["miss", "exact_hit", "semantic_hit"] = "miss"
    generation: Literal["miss", "exact_hit", "semantic_hit"] = "miss"
    similarity: float | None = None


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    branch: str | None
    commit_sha: str | None
    status: str
    analysis_fingerprint: str | None = None
    base_snapshot_id: str | None = None
    reuse_mode: str = "full"
    manifest_hash: str | None = None
    change_summary: dict = Field(default_factory=dict)
    resolved_at: datetime | None = None
    ready_at: datetime | None = None
    parser_version: str
    index_version: str
    file_count: int
    symbol_count: int
    edge_count: int
    chunk_count: int
    total_bytes: int
    embedding_model: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    job: AnalysisJobResponse | None = None


class RepositoryCreateResponse(BaseModel):
    repository: RepositorySummary
    snapshot: SnapshotResponse
    reuse: ReuseSummary


class TreeNode(BaseModel):
    id: str
    name: str
    path: str
    type: str
    file_id: str | None = None
    language: str | None = None
    children: list["TreeNode"] = Field(default_factory=list)


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    snapshot_id: str
    path: str
    language: str
    content: str
    content_hash: str
    byte_size: int
    line_count: int


class SymbolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_id: str
    qualified_name: str
    display_name: str
    kind: str
    signature: str | None
    start_line: int
    end_line: int


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str
    file_id: str | None = None
    path: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    confidence: float


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


ArchitectureConfidence = Literal["verified", "inferred", "unknown"]
ArchitectureLayer = Literal[
    "client", "server", "domain", "data", "external", "configuration", "shared"
]


class ArchitectureGraphEvidence(BaseModel):
    file_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    reason: str


class ArchitectureGraphGroup(BaseModel):
    id: str
    label: str
    description: str
    layer: ArchitectureLayer
    confidence: ArchitectureConfidence
    evidence: list[ArchitectureGraphEvidence]


class ArchitectureGraphNode(BaseModel):
    id: str
    label: str
    responsibility: str
    node_type: str
    group_id: str | None = None
    confidence: ArchitectureConfidence
    inputs: list[str]
    outputs: list[str]
    capability_ids: list[str]
    feature_flow_ids: list[str]
    evidence: list[ArchitectureGraphEvidence] = Field(min_length=1)


class ArchitectureGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    label: str
    description: str
    confidence: ArchitectureConfidence
    feature_flow_ids: list[str]
    evidence: list[ArchitectureGraphEvidence] = Field(min_length=1)


class ArchitectureGraphResponse(BaseModel):
    repository_name: str
    snapshot_id: str
    commit_sha: str
    analysis_version: str
    summary: str
    groups: list[ArchitectureGraphGroup] = Field(max_length=8)
    nodes: list[ArchitectureGraphNode] = Field(max_length=34)
    edges: list[ArchitectureGraphEdge] = Field(max_length=48)
    limitations: list[str]


class RepositoryStoryPurpose(BaseModel):
    one_liner: str
    primary_audience: str
    primary_outcome: str
    how_it_works: list[str] = Field(min_length=1, max_length=5)
    confidence: ArchitectureConfidence
    evidence: list[ArchitectureGraphEvidence] = Field(min_length=1)


class RepositoryStoryRole(BaseModel):
    id: str
    display_name: str
    role_summary: str
    why_it_exists: str
    contribution_to_goal: str
    receives: list[str]
    produces: list[str]
    member_node_ids: list[str] = Field(min_length=1)
    member_file_ids: list[str] = Field(min_length=1)
    capability_ids: list[str]
    feature_flow_ids: list[str]
    confidence: ArchitectureConfidence
    evidence: list[ArchitectureGraphEvidence] = Field(min_length=1)


class RepositoryStoryConnection(BaseModel):
    id: str
    source: str
    target: str
    label: str
    description: str
    relation_types: list[str] = Field(min_length=1)
    feature_flow_ids: list[str]
    confidence: ArchitectureConfidence
    evidence: list[ArchitectureGraphEvidence] = Field(min_length=1)


class RepositoryStoryResponse(BaseModel):
    repository_name: str
    snapshot_id: str
    commit_sha: str
    analysis_version: str
    purpose: RepositoryStoryPurpose
    roles: list[RepositoryStoryRole] = Field(min_length=1, max_length=12)
    connections: list[RepositoryStoryConnection]
    features: list["FeatureFlowSummary"]
    implementation_graph: ArchitectureGraphResponse
    limitations: list[str]


class ArchitectureGraphDiffNode(BaseModel):
    path: str
    status: Literal["added", "removed", "changed"]
    before_label: str | None = None
    after_label: str | None = None
    before_responsibility: str | None = None
    after_responsibility: str | None = None


class ArchitectureGraphDiffEdge(BaseModel):
    source_path: str
    target_path: str
    relation: str
    status: Literal["added", "removed"]


class ArchitectureGraphDiffResponse(BaseModel):
    repository_name: str
    base_snapshot_id: str
    target_snapshot_id: str
    base_commit_sha: str
    target_commit_sha: str
    nodes: list[ArchitectureGraphDiffNode]
    edges: list[ArchitectureGraphDiffEdge]
    summary: dict[str, int]


class EntryPoint(BaseModel):
    file_id: str
    path: str
    reason: str


class StartHereResponse(BaseModel):
    repository_name: str
    snapshot_id: str
    commit_sha: str
    summary: str
    tech_stack: list[str]
    entry_points: list[EntryPoint]
    top_directories: list[str]
    suggested_goals: list[str]


ProjectMapConfidence = Literal["verified", "inferred", "unknown"]


class ProjectMapEvidence(BaseModel):
    file_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    reason: str


class ProjectMapTechnology(BaseModel):
    name: str
    category: str
    confidence: ProjectMapConfidence
    evidence: list[ProjectMapEvidence] = Field(min_length=1)


class ProjectMapCapability(BaseModel):
    id: str
    name: str
    description: str
    confidence: ProjectMapConfidence
    evidence: list[ProjectMapEvidence] = Field(min_length=1)


class ProjectMapSystemArea(BaseModel):
    id: str
    name: str
    description: str
    confidence: ProjectMapConfidence
    evidence: list[ProjectMapEvidence] = Field(min_length=1)


class ProjectMapExternalService(BaseModel):
    name: str
    description: str
    confidence: ProjectMapConfidence
    evidence: list[ProjectMapEvidence] = Field(min_length=1)


class ProjectMapEnvironmentVariable(BaseModel):
    name: str
    description: str
    confidence: ProjectMapConfidence
    evidence: list[ProjectMapEvidence] = Field(min_length=1)


class ProjectMapReadFirst(ProjectMapEvidence):
    confidence: ProjectMapConfidence


class ProjectMapResponse(BaseModel):
    repository_name: str
    snapshot_id: str
    commit_sha: str
    summary: str
    summary_confidence: ProjectMapConfidence
    tech_stack: list[ProjectMapTechnology]
    capabilities: list[ProjectMapCapability]
    system_areas: list[ProjectMapSystemArea]
    external_services: list[ProjectMapExternalService]
    environment_variables: list[ProjectMapEnvironmentVariable]
    read_first: list[ProjectMapReadFirst]
    limitations: list[str]


FeatureFlowConfidence = Literal["verified", "inferred", "unknown"]


class FeatureFlowEvidence(BaseModel):
    file_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    reason: str


class FeatureFlowSummary(BaseModel):
    id: str
    title: str
    user_goal: str
    trigger: str
    outcome: str
    step_count: int = Field(ge=1)
    involved_areas: list[str]
    confidence: FeatureFlowConfidence
    evidence_coverage: float = Field(ge=0, le=1)
    entry_evidence: FeatureFlowEvidence


class FeatureFlowListResponse(BaseModel):
    repository_name: str
    snapshot_id: str
    commit_sha: str
    analysis_version: str
    flows: list[FeatureFlowSummary]
    limitations: list[str]


class FeatureFlowStep(BaseModel):
    id: str
    ordinal: int = Field(ge=1)
    title: str
    role: str
    executes_when: str
    input: str
    output_or_side_effect: str
    previous_step_id: str | None = None
    next_step_id: str | None = None
    relation_type: str
    confidence: FeatureFlowConfidence
    evidence: list[FeatureFlowEvidence] = Field(min_length=1)


class FeatureFlowDetail(BaseModel):
    id: str
    title: str
    user_goal: str
    trigger: str
    outcome: str
    normal_steps: list[FeatureFlowStep] = Field(min_length=1)
    failure_steps: list[FeatureFlowStep]
    involved_areas: list[str]
    confidence: FeatureFlowConfidence
    limitations: list[str]


class ChatSessionCreate(BaseModel):
    snapshot_id: str
    goal: str | None = Field(default=None, max_length=500)
    preferred_style: Literal["beginner", "standard", "advanced"] = "beginner"


class ChatSessionUpdate(BaseModel):
    preferred_style: Literal["beginner", "standard", "advanced"]


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    snapshot_id: str
    goal: str | None
    preferred_style: str
    learning_session_id: str | None
    navigation_context: dict
    created_at: datetime
    updated_at: datetime


class CodeSelection(BaseModel):
    file_id: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


CodeExplanationDepth = Literal["minimum", "behavior", "syntax", "analogy", "change"]


class CodeExplanationCreate(BaseModel):
    selection: CodeSelection
    feature_flow_id: str | None = Field(default=None, max_length=100)
    flow_step_id: str | None = Field(default=None, max_length=100)
    depth: CodeExplanationDepth = "minimum"


class CodeExplanationEvidence(BaseModel):
    file_id: str
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    reason: str


class CodeExplanationRelatedStep(BaseModel):
    relation_type: str
    title: str
    target: str
    confidence: ProjectMapConfidence
    evidence: CodeExplanationEvidence


class CodeExplanationSyntaxSegment(BaseModel):
    node_type: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    explanation: str


class CodeExplanationResponse(BaseModel):
    id: str
    snapshot_id: str
    analysis_version: str
    depth: CodeExplanationDepth
    selection: CodeSelection
    purpose: str
    executes_when: str
    input: str
    output_or_side_effect: str
    project_role: str
    change_impact: str
    required_concepts: list[str]
    related_steps: list[CodeExplanationRelatedStep]
    syntax_segments: list[CodeExplanationSyntaxSegment]
    analogy: str | None = None
    confidence: ProjectMapConfidence
    evidence: list[CodeExplanationEvidence] = Field(min_length=1)
    limitations: list[str]


class NavigationContext(BaseModel):
    feature_key: str | None = Field(default=None, max_length=100)
    flow_step_id: str | None = Field(default=None, max_length=100)
    selection: CodeSelection | None = None
    explanation_depth: CodeExplanationDepth | None = None


ChangeBriefRisk = Literal["low", "medium", "high", "unknown"]


class ChangeBriefCandidateLocation(BaseModel):
    title: str
    reason: str
    confidence: ProjectMapConfidence
    evidence: CodeExplanationEvidence


class ChangeBriefImpact(BaseModel):
    title: str
    description: str
    relation_type: str
    confidence: ProjectMapConfidence
    evidence: list[CodeExplanationEvidence] = Field(min_length=1)


class ChangeBriefResponse(BaseModel):
    id: str
    snapshot_id: str
    analysis_version: str
    request_summary: str
    selection: CodeSelection
    candidate_locations: list[ChangeBriefCandidateLocation] = Field(min_length=1)
    confirmed_direct_impacts: list[ChangeBriefImpact]
    possible_impacts_to_verify: list[ChangeBriefImpact]
    unknown_boundaries: list[str] = Field(min_length=1)
    risk_level: ChangeBriefRisk
    risk_rationale: str
    verification_steps: list[str] = Field(min_length=1)
    rollback_guidance: list[str] = Field(min_length=1)
    evidence: list[CodeExplanationEvidence] = Field(min_length=1)
    limitations: list[str]


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=2, max_length=4_000)
    selection: CodeSelection | None = None
    modality: Literal["text", "voice"] = "text"


class CitationResponse(BaseModel):
    evidence_id: str
    source_type: str = "repository_code"
    snapshot_id: str
    file_id: str
    path: str
    language: str
    title: str
    chunk_type: str
    start_line: int
    end_line: int
    preview: str
    score: float
    retrievers: list[str]


class ChatAnswerResponse(BaseModel):
    id: str
    session_id: str
    question: str
    answer: str
    status: str
    intent: str
    retrieval_run_id: str
    citations: list[CitationResponse]
    follow_up: str | None
    voice_summary: str | None = None
    generation_mode: str
    model_name: str | None
    created_at: datetime
    cache: CacheSummary | None = Field(default=None, exclude_if=lambda value: value is None)
    usage: dict | None = Field(default=None, exclude_if=lambda value: value is None)
    quota: dict | None = Field(default=None, exclude_if=lambda value: value is None)


class DeepTaskCreate(BaseModel):
    kind: Literal[
        "deep_explanation",
        "impact_analysis",
        "roadmap_proposal",
        "research_materials",
    ]
    prompt: str = Field(min_length=2, max_length=4_000)
    selection: CodeSelection | None = None
    navigation_context: NavigationContext | None = None
    modality: Literal["text", "voice"] = "text"


class DeepTaskErrorResponse(BaseModel):
    code: str
    message: str


class ResearchSourceResponse(BaseModel):
    title: str
    publisher: str
    url: HttpUrl
    difficulty: Literal["beginner", "intermediate", "advanced"]
    estimated_minutes: int = Field(ge=1, le=240)
    recommendation_reason: str
    checked_at: datetime


class ResearchMaterialsResponse(BaseModel):
    answer: str
    voice_summary: str | None = None
    sources: list[ResearchSourceResponse] = Field(min_length=1, max_length=8)
    generation_mode: Literal["openai_web_search"] = "openai_web_search"
    model_name: str


class DeepTaskResponse(BaseModel):
    id: str
    status: Literal[
        "queued",
        "running",
        "retrieving",
        "reasoning",
        "verifying",
        "completed",
        "failed",
        "cancelled",
    ]
    kind: str
    progress: int = Field(ge=0, le=100)
    message: str
    result: ChatAnswerResponse | ResearchMaterialsResponse | ChangeBriefResponse | None = None
    error: DeepTaskErrorResponse | None = None


class GuidedStepResponse(BaseModel):
    id: str
    ordinal: int
    step_type: str
    title: str
    learning_objective: str
    summary: str
    concept_ids: list[str]
    checkpoint: dict
    estimated_minutes: int
    evidence: CitationResponse


class GuidedPathResponse(BaseModel):
    id: str
    snapshot_id: str
    title: str
    goal: str
    difficulty: str
    path_version: str
    generation_method: str
    total_minutes: int
    steps: list[GuidedStepResponse]
    created_at: datetime
    updated_at: datetime


class GuidedTourSessionCreate(BaseModel):
    preferred_style: Literal["beginner", "standard", "advanced"] = "beginner"


class GuidedTourSessionResponse(BaseModel):
    id: str
    path_id: str
    preferred_style: str
    status: str
    current_step_ordinal: int
    completed_step_ids: list[str]
    needs_help_step_ids: list[str]
    completed_count: int
    total_steps: int
    created_at: datetime
    updated_at: datetime


class GuidedStepFeedbackCreate(BaseModel):
    event_type: Literal["opened", "understood", "needs_help"]
    payload: dict = Field(default_factory=dict)


class LearnerProfileCreate(BaseModel):
    anonymous_key: str = Field(min_length=8, max_length=120)


class LearnerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    anonymous_key: str
    goal: str
    preferred_explanation: list[str]
    pace: str
    background: dict
    concept_mastery: dict
    assessment_version: str
    created_at: datetime
    updated_at: datetime


class AssessmentSessionCreate(BaseModel):
    learner_profile_id: str


class AssessmentChoice(BaseModel):
    value: str
    label: str


class AssessmentQuestionResponse(BaseModel):
    id: str
    category: str
    prompt: str
    choices: list[AssessmentChoice]
    concept_id: str | None = None
    stack_requirement: str | None = None


class AssessmentSessionResponse(BaseModel):
    id: str
    snapshot_id: str
    learner_profile_id: str
    status: str
    detected_stack: list[str]
    assessment_version: str
    questions: list[AssessmentQuestionResponse]
    answers: dict[str, str]
    answered_count: int
    total_count: int
    created_at: datetime
    submitted_at: datetime | None
    skipped_at: datetime | None
    profile: LearnerProfileResponse


class AssessmentAnswerCreate(BaseModel):
    item_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=500)


class LearningPathCreate(BaseModel):
    learner_profile_id: str
    goal: str | None = Field(default=None, max_length=60)


class LearningStepResponse(BaseModel):
    id: str
    ordinal: int
    step_type: str
    title: str
    instruction: str
    concept_id: str | None
    evidence: CitationResponse | None
    metadata: dict


class LearningLessonResponse(BaseModel):
    id: str
    ordinal: int
    lesson_type: str
    title: str
    objective: str
    required_concept_ids: list[str]
    checkpoint: dict
    estimated_minutes: int
    optional: bool
    steps: list[LearningStepResponse]


class LearningModuleResponse(BaseModel):
    id: str
    ordinal: int
    module_type: str
    title: str
    objective: str
    required: bool
    estimated_minutes: int
    coverage_keys: list[str]
    lessons: list[LearningLessonResponse]


class LearningPathResponse(BaseModel):
    id: str
    snapshot_id: str
    learner_profile_id: str
    title: str
    goal: str
    status: str
    path_version: str
    generation_method: str
    coverage: dict
    model_metadata: dict
    estimated_minutes: int
    total_modules: int
    total_lessons: int
    modules: list[LearningModuleResponse]
    created_at: datetime
    updated_at: datetime


class LearningSessionCreate(BaseModel):
    preferred_style: Literal["beginner", "standard", "advanced"] = "beginner"


class LearningSessionResponse(BaseModel):
    id: str
    snapshot_id: str
    learner_profile_id: str
    path_id: str
    chat_session_id: str
    current_module_id: str | None
    current_lesson_id: str | None
    current_step_id: str | None
    completed_lesson_ids: list[str]
    return_stack: list[dict]
    current_selection: dict
    focus_concept_ids: list[str]
    status: str
    completed_count: int
    total_lessons: int
    created_at: datetime
    updated_at: datetime


class LearningReplanResponse(BaseModel):
    path: LearningPathResponse
    session: LearningSessionResponse
    preserved_lesson_ids: list[str]
    added_lesson_count: int
    revision: int


class LearningLessonFeedbackCreate(BaseModel):
    event_type: Literal["opened", "understood", "needs_help", "skip"]


class LearningSelectionUpdate(BaseModel):
    selection: CodeSelection | None = None


class RemediationCreate(BaseModel):
    mode: Literal["line_by_line", "prerequisite", "small_example", "learning_sources"]
    lesson_id: str
    step_id: str | None = None


class RemediationBranchResponse(BaseModel):
    id: str
    learning_session_id: str
    source_lesson_id: str
    source_step_id: str | None
    mode: str
    status: str
    concept_ids: list[str]
    content: dict
    return_lesson_id: str
    return_step_id: str | None
    created_at: datetime
    completed_at: datetime | None


class ExplanationSegmentResponse(BaseModel):
    segment_id: str
    start_line: int
    end_line: int
    source: str
    what: str
    why: str
    syntax_concepts: list[str]
    evidence_id: str


class LineExplanationResponse(BaseModel):
    artifact_id: str
    step_id: str
    file_id: str
    path: str
    segments: list[ExplanationSegmentResponse]
    generation_mode: str


class LearningSourceResponse(BaseModel):
    id: str
    concept_id: str
    title: str
    publisher: str
    canonical_url: str
    source_tier: str
    difficulty: str
    language: str
    estimated_minutes: int
    recommendation_reason: str


class ActivityChoiceResponse(BaseModel):
    id: str
    label: str


class ActivityAttemptSummary(BaseModel):
    id: str
    selected_choice_id: str
    is_correct: bool
    score_delta: float
    feedback: dict
    created_at: datetime


class LearningActivityResponse(BaseModel):
    id: str
    step_id: str
    activity_type: str
    prompt: str
    choices: list[ActivityChoiceResponse]
    concept_ids: list[str]
    evidence: CitationResponse
    generator_version: str
    latest_attempt: ActivityAttemptSummary | None


class ActivityAttemptCreate(BaseModel):
    selected_choice_id: str = Field(min_length=1, max_length=80)


class MasteryUpdateResponse(BaseModel):
    concept_id: str
    previous_score: float
    new_score: float
    previous_confidence: float
    new_confidence: float


class ActivityAttemptResponse(BaseModel):
    id: str
    activity_id: str
    learning_session_id: str
    selected_choice_id: str
    correct_choice_id: str
    is_correct: bool
    score_delta: float
    feedback: dict
    evidence: CitationResponse
    mastery_updates: list[MasteryUpdateResponse]
    created_at: datetime


class MasteryEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    learner_profile_id: str
    learning_session_id: str | None
    concept_id: str
    event_type: str
    source_type: str
    source_id: str | None
    previous_score: float
    new_score: float
    previous_confidence: float
    new_confidence: float
    evidence: dict
    policy_version: str
    created_at: datetime


class ConceptMasteryStateResponse(BaseModel):
    concept_id: str
    display_name: str
    description: str
    domain: str
    difficulty: str
    score: float
    confidence: float
    state: Literal["unknown", "needs_review", "developing", "ready"]
    source: str | None
    prerequisite_ids: list[str]
    event_count: int
    last_event_at: datetime | None


class MasterySummaryResponse(BaseModel):
    ready: int
    developing: int
    needs_review: int
    unknown: int
    total: int


class MasteryOverviewResponse(BaseModel):
    profile_id: str
    graph_version: str
    summary: MasterySummaryResponse
    concepts: list[ConceptMasteryStateResponse]
    recent_events: list[MasteryEventResponse]


class RetrievalCandidateDebug(BaseModel):
    evidence_id: str
    source_id: str
    retriever: str
    rank: int
    raw_score: float
    rrf_score: float
    rerank_score: float | None
    selected: bool
    title: str
    path: str
    start_line: int
    end_line: int


class RetrievalRunDebug(BaseModel):
    id: str
    session_id: str
    message_id: str
    query_text: str
    intent: str
    resolved_context: dict
    retrieval_plan: dict
    index_version: str
    latency_ms: int
    created_at: datetime
    candidates: list[RetrievalCandidateDebug]


class UserResponse(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    kind: str
    role: str | None = None


class MeResponse(BaseModel):
    user: UserResponse
    active_organization: OrganizationResponse
    organizations: list[OrganizationResponse]


class UsageCurrentResponse(BaseModel):
    organization_id: str
    period_start: datetime
    period_end: datetime
    allowance_micro_usd: int
    bonus_available_micro_usd: int
    reserved_micro_usd: int
    consumed_micro_usd: int
    remaining_micro_usd: int


class UsageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    feature: str
    provider: str | None
    model: str | None
    usage_json: dict
    settled_cost_micro_usd: int
    cache_status: str
    created_at: datetime


class FeatureLimitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature: str
    request_limit: int | None
    token_limit: int | None
    duration_limit_seconds: int | None
    concurrent_limit: int | None
    max_input_size: int | None
    max_output_tokens: int | None


class BonusCreditCreate(BaseModel):
    amount_micro_usd: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=2_000)
    reference: str = Field(min_length=1, max_length=240)
    expires_at: datetime | None = None


class BonusCreditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    amount_micro_usd: int
    remaining_micro_usd: int
    reason: str
    reference: str
    expires_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
