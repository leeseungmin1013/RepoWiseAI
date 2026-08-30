import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  health: vi.fn(),
  listSnapshots: vi.fn(),
  createRepository: vi.fn(),
  getSnapshot: vi.fn(),
  retrySnapshot: vi.fn(),
  createLearnerProfile: vi.fn(),
  getProjectMap: vi.fn(),
  getArchitectureGraph: vi.fn(),
  getRepositoryStory: vi.fn(),
  getFeatureFlows: vi.fn(),
  getFeatureFlow: vi.fn(),
  createCodeExplanation: vi.fn(),
  createChatSession: vi.fn(),
  createNavigationDeepTask: vi.fn(),
  startDeepTask: vi.fn(),
  getTree: vi.fn(),
  getStartHere: vi.fn(),
  getGraph: vi.fn(),
  getFile: vi.fn(),
  getSymbols: vi.fn(),
  createAssessmentSession: vi.fn(),
  getAssessmentSession: vi.fn(),
  createLearningPath: vi.fn(),
}));

vi.mock("./AuthUserMenu", () => ({
  AuthUserMenu: () => <div data-testid="auth-user-menu" />,
}));
vi.mock("@/lib/api", () => ({
  api: {
    health: mocks.health,
    listSnapshots: mocks.listSnapshots,
    createRepository: mocks.createRepository,
    getSnapshot: mocks.getSnapshot,
    retrySnapshot: mocks.retrySnapshot,
    createLearnerProfile: mocks.createLearnerProfile,
    getProjectMap: mocks.getProjectMap,
    getArchitectureGraph: mocks.getArchitectureGraph,
    getRepositoryStory: mocks.getRepositoryStory,
    getFeatureFlows: mocks.getFeatureFlows,
    getFeatureFlow: mocks.getFeatureFlow,
    createCodeExplanation: mocks.createCodeExplanation,
    createChatSession: mocks.createChatSession,
    createNavigationDeepTask: mocks.createNavigationDeepTask,
    getTree: mocks.getTree,
    getStartHere: mocks.getStartHere,
    getGraph: mocks.getGraph,
    getFile: mocks.getFile,
    getSymbols: mocks.getSymbols,
    createAssessmentSession: mocks.createAssessmentSession,
    getAssessmentSession: mocks.getAssessmentSession,
    createLearningPath: mocks.createLearningPath,
  },
}));

vi.mock("@/hooks/useRealtimeLearningSession", () => ({
  useRealtimeLearningSession: () => ({
    isConnected: false,
    speakVerifiedText: vi.fn(),
    stop: vi.fn(),
  }),
}));

vi.mock("@/hooks/useDeepLearningTask", () => ({
  useDeepLearningTask: () => ({
    cancel: vi.fn(),
    error: null,
    isCancelling: false,
    isRunning: false,
    isStarting: false,
    reset: vi.fn(),
    start: mocks.startDeepTask,
    task: null,
  }),
}));

vi.mock("@/lib/deep-tasks", () => ({
  routeQuestionToDeepTask: () => null,
}));

vi.mock("./AssistantPanel", () => ({
  AssistantPanel: () => <div>학습 패널</div>,
}));

vi.mock("./ArchitectureMapPanel", () => ({
  ArchitectureMapPanel: ({ graph, loading }: { graph: { snapshot_id: string } | null; loading: boolean }) => (
    <div data-testid="architecture-map">
      {loading ? "loading" : graph?.snapshot_id ?? "empty"}
    </div>
  ),
}));

vi.mock("./RepositoryStoryPage", () => ({
  RepositoryStoryPage: ({
    story,
    loading,
    onOpenEvidence,
    onOpenDependencyGraph,
    onStartLearning,
    onSelectFlow,
  }: {
    story: {
      snapshot_id: string;
      purpose: { one_liner: string };
      roles: Array<{
        display_name: string;
        evidence: Array<{
          file_id: string;
          path: string;
          start_line: number;
          end_line: number;
          reason: string;
        }>;
      }>;
      features: Array<{ id: string; title: string }>;
    } | null;
    loading: boolean;
    onOpenEvidence: (evidence: {
      file_id: string;
      path: string;
      start_line: number;
      end_line: number;
      reason: string;
    }) => void;
    onOpenDependencyGraph: () => void;
    onStartLearning: () => void;
    onSelectFlow: (flowId: string | null) => void;
  }) => (
    <div data-testid="repository-story">
      {loading ? "loading" : story?.purpose.one_liner ?? "empty"}
      {story?.roles.map((role) => (
        <div key={role.display_name}>
          <span>{role.display_name}</span>
          {role.evidence.map((item) => (
            <button
              key={item.file_id}
              aria-label={`근거 코드 열기: ${role.display_name}, ${item.path}`}
              onClick={() => onOpenEvidence(item)}
              type="button"
            >
              근거
            </button>
          ))}
        </div>
      ))}
      {story?.features.map((feature) => (
        <button key={feature.id} onClick={() => onSelectFlow(feature.id)} type="button">
          {feature.title} 구조도에 표시
        </button>
      ))}
      <button onClick={onOpenDependencyGraph} type="button">원본 코드 탐색</button>
      <button onClick={onStartLearning} type="button">깊이 배우기 선택</button>
    </div>
  ),
}));

vi.mock("./CodePanel", () => ({
  CodePanel: ({
    file,
    highlight,
    loading,
  }: {
    file: { id: string } | null;
    highlight: { startLine: number; endLine: number } | null;
    loading: boolean;
  }) => (
    <div>
      코드 패널
      <span data-testid="opened-file">{file?.id ?? "none"}</span>
      <span data-testid="opened-highlight">
        {highlight ? `${highlight.startLine}-${highlight.endLine}` : "none"}
      </span>
      <span data-testid="file-loading">{loading ? "loading" : "idle"}</span>
    </div>
  ),
}));

vi.mock("./CodeFocusPanel", () => ({
  CodeFocusPanel: ({
    explanation,
    loading,
  }: {
    explanation: { purpose: string } | null;
    loading: boolean;
  }) => (
    <div>
      Code Focus
      <span data-testid="code-focus-state">
        {loading ? "loading" : explanation?.purpose ?? "empty"}
      </span>
    </div>
  ),
}));

vi.mock("./ChangeBriefPanel", () => ({
  ChangeBriefPanel: ({
    selection,
    onStart,
  }: {
    selection: { file_id: string } | null;
    onStart: (prompt: string) => void;
  }) => (
    <div>
      Change Brief
      <span data-testid="change-brief-selection">{selection?.file_id ?? "none"}</span>
      <button onClick={() => onStart("이 동작을 바꾸고 싶어요")} type="button">
        변경 요청 테스트
      </button>
    </div>
  ),
}));

vi.mock("./FileTree", () => ({
  FileTree: ({ onSelectFile }: { onSelectFile: (fileId: string) => void }) => (
    <div>
      파일 트리
      <button type="button" onClick={() => onSelectFile("file-slow")}>느린 파일</button>
      <button type="button" onClick={() => onSelectFile("file-latest")}>최신 파일</button>
    </div>
  ),
}));

vi.mock("./StartHerePanel", () => ({
  StartHerePanel: () => <div>원본 개요</div>,
}));

import { RepositoryWorkbench } from "./RepositoryWorkbench";

const snapshot = {
  id: "snap_map",
  repository_id: "repo_1",
  branch: "main",
  commit_sha: "abcdef1234567890",
  status: "ready",
  parser_version: "tree-sitter-v1",
  index_version: "index-v1",
  file_count: 3,
  symbol_count: 5,
  edge_count: 2,
  chunk_count: 6,
  total_bytes: 300,
  embedding_model: "local",
  error_message: null,
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
  job: null,
};

const replacementSnapshot = {
  ...snapshot,
  id: "snap_replacement",
  commit_sha: "replacement123456",
};

const profile = {
  id: "learn_1",
  anonymous_key: "learner-test",
  goal: "understand_whole_project",
  preferred_explanation: ["line_by_line"],
  pace: "careful",
  background: {},
  concept_mastery: {},
  assessment_version: "stack-diagnostic-v1",
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
};

const evidence = {
  file_id: "file_1",
  path: "src/app/page.tsx",
  start_line: 1,
  end_line: 20,
  reason: "첫 화면 근거",
};

const secondEvidence = {
  file_id: "file_2",
  path: "src/app/flow.tsx",
  start_line: 31,
  end_line: 44,
  reason: "두 번째 기능 근거",
};

const projectMap = {
  repository_name: "example/map-demo",
  snapshot_id: snapshot.id,
  commit_sha: snapshot.commit_sha,
  summary: "사용자가 프로젝트의 큰 그림부터 이해하도록 돕는 저장소입니다.",
  summary_confidence: "verified",
  tech_stack: [
    { name: "Next.js", category: "framework", confidence: "verified", evidence: [evidence] },
  ],
  capabilities: [
    {
      id: "project-map",
      name: "프로젝트 지도 보기",
      description: "코드보다 먼저 저장소의 역할을 설명합니다.",
      confidence: "verified",
      evidence: [evidence],
    },
    {
      id: "feature-flow",
      name: "기능 흐름 열기",
      description: "실행 순서와 코드 근거를 연결합니다.",
      confidence: "verified",
      evidence: [secondEvidence],
    },
  ],
  system_areas: [
    {
      id: "interface",
      name: "사용자 화면",
      description: "사용자에게 프로젝트 지도를 보여줍니다.",
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  external_services: [],
  environment_variables: [],
  read_first: [{ ...evidence, confidence: "verified" }],
  limitations: ["런타임 동작은 확인하지 않았습니다."],
};

const assessment = {
  id: "asm_1",
  snapshot_id: snapshot.id,
  learner_profile_id: profile.id,
  status: "active",
  detected_stack: ["Next.js"],
  questions: [],
  answers: {},
  answered_count: 0,
  total_count: 1,
  assessment_version: "stack-diagnostic-v1",
  profile,
  created_at: "2026-07-19T00:00:00Z",
  expires_at: "2026-07-19T00:15:00Z",
  submitted_at: null,
  skipped_at: null,
  timed_out_at: null,
};

const featureFlowCatalog = {
  repository_name: projectMap.repository_name,
  snapshot_id: snapshot.id,
  commit_sha: snapshot.commit_sha,
  analysis_version: "feature-flow-v3",
  flows: [
    {
      id: "flow-project-map",
      title: "프로젝트 지도 조회",
      user_goal: "저장소의 큰 그림을 확인합니다.",
      trigger: "프로젝트 지도 요청",
      outcome: "지도 응답 표시",
      step_count: 1,
      involved_areas: ["API", "Web"],
      confidence: "verified",
      evidence_coverage: 1,
      entry_evidence: evidence,
    },
  ],
  limitations: ["정적 분석 기반입니다."],
};

const featureFlowDetail = {
  id: "flow-project-map",
  title: "프로젝트 지도 조회",
  user_goal: "저장소의 큰 그림을 확인합니다.",
  trigger: "프로젝트 지도 요청",
  outcome: "지도 응답 표시",
  normal_steps: [
    {
      id: "flow-step-1",
      ordinal: 1,
      title: "지도 API 요청 수신",
      role: "user_trigger",
      executes_when: "GET 요청 도착",
      input: "snapshot_id",
      output_or_side_effect: "지도 서비스 호출",
      previous_step_id: null,
      next_step_id: null,
      relation_type: "TRIGGERS",
      confidence: "verified",
      evidence: [evidence],
    },
  ],
  failure_steps: [],
  involved_areas: ["API", "Web"],
  confidence: "verified",
  limitations: ["정적 분석 기반입니다."],
};

const codeExplanation = {
  id: "focus-1",
  snapshot_id: snapshot.id,
  analysis_version: "minimum-sufficient-v1",
  depth: "minimum" as const,
  selection: {
    file_id: evidence.file_id,
    start_line: evidence.start_line,
    end_line: evidence.end_line,
  },
  purpose: "지도 API 요청을 시작합니다.",
  executes_when: "사용자가 지도를 열 때",
  input: "snapshot_id",
  output_or_side_effect: "지도 요청",
  project_role: "화면 경계",
  change_impact: "지도 진입 동작이 달라질 수 있습니다.",
  required_concepts: ["HTTP 요청"],
  related_steps: [],
  syntax_segments: [],
  analogy: null,
  confidence: "verified" as const,
  evidence: [evidence],
  limitations: [],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, reject, resolve };
}

function sourceFile(fileId: string, path = `${fileId}.ts`) {
  return {
    id: fileId,
    snapshot_id: snapshot.id,
    path,
    language: "typescript",
    content: `export const id = "${fileId}";`,
    content_hash: `hash-${fileId}`,
    byte_size: 30,
    line_count: 1,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  mocks.health.mockResolvedValue({ status: "ready", version: "test", checks: {} });
  mocks.listSnapshots.mockResolvedValue([snapshot]);
  mocks.createRepository.mockResolvedValue({
    repository: {
      id: "repo_replacement",
      provider: "github",
      owner: "new-owner",
      name: "new-repository",
      url: "https://github.com/new-owner/new-repository",
      created_at: "2026-07-19T00:00:00Z",
    },
    snapshot: replacementSnapshot,
  });
  mocks.createLearnerProfile.mockResolvedValue(profile);
  mocks.getProjectMap.mockResolvedValue(projectMap);
  const implementationGraph = {
    repository_name: "example/repository",
    snapshot_id: snapshot.id,
    commit_sha: snapshot.commit_sha,
    analysis_version: "architecture-graph-v2",
    summary: "structure",
    groups: [],
    nodes: [],
    edges: [],
    limitations: [],
  };
  mocks.getArchitectureGraph.mockResolvedValue(implementationGraph);
  mocks.getRepositoryStory.mockResolvedValue({
    repository_name: projectMap.repository_name,
    snapshot_id: snapshot.id,
    commit_sha: snapshot.commit_sha,
    analysis_version: "repository-story-v1",
    purpose: {
      one_liner: projectMap.summary,
      primary_audience: "저장소를 이해하려는 사용자",
      primary_outcome: "구조와 기능 흐름을 이해합니다.",
      how_it_works: ["1. 사용자 작업 공간", "2. 구조와 기능 흐름 구성"],
      confidence: "verified",
      evidence: [evidence],
    },
    roles: [
      {
        id: "role-map",
        display_name: "프로젝트 지도 보기",
        role_summary: "저장소의 큰 그림을 보여줍니다.",
        why_it_exists: "코드보다 목적을 먼저 이해하기 위해 필요합니다.",
        contribution_to_goal: "전체 구조를 설명합니다.",
        receives: ["snapshot"],
        produces: ["project map"],
        member_node_ids: ["node-map"],
        member_file_ids: [evidence.file_id],
        capability_ids: ["project-map"],
        feature_flow_ids: ["flow-project-map"],
        confidence: "verified",
        evidence: [evidence],
      },
      {
        id: "role-flow",
        display_name: "기능 흐름 열기",
        role_summary: "실행 흐름을 보여줍니다.",
        why_it_exists: "기능의 순서를 이해하기 위해 필요합니다.",
        contribution_to_goal: "코드 연결을 설명합니다.",
        receives: ["feature"],
        produces: ["flow"],
        member_node_ids: ["node-flow"],
        member_file_ids: [secondEvidence.file_id],
        capability_ids: ["feature-flow"],
        feature_flow_ids: ["flow-project-map"],
        confidence: "verified",
        evidence: [secondEvidence],
      },
    ],
    connections: [],
    features: featureFlowCatalog.flows,
    implementation_graph: implementationGraph,
    limitations: [],
  });
  mocks.getFeatureFlows.mockResolvedValue(featureFlowCatalog);
  mocks.getFeatureFlow.mockResolvedValue(featureFlowDetail);
  mocks.createCodeExplanation.mockResolvedValue(codeExplanation);
  mocks.createChatSession.mockResolvedValue({
    id: "chat_navigation",
    snapshot_id: snapshot.id,
    goal: null,
    preferred_style: "beginner",
    learning_session_id: null,
    navigation_context: {},
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:00Z",
  });
  mocks.getTree.mockResolvedValue([]);
  mocks.getStartHere.mockResolvedValue({
    repository_name: projectMap.repository_name,
    snapshot_id: snapshot.id,
    commit_sha: snapshot.commit_sha,
    summary: projectMap.summary,
    tech_stack: ["Next.js"],
    entry_points: [],
    top_directories: [],
    suggested_goals: [],
  });
  mocks.getGraph.mockResolvedValue({ nodes: [], edges: [] });
  mocks.getFile.mockResolvedValue(sourceFile(evidence.file_id, evidence.path));
  mocks.getSymbols.mockResolvedValue([]);
  mocks.createAssessmentSession.mockResolvedValue(assessment);
});

afterEach(cleanup);

describe("RepositoryWorkbench map-first entry", () => {
  it("keeps polling a stalled analysis and retries it with a new server job", async () => {
    const stalledSnapshot = {
      ...snapshot,
      status: "analyzing",
      job: {
        id: "job-stalled",
        snapshot_id: snapshot.id,
        stage: "embedding",
        status: "running",
        progress_current: 2,
        progress_total: 10,
        error_code: null,
        error_detail: null,
        retry_count: 0,
        runtime_state: "stalled",
        stalled_reason: "progress_timeout",
        created_at: "2026-07-19T00:00:00Z",
        started_at: "2026-07-19T00:00:00Z",
        heartbeat_at: "2026-07-19T00:01:00Z",
        last_progress_at: "2026-07-19T00:01:00Z",
        finished_at: null,
      },
    };
    const retriedSnapshot = {
      ...stalledSnapshot,
      status: "pending",
      job: {
        ...stalledSnapshot.job,
        status: "queued",
        stage: "pending",
        retry_count: 1,
        runtime_state: "queued",
        stalled_reason: null,
      },
    };
    mocks.listSnapshots.mockResolvedValueOnce([stalledSnapshot]);
    mocks.retrySnapshot.mockResolvedValueOnce(retriedSnapshot);

    render(<RepositoryWorkbench />);

    expect(await screen.findByText("분석 정체")).toBeTruthy();
    expect(screen.getByText(/분석 진행이 멈췄습니다/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "분석 다시 시도" }));

    await waitFor(() => expect(mocks.retrySnapshot).toHaveBeenCalledWith(snapshot.id));
    expect(await screen.findByText("대기 중")).toBeTruthy();
  });

  it("shows the persisted failure reason and retries a failed analysis", async () => {
    const failedSnapshot = {
      ...snapshot,
      status: "failed",
      error_message: "Worker terminated before analysis completed.",
      job: {
        id: "job-failed",
        snapshot_id: snapshot.id,
        stage: "embedding",
        status: "failed",
        progress_current: 2,
        progress_total: 10,
        error_code: "worker_killed",
        error_detail: "Worker terminated before analysis completed.",
        retry_count: 0,
        runtime_state: "terminal",
        stalled_reason: null,
        created_at: "2026-07-19T00:00:00Z",
        started_at: "2026-07-19T00:00:00Z",
        heartbeat_at: "2026-07-19T00:01:00Z",
        last_progress_at: "2026-07-19T00:01:00Z",
        finished_at: "2026-07-19T00:02:00Z",
      },
    };
    const retriedSnapshot = {
      ...failedSnapshot,
      status: "pending",
      error_message: null,
      job: {
        ...failedSnapshot.job,
        status: "queued",
        stage: "pending",
        error_code: null,
        error_detail: null,
        retry_count: 1,
        runtime_state: "queued",
        finished_at: null,
      },
    };
    mocks.listSnapshots.mockResolvedValueOnce([failedSnapshot]);
    mocks.retrySnapshot.mockResolvedValueOnce(retriedSnapshot);

    render(<RepositoryWorkbench />);

    expect(await screen.findByText("분석 실패")).toBeTruthy();
    expect(screen.getByText("Worker terminated before analysis completed.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "분석 다시 시도" }));

    await waitFor(() => expect(mocks.retrySnapshot).toHaveBeenCalledWith(snapshot.id));
    expect(await screen.findByText("대기 중")).toBeTruthy();
  });

  it("loads Repository Structure without starting assessment or explorer APIs", async () => {
    render(<RepositoryWorkbench />);

    await waitFor(() =>
      expect(screen.getByTestId("repository-story").textContent).toContain(projectMap.summary),
    );
    expect(mocks.getRepositoryStory).toHaveBeenCalledWith(snapshot.id);
    expect(mocks.createAssessmentSession).not.toHaveBeenCalled();
    expect(mocks.getFeatureFlows).not.toHaveBeenCalled();
    expect(mocks.getTree).not.toHaveBeenCalled();
    expect(mocks.getGraph).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Repository Structure" }).getAttribute("aria-pressed"))
      .toBe("true");
  });

  it("uses the story implementation graph without a second architecture request", async () => {
    render(<RepositoryWorkbench />);

    await waitFor(() => expect(mocks.getRepositoryStory).toHaveBeenCalledWith(snapshot.id));
    await waitFor(() =>
      expect(screen.getByTestId("repository-story").textContent).toContain(projectMap.summary),
    );
    expect(mocks.getArchitectureGraph).not.toHaveBeenCalled();
    expect(mocks.getFeatureFlows).not.toHaveBeenCalled();
    expect(mocks.getTree).not.toHaveBeenCalled();
    expect(mocks.getGraph).not.toHaveBeenCalled();
  });

  it("loads a feature flow from Repository Structure, then opens exact evidence", async () => {
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    fireEvent.click(screen.getByRole("button", { name: /구조도에 표시/ }));
    await waitFor(() =>
      expect(mocks.getFeatureFlow).toHaveBeenCalledWith(snapshot.id, "flow-project-map"),
    );
    expect(mocks.createAssessmentSession).not.toHaveBeenCalled();
    expect(mocks.getTree).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", {
        name: `근거 코드 열기: 프로젝트 지도 보기, ${evidence.path}`,
      }),
    );
    await waitFor(() => expect(mocks.getFile).toHaveBeenCalledWith(snapshot.id, evidence.file_id));
    expect(mocks.getSymbols).toHaveBeenCalledWith(snapshot.id, evidence.file_id);
    expect(screen.getByTestId("opened-highlight").textContent).toBe(
      `${evidence.start_line}-${evidence.end_line}`,
    );
    expect(screen.getByRole("button", { name: "원본 코드 탐색" }).className).toContain(
      "is-active",
    );
    await waitFor(() =>
      expect(mocks.createCodeExplanation).toHaveBeenCalledWith(
        snapshot.id,
        {
          file_id: evidence.file_id,
          start_line: evidence.start_line,
          end_line: evidence.end_line,
        },
        "minimum",
        undefined,
      ),
    );
    expect(screen.getByTestId("code-focus-state").textContent).toBe(
      codeExplanation.purpose,
    );
  });

  it("does not restore stale feature detail after leaving Repository Structure", async () => {
    const pendingDetail = deferred<typeof featureFlowDetail>();
    mocks.getFeatureFlow.mockReturnValueOnce(pendingDetail.promise);
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    fireEvent.click(screen.getByRole("button", { name: /구조도에 표시/ }));
    await waitFor(() =>
      expect(mocks.getFeatureFlow).toHaveBeenCalledWith(snapshot.id, "flow-project-map"),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "원본 코드 탐색" })[0]);
    await waitFor(() => expect(screen.queryByTestId("repository-story")).toBeNull());

    await act(async () => {
      pendingDetail.resolve(featureFlowDetail);
      await pendingDetail.promise;
    });
    expect(screen.queryByTestId("repository-story")).toBeNull();
  });

  it("opens Project Map evidence with its exact line range", async () => {
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    fireEvent.click(
      screen.getByRole("button", {
        name: "근거 코드 열기: 프로젝트 지도 보기, src/app/page.tsx",
      }),
    );

    await waitFor(() => expect(mocks.getFile).toHaveBeenCalledWith(snapshot.id, evidence.file_id));
    expect(screen.getByTestId("opened-highlight").textContent).toBe(
      `${evidence.start_line}-${evidence.end_line}`,
    );
  });

  it("starts a navigation Change Brief with the current evidence context", async () => {
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");
    fireEvent.click(
      screen.getByRole("button", {
        name: "근거 코드 열기: 프로젝트 지도 보기, src/app/page.tsx",
      }),
    );
    await waitFor(() => expect(mocks.createCodeExplanation).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "변경 영향" }));
    expect(screen.getByTestId("change-brief-selection").textContent).toBe(evidence.file_id);
    fireEvent.click(screen.getByRole("button", { name: "변경 요청 테스트" }));

    await waitFor(() =>
      expect(mocks.startDeepTask).toHaveBeenCalledWith(
        "chat_navigation",
        expect.objectContaining({
          kind: "impact_analysis",
          prompt: "이 동작을 바꾸고 싶어요",
          selection: {
            file_id: evidence.file_id,
            start_line: evidence.start_line,
            end_line: evidence.end_line,
          },
          navigation_context: expect.objectContaining({
            selection: {
              file_id: evidence.file_id,
              start_line: evidence.start_line,
              end_line: evidence.end_line,
            },
          }),
        }),
      ),
    );
  });

  it("keeps the latest evidence result when file requests resolve in reverse order", async () => {
    const slowFile = deferred<ReturnType<typeof sourceFile>>();
    const latestFile = deferred<ReturnType<typeof sourceFile>>();
    mocks.getFile.mockImplementation((_snapshotId: string, fileId: string) => {
      if (fileId === evidence.file_id) return slowFile.promise;
      if (fileId === secondEvidence.file_id) return latestFile.promise;
      return Promise.resolve(sourceFile(fileId));
    });
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    const slowEvidenceButton = screen.getByRole("button", {
      name: "근거 코드 열기: 프로젝트 지도 보기, src/app/page.tsx",
    });
    const latestEvidenceButton = screen.getByRole("button", {
      name: "근거 코드 열기: 기능 흐름 열기, src/app/flow.tsx",
    });
    await act(async () => {
      slowEvidenceButton.click();
      latestEvidenceButton.click();
    });

    await act(async () => {
      latestFile.resolve(sourceFile(secondEvidence.file_id, secondEvidence.path));
      await latestFile.promise;
    });
    expect(screen.getByTestId("opened-file").textContent).toBe(secondEvidence.file_id);
    expect(screen.getByTestId("opened-highlight").textContent).toBe(
      `${secondEvidence.start_line}-${secondEvidence.end_line}`,
    );
    expect(screen.getByTestId("file-loading").textContent).toBe("idle");

    await act(async () => {
      slowFile.resolve(sourceFile(evidence.file_id, evidence.path));
      await slowFile.promise;
    });
    expect(screen.getByTestId("opened-file").textContent).toBe(secondEvidence.file_id);
    expect(screen.getByTestId("opened-highlight").textContent).toBe(
      `${secondEvidence.start_line}-${secondEvidence.end_line}`,
    );
    expect(screen.getByTestId("file-loading").textContent).toBe("idle");
  });

  it("keeps the latest Code Focus explanation when requests resolve in reverse order", async () => {
    const slowExplanation = deferred<typeof codeExplanation>();
    const latestExplanation = deferred<typeof codeExplanation>();
    mocks.createCodeExplanation.mockImplementation(
      (_snapshotId: string, selection: { file_id: string }) => {
        if (selection.file_id === evidence.file_id) return slowExplanation.promise;
        return latestExplanation.promise;
      },
    );
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    await act(async () => {
      screen.getByRole("button", {
        name: "근거 코드 열기: 프로젝트 지도 보기, src/app/page.tsx",
      }).click();
      screen.getByRole("button", {
        name: "근거 코드 열기: 기능 흐름 열기, src/app/flow.tsx",
      }).click();
    });

    const latestResult = {
      ...codeExplanation,
      id: "focus-latest",
      purpose: "최신 선택 범위를 설명합니다.",
      selection: {
        file_id: secondEvidence.file_id,
        start_line: secondEvidence.start_line,
        end_line: secondEvidence.end_line,
      },
      evidence: [secondEvidence],
    };
    await act(async () => {
      latestExplanation.resolve(latestResult);
      await latestExplanation.promise;
    });
    expect(screen.getByTestId("code-focus-state").textContent).toBe(latestResult.purpose);

    await act(async () => {
      slowExplanation.resolve(codeExplanation);
      await slowExplanation.promise;
    });
    expect(screen.getByTestId("code-focus-state").textContent).toBe(latestResult.purpose);
  });

  it("does not restore a stale file after repository state is reset", async () => {
    const staleFile = deferred<ReturnType<typeof sourceFile>>();
    mocks.getFile.mockReturnValueOnce(staleFile.promise);
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    fireEvent.click(
      screen.getByRole("button", {
        name: "근거 코드 열기: 프로젝트 지도 보기, src/app/page.tsx",
      }),
    );
    await waitFor(() => expect(mocks.getFile).toHaveBeenCalledWith(snapshot.id, evidence.file_id));

    const repositoryInput = screen.getByLabelText("GitHub repository URL");
    fireEvent.change(repositoryInput, {
      target: { value: "https://github.com/new-owner/new-repository" },
    });
    fireEvent.submit(repositoryInput.closest("form") as HTMLFormElement);
    await waitFor(() =>
      expect(mocks.createRepository).toHaveBeenCalledWith(
        "https://github.com/new-owner/new-repository",
        "",
      ),
    );
    await waitFor(() =>
      expect(mocks.getRepositoryStory).toHaveBeenCalledWith(replacementSnapshot.id),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "원본 코드 탐색" })[0]);
    expect((await screen.findByTestId("opened-file")).textContent).toBe("none");
    expect(screen.getByTestId("file-loading").textContent).toBe("idle");

    await act(async () => {
      staleFile.resolve(sourceFile(evidence.file_id, evidence.path));
      await staleFile.promise;
    });
    expect(screen.getByTestId("opened-file").textContent).toBe("none");
    expect(screen.getByTestId("opened-highlight").textContent).toBe("none");
    expect(screen.getByTestId("file-loading").textContent).toBe("idle");
  });

  it("loads explorer data without assessment when the user opens original code", async () => {
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    fireEvent.click(screen.getAllByRole("button", { name: "원본 코드 탐색" })[0]);

    await waitFor(() => expect(mocks.getTree).toHaveBeenCalledWith(snapshot.id));
    expect(mocks.getStartHere).toHaveBeenCalledWith(snapshot.id);
    expect(mocks.getGraph).toHaveBeenCalledWith(snapshot.id);
    expect(mocks.createAssessmentSession).not.toHaveBeenCalled();
  });

  it("creates assessment only after the user explicitly starts learning", async () => {
    render(<RepositoryWorkbench />);
    await screen.findByText("프로젝트 지도 보기");

    fireEvent.click(screen.getByRole("button", { name: "깊이 배우기 선택" }));

    await waitFor(() =>
      expect(mocks.createAssessmentSession).toHaveBeenCalledWith(snapshot.id, profile.id),
    );
    expect(mocks.getTree).toHaveBeenCalledWith(snapshot.id);
    expect(mocks.getGraph).toHaveBeenCalledWith(snapshot.id);
  });
});
