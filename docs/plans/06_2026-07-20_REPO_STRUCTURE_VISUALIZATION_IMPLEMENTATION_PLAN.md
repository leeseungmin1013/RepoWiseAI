# RepoWiseAI Repository Structure Visualization 구현 계획

- 작성일: 2026-07-20
- 선행 기준선: Navigation Reform Phase 1~4 완료 (`semantic-ts-v2`)
- 목표: 파일 import 목록이 아니라 저장소의 책임 경계와 기능 실행 흐름을 한 화면에서 이해할 수 있는 구조 시각화 제공
- 참고 설계: GitDiagram의 bounded graph AST, 검증, 그룹화, 결정론적 렌더링 패턴

## 구현 상태 (2026-07-30)

Phase 5A~5E와 실측 결과에 따른 관계 확장, Phase 6 선택 기능까지 구현했다.

- `architecture-graph-v2` Pydantic 계약과 version 상수
- Project Map, Semantic Graph, Feature Flow를 결합하는 결정론적 builder
- Python/FastAPI AST, DB SDK read/write, explicit raise, local fetch wrapper, cross-file helper 관계
- ID, evidence, graph size, feature mapping 검증기
- versioned `NavigationArtifact` cache와 `GET /architecture-graph` API
- old parser 거부, cache fallback, feature flag
- ELK 기반 React Flow 구조도와 deterministic fallback layout
- group, 책임 node, 의미 edge, inspector, evidence code jump
- 정상·실패 Feature Flow 오버레이
- UI가 없는 라이브러리 저장소의 public API 실행 흐름
- Change Brief direct·possible impact 표시와 변경 검토 진입
- architecture gold 평가 CLI와 recall·precision·noise·evidence·size 지표
- RepoWiseAI 및 p-map 사람 검수 gold fixture
- PNG·Mermaid export, commit 간 architecture diff
- 기존 node ID만 선택할 수 있는 제한형 AI label 개선(feature flag 기본 off)
- API 및 Web 단위·통합 테스트

대표 저장소 실측:

- RepoWiseAI snapshot `snap_45a90b131a54472fa4d5a5261bf44282`, commit `dd13096`
- p-map snapshot `snap_7d5acb76705d4152af471da029c53d06`, commit `bc26cf0`
- RepoWiseAI architecture: node recall `1.00`, verified precision `1.00`, required edge recall `0.875`, feature mapping `1.00`, noise `0.0455`, evidence `1.00`
- p-map architecture: node recall `1.00`, verified precision `1.00`, required edge recall `1.00`, feature mapping `1.00`, noise `0.00`, evidence `1.00`
- 두 저장소 Navigation gold: feature recall `1.00`, step recall `1.00`, verified precision `1.00`
- RepoWiseAI Change Brief: Web→API→queue/model 후보와 direct `WRITES/RAISES`, possible `CALLS/READS` 확인
- p-map Change Brief: public API 내부 호출과 명시적 실패 경로, medium risk 검수

최종 회귀 검사는 branch/commit 전 최신 변경 전체를 대상으로 다시 실행한다.

## 1. 현재 기준선

완료된 기능은 새 시각화의 입력 데이터로 재사용한다.

| 기존 기능 | 시각화에서의 역할 |
| --- | --- |
| Project Map v2 | 저장소 요약, capability, system area, external service 후보 |
| Semantic Graph v2 | `TRIGGERS`, `REQUESTS`, `HANDLED_BY`, `READS`, `WRITES`, `NAVIGATES_TO`, `USES_EXTERNAL`, `IMPORTS`, `CALLS` 근거 |
| Feature Flow v2 | 기능별 정상·실패 경로 오버레이 |
| Code Focus | 선택한 노드·edge·flow step의 최소 충분 설명 |
| Change Brief | 선택한 구조 범위의 변경 영향 표시 |
| NavigationArtifact | commit·version 기반 구조도 캐시 |
| Navigation evaluator | 실제 저장소 gold 기반 품질 게이트 확장 기반 |

기존 `GET /snapshots/{snapshot_id}/graph`와 `DependencyGraph.tsx`는 최대 300개의 import 관계를 파일 단위로 표현하고 고정 격자에 배치한다. 이 화면은 삭제하지 않고 `원시 의존성` 고급 보기로 이동한다.

## 2. 제품 목표

사용자는 구조도에서 다음 질문에 답할 수 있어야 한다.

1. 이 저장소는 어떤 시스템 영역으로 나뉘는가?
2. 각 영역과 주요 컴포넌트는 무슨 책임을 갖는가?
3. 특정 기능은 어떤 컴포넌트와 파일을 어떤 순서로 통과하는가?
4. 선택한 노드나 관계의 설명은 어떤 코드에서 검증되는가?
5. 이 부분을 변경하면 직접·간접적으로 무엇이 영향을 받는가?

기본 화면의 정보 제한은 다음과 같이 둔다.

- 그룹 권장 3~6개, 최대 8개
- 노드 권장 12~22개, 최대 34개
- edge 권장 8~30개, 최대 48개
- 기능 흐름 정상 경로 최대 7단계
- 노드 본문은 이름, 한 줄 책임, 유형, confidence만 표시
- 상세 설명과 근거는 inspector에서 표시

## 3. 사용자 경험

### 3.1 통합 Structure Map 화면

Project Map 기본 화면에 구조 시각화 진입점을 추가하고, 최종적으로는 동일 화면 안에서 다음 보기 모드를 전환한다.

```text
[전체 구조] [기능 흐름] [원시 의존성]

┌──────────────────────── Structure Canvas ────────────────────────┬──────── Inspector ────────┐
│ 시스템 그룹, 책임 노드, 의미 edge                               │ 선택 대상 설명             │
│ pan / zoom / fit / group collapse                               │ 입력·출력·부작용            │
│ 기능 선택 시 관련 경로 강조                                     │ 관련 기능·관계               │
│                                                                 │ confidence·limitations      │
│                                                                 │ 코드 근거 열기              │
└─────────────────────────────────────────────────────────────────┴────────────────────────────┘
```

### 3.2 전체 구조 모드

- 브라우저, 서버, 도메인, 데이터, 외부 서비스, 설정 등 책임 경계로 그룹화한다.
- 파일명보다 `Repository Workbench`, `Navigation API`, `Feature Flow Builder` 같은 역할명을 우선한다.
- 노드 선택 시 직전·직후 관계만 강조하고 나머지를 흐리게 한다.
- edge 선택 시 관계 의미와 양쪽 코드 근거를 inspector에 표시한다.
- `verified`, `inferred`, `unknown`을 색뿐 아니라 badge와 선 스타일로 구분한다.

### 3.3 기능 흐름 모드

- 기존 Feature Flow catalog에서 기능을 선택한다.
- 선택된 `normal_steps`를 구조도 위에 1~7 번호로 표시한다.
- 관련 없는 노드와 edge는 흐리게 처리한다.
- 정상 경로와 failure path를 토글한다.
- step 선택 시 `executes_when`, `input`, `output_or_side_effect`, evidence를 표시한다.
- evidence 선택 시 explorer로 이동하고 정확한 라인을 강조한다.

### 3.4 변경 영향 모드 연동

초기 버전에서는 별도 모드를 추가하지 않고 기존 Change Brief로 연결한다.

- 노드 inspector의 `이 영역 변경 검토` 버튼으로 대표 evidence를 selection으로 전달한다.
- Change Brief 완료 후 confirmed direct impact에 해당하는 노드를 강조한다.
- possible impact는 점선 또는 경고 outline으로 표시한다.
- unknown boundary는 그래프 바깥쪽 warning panel에 표시한다.

## 4. 데이터 계약

기존 `GraphResponse`를 변경하지 않고 새 계약을 추가한다.

```python
ArchitectureConfidence = Literal["verified", "inferred", "unknown"]
ArchitectureLayer = Literal[
    "client", "server", "domain", "data", "external", "configuration", "shared"
]

class ArchitectureGraphEvidence(BaseModel):
    file_id: str
    path: str
    start_line: int
    end_line: int
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
    group_id: str | None
    confidence: ArchitectureConfidence
    inputs: list[str]
    outputs: list[str]
    capability_ids: list[str]
    feature_flow_ids: list[str]
    evidence: list[ArchitectureGraphEvidence]

class ArchitectureGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    label: str
    description: str
    confidence: ArchitectureConfidence
    feature_flow_ids: list[str]
    evidence: list[ArchitectureGraphEvidence]

class ArchitectureGraphResponse(BaseModel):
    repository_name: str
    snapshot_id: str
    commit_sha: str
    analysis_version: str
    summary: str
    groups: list[ArchitectureGraphGroup]
    nodes: list[ArchitectureGraphNode]
    edges: list[ArchitectureGraphEdge]
    limitations: list[str]
```

현재 버전 상수는 `ARCHITECTURE_GRAPH_VERSION = "architecture-graph-v2"`다.

artifact 계약:

- `artifact_type`: `architecture_graph`
- `artifact_key`: `overview`
- `artifact_version`: `architecture-graph-v2`
- cache identity: snapshot ID + commit SHA + artifact version
- generation metadata에 semantic graph, project map, feature flow 버전을 함께 기록

## 5. 생성 파이프라인

### 5.1 v1은 결정론적으로 생성

첫 배포에서는 LLM을 필수로 사용하지 않는다. 실저장소 gold 측정이 끝나기 전에 모델 기반 추상화를 넣으면 semantic relation 품질과 요약 품질을 분리해 평가하기 어렵기 때문이다.

```text
FileRecord / Symbol / SymbolEdge
          +
ProjectMap capability / system area
          +
FeatureFlow catalog / detail
          ↓
Architecture candidates
          ↓
importance scoring + grouping + deduplication
          ↓
bounded graph validation
          ↓
ArchitectureGraph NavigationArtifact
```

### 5.2 후보 생성 규칙

노드 후보 우선순위:

1. Feature Flow에 포함된 client handler, request, server handler, effect target
2. Project Map capability의 대표 evidence
3. entry point, page, route, service, model, repository
4. 여러 중요 노드를 연결하는 cross-file helper
5. 외부 서비스와 데이터 저장소

제외 또는 축약:

- test, fixture, story, generated file
- leaf utility와 단일 소비자 helper
- framework config는 구조적으로 중요할 때만 포함
- 동일 디렉터리·동일 책임의 반복 노드는 하나의 책임 노드로 병합
- 외부 package는 서비스 단위로 병합

중요도 점수 예시:

```text
feature flow 등장 횟수             +4
Project Map capability evidence    +3
entry point / route                +3
semantic in/out degree             +0~3
external or persistent boundary    +2
test/generated/leaf                -5
```

### 5.3 그룹 생성

Project Map system area를 seed로 사용하되, 파일 경로만으로 그룹을 결정하지 않는다.

- `client`: page, component, hook, browser event
- `server`: route, controller, worker, queue consumer
- `domain`: feature builder, analysis, orchestration
- `data`: model, schema, repository, database client
- `external`: GitHub, OpenAI, storage, mail, payment 등
- `configuration`: runtime configuration이 구조의 일부일 때만
- `shared`: 공통 타입·유틸이 실제 경계 역할을 할 때만

빈 그룹과 노드가 하나뿐이며 의미 없는 그룹은 제거한다.

### 5.4 edge 축약

원시 `IMPORTS`는 그대로 Architecture Graph에 넣지 않는다.

- `TRIGGERS`, `REQUESTS`, `HANDLED_BY`, effect relation을 최우선 사용
- 여러 symbol edge가 동일 architecture node 쌍을 연결하면 하나로 병합
- `IMPORTS`와 `CALLS`는 다른 의미 관계를 보완하거나 고립 노드를 연결할 때만 사용
- 동일 source/target/relation edge를 deduplicate
- 양방향 import는 필요하면 `depends_on` 하나로 축약
- self edge 제거

### 5.5 검증기

`architecture_graph.py`와 별도로 `architecture_validation.py`를 둔다.

필수 검증:

- group/node ID 형식과 중복
- node의 group 존재 여부
- edge endpoint 존재 여부
- evidence file ID, path, line 범위 일치
- capability ID와 feature flow ID 존재 여부
- 노드와 edge 상한
- self edge와 중복 edge
- 고립 노드 비율
- 모든 verified item의 evidence 존재
- 각 선택 가능 Feature Flow의 step 중 구조도에 매핑되는 비율

검증 실패는 API 500보다 artifact cache miss와 limitations로 안전하게 처리한다. 계약 자체가 깨진 경우에만 생성 실패로 본다.

## 6. API 계획

새 endpoint:

```http
GET /api/snapshots/{snapshot_id}/architecture-graph
GET /api/snapshots/{snapshot_id}/architecture-graph?feature_flow_id={flow_id}
```

권장 동작:

- 기본 endpoint는 전체 graph와 각 노드의 `feature_flow_ids`를 반환한다.
- query가 있더라도 별도 graph를 생성하지 않고 동일 artifact를 필터링한다.
- 존재하지 않는 flow ID는 `404`.
- snapshot이 ready가 아니면 `409`.
- parser가 `semantic-ts-v2`가 아니면 `409` 또는 명시적 reanalysis-required 응답을 사용한다.
- `X-Navigation-Artifact-Version` 헤더를 유지한다.
- artifact cache read/write 실패 시 결정론적 builder 결과로 fallback한다.

예상 파일:

- `apps/api/app/navigation/architecture_graph.py`
- `apps/api/app/navigation/architecture_validation.py`
- `apps/api/app/navigation/versions.py`
- `apps/api/app/schemas.py`
- `apps/api/app/api/repositories.py`
- `apps/api/tests/test_architecture_graph.py`
- `apps/api/tests/test_architecture_graph_api.py`

## 7. Web 구현 계획

### 7.1 렌더러

현재 `@xyflow/react`를 유지하고 `elkjs`를 추가한다. Mermaid는 렌더링 엔진이 아니라 후속 export 포맷으로만 검토한다.

구성:

- `ArchitectureMapPanel.tsx`: 데이터 로딩 상태와 화면 orchestration
- `ArchitectureCanvas.tsx`: React Flow canvas
- `ArchitectureNode.tsx`: custom node
- `ArchitectureInspector.tsx`: node, edge, flow step 상세
- `architecture-layout.ts`: ELK 입력 변환과 위치 계산
- `architecture-selection.ts`: focus, dimming, flow overlay 계산
- CSS module과 component test

ELK 기본 설정:

- direction: `RIGHT`
- algorithm: `layered`
- group별 compound node 사용
- spacing은 node 간 48px 이상, layer 간 80px 이상
- layout 결과는 `(graph version, node IDs, edge IDs)` 기준으로 memoize
- layout 실패 시 단순 계층형 fallback 제공

### 7.2 Workbench 통합

초기에는 `WorkspaceMode = "map"`을 유지하고 Project Map 내부에 `요약 / 구조도` segment를 둔다. 별도의 최상위 workspace mode를 즉시 추가하면 이미 5개인 navigation 항목이 더 복잡해진다.

상태:

```ts
type MapView = "summary" | "structure";
type StructureMode = "overview" | "feature" | "dependency";
```

- Project Map capability 클릭 시 structure view로 이동하고 관련 노드를 강조할 수 있다.
- Feature Flow 상세에서 `구조도에서 보기`를 누르면 map/structure/feature로 이동한다.
- inspector evidence는 기존 `openMapEvidence`, `openFeatureFlowEvidence` 경로를 재사용한다.
- 원시 dependency 모드는 기존 `DependencyGraph`를 재사용하되 explorer 내부의 고급 보기로 유지한다.

### 7.3 접근성 및 모바일

- 색상만으로 confidence와 선택 상태를 구분하지 않는다.
- 노드와 inspector를 키보드로 이동할 수 있게 한다.
- `aria-label`에 책임과 confidence를 포함한다.
- 모바일에서는 canvas와 inspector를 동시에 좁게 표시하지 않고 `구조 / 설명` 탭으로 전환한다.
- reduced motion에서는 flow edge animation을 비활성화한다.

## 8. 단계별 구현 순서

### Phase 5A — 운영 기준선과 구조도 gold 설계

선행 작업:

1. Worker를 현재 코드로 재시작한다.
2. 대표 저장소를 `semantic-ts-v2`로 재분석한다.
3. 기존 Feature Flow·Change Brief gold 검수를 완료한다.
4. parser relation 확장은 측정 결과가 요구할 때만 수행한다.

병행 가능한 구조도 작업:

- Architecture Graph schema 초안
- fixture 포맷
- graph validation unit test
- mock 데이터 기반 Web renderer prototype

종료 조건:

- 대표 저장소와 snapshot ID가 고정됨
- 기존 navigation recall·precision baseline이 기록됨
- 구조도 gold에서 기대 group, node responsibility, 주요 edge, feature mapping을 표현할 수 있음

### Phase 5B — Architecture Graph backend vertical slice

- 결정론적 builder
- validator
- versioned NavigationArtifact
- GET endpoint
- cache hit/miss/stale/old-parser 테스트
- RepoWiseAI 자체 저장소 fixture로 응답 검수

종료 조건:

- 34개 이하 노드와 48개 이하 edge 보장
- 모든 verified node/edge가 유효한 evidence를 가짐
- 동일 snapshot에서 byte-equivalent한 안정적 결과 생성
- cache 장애 시 정상 fallback

### Phase 5C — 전체 구조 UI

- ELK layout
- group·node·edge custom rendering
- inspector
- evidence code jump
- selection focus와 검색
- loading/empty/error/reanalysis-required 상태
- responsive 및 접근성 테스트

종료 조건:

- 주요 구조가 초기 fit view에서 읽힘
- 노드 선택 후 1회 클릭으로 evidence 확인
- 22개 노드 fixture에서 label overlap과 canvas overflow 없음
- layout 결과가 입력 순서에 따라 흔들리지 않음

### Phase 5D — Feature Flow 오버레이

- catalog 선택과 graph mapping
- normal/failure path 토글
- step 번호와 방향 강조
- step inspector
- Feature Flow Panel과 deep link
- flow mapping coverage 표시

종료 조건:

- 대표 기능의 정상 경로가 5~7단계 내에서 추적됨
- 선택된 step이 실제 file·line으로 이동함
- 매핑되지 않은 step을 숨기지 않고 limitation으로 표시

### Phase 5E — Change Brief 연동과 품질 게이트

- node에서 Change Brief 시작
- 결과의 direct/possible impact를 graph node에 투영
- architecture graph evaluator 추가
- 대표 저장소 UX 검수
- feature flag rollout

종료 조건:

- 직접 영향과 추정 영향을 시각적으로 구분
- gold 기준 주요 node/edge recall과 verified precision 통과
- 기존 Project Map, Feature Flow, explorer 회귀 없음

### Phase 6 — 제한형 LLM 보강과 export

실저장소 평가 통과 후 구현했다.

- Structured Outputs로 책임 노드 병합과 label 개선
- 모델이 evidence나 edge를 새로 만들지 못하도록 candidate ID 선택 방식 사용
- validator feedback 기반 제한적 repair
- PNG export
- Mermaid source export
- commit 간 architecture diff

## 9. 평가 계획

기존 navigation evaluator에 별도 architecture fixture를 추가한다.

gold 항목:

- expected groups
- expected responsibility nodes와 허용 가능한 evidence path
- required semantic edges
- forbidden nodes 또는 noise path
- feature flow별 expected node sequence

지표:

| 지표 | 의미 | 초기 목표 |
| --- | --- | --- |
| architecture node recall | 필수 책임 노드 발견률 | 0.80 이상 |
| verified node precision | verified 노드 중 gold 일치 비율 | 0.95 이상 |
| required edge recall | 주요 시스템 관계 발견률 | 0.75 이상 |
| evidence validity | 존재하는 path·line 근거 비율 | 1.00 |
| feature mapping coverage | flow step의 graph 매핑 비율 | 0.85 이상 |
| noise ratio | 불필요한 leaf node 비율 | 0.15 이하 |
| graph size compliance | 상한 준수 | 1.00 |

정성 검수 질문:

1. 30초 안에 저장소의 주요 경계를 말할 수 있는가?
2. 기능 하나가 client에서 server와 data까지 이동하는 경로를 설명할 수 있는가?
3. 노드 이름이 파일명이 아니라 책임을 표현하는가?
4. 그래프가 틀렸을 때 어떤 부분이 추정인지 알 수 있는가?
5. 코드 근거까지 이동하는 데 2회 이상의 탐색이 필요한가?

## 10. 테스트 계획

API:

- candidate grouping과 stable ID
- edge aggregation과 deduplication
- node/edge/group 상한
- invalid evidence 제거
- old parser version 처리
- artifact cache hit, corrupt payload, stale commit, DB failure fallback
- feature_flow_ids mapping
- deterministic ordering

Web:

- API 타입과 fetch
- ELK adapter와 fallback layout
- node/edge selection
- capability filter
- normal/failure overlay
- evidence callback
- mobile structure/inspector tab
- empty, loading, error, reanalysis-required 상태
- large fixture의 bounded render

회귀 게이트:

```text
API Ruff
API pytest
Web Vitest
Web TypeScript
Web ESLint
Next.js production build
git diff --check
navigation gold evaluator
architecture graph evaluator
```

## 11. Feature flag와 rollout

환경 변수:

```dotenv
NAVIGATION_ARCHITECTURE_GRAPH_ENABLED=false
NEXT_PUBLIC_ARCHITECTURE_GRAPH_ENABLED=false
```

rollout:

1. 개발 환경에서 RepoWiseAI 자체 저장소로 dogfood
2. 대표 저장소 gold 검수
3. 기존 Project Map의 보조 탭으로 노출
4. 지표 통과 후 기본 Project Map 화면의 주요 진입점으로 승격
5. 안정화 후 원시 dependency graph를 고급 보기로 이동

## 12. 위험과 대응

| 위험 | 대응 |
| --- | --- |
| semantic relation 누락으로 구조가 끊김 | inferred edge를 만들기보다 limitation 표시, gold 결과에 따라 parser 확장 |
| 파일 수가 많을수록 노드가 폭증 | candidate score, 책임 병합, hard limit, leaf 제거 |
| Project Map과 구조도의 명칭 불일치 | capability ID와 system area ID를 canonical key로 사용 |
| Feature Flow step이 graph node에 매핑되지 않음 | evidence file/symbol 기반 mapping coverage와 unmapped step 표시 |
| 자동 레이아웃이 불안정 | stable sorting, layout version, deterministic fallback |
| 설명이 캔버스를 다시 복잡하게 함 | 한 줄 책임만 노드에 표시하고 나머지는 inspector로 이동 |
| LLM 환각 | v1 결정론적 생성, 후속 LLM은 candidate 선택·label 개선만 허용 |

## 13. 권장 PR 분할

1. `architecture graph schema + validator + fixtures`
2. `deterministic architecture graph builder + artifact API`
3. `architecture canvas + ELK layout + inspector`
4. `feature flow overlay + evidence navigation`
5. `change brief projection + evaluator + rollout flags`

각 PR은 독립적으로 테스트 가능해야 하며 기존 `/graph`, Project Map, Feature Flow 계약을 깨지 않는다.

## 14. 즉시 다음 작업

1. 운영 Worker 재시작과 대표 저장소 재분석을 먼저 수행해 Phase 1~4 기준선을 확보한다.
2. 동시에 Phase 5A의 Architecture Graph schema와 gold fixture 포맷을 코드 없이 검토한다.
3. 실저장소 navigation 측정 결과를 기록한 뒤 Phase 5B를 시작한다.
4. DB SDK, `Link`, cross-file helper 관계 확장은 구조도 구현 전에 일괄 추가하지 않고 실제 recall 실패 사례를 근거로 추가한다.
5. 기본 구조도는 결정론적으로 생성하고, candidate-constrained LLM 라벨 개선은 server/client feature flag가 모두 켜진 경우에만 선택적으로 사용한다.
