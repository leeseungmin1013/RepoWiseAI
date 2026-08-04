# RepoWiseAI Repository Structure First UI 개편 계획

- 작성일: 2026-07-30
- 최종 업데이트: 2026-07-30
- 상태: 구현 완료 — 자동 테스트·실저장소 story gate 통과, 수동 사용자 이해도 검수만 운영 단계로 이관
- 선행 구현: `architecture-graph-v2`, `feature-flow-v3`, Project Map, Code Focus, Change Brief, DeepTask
- 관련 문서: [`06_2026-07-20_REPO_STRUCTURE_VISUALIZATION_IMPLEMENTATION_PLAN.md`](06_2026-07-20_REPO_STRUCTURE_VISUALIZATION_IMPLEMENTATION_PLAN.md)
- 제품 방향: Repository Structure를 메인 경험으로 승격하고, 나머지 기능을 구조도 문맥에 연결한다.

## 0. 구현 결과

| 범위 | 결과 |
| --- | --- |
| Phase A — UI 안정화 | document scroll 복구, sticky header/nav, toolbar wrapping, responsive canvas/inspector, mobile bottom sheet, 낮은 높이 breakpoint 구현 |
| Phase B — Repository Story backend | `repository-story-v1` schema·builder·validator·cache API·evaluator·gold fixture 구현 |
| Phase C — Structure-first main | 분석 완료 기본 화면을 Purpose + Role Graph + 설명 inspector로 전환, 역할/구현 단계 보기 구현 |
| Phase D — 보조 기능 부착 | Feature Flow overlay, evidence/Code Focus, Change Brief, 학습, 고급 코드 탐색을 구조도 선택 문맥에 연결 |
| Phase E — 반응형·접근성 | 44px mobile target, keyboard role activation, screen reader label, reduced motion, 색 외 confidence/impact 표식 구현 |
| Phase F — 실저장소 gate | RepoWiseAI와 p-map semantic-ts-v2 snapshot 평가 통과 |

자동 검증 결과:

- API: `131 passed`
- Web: `102 passed`
- API/Web lint: 통과
- TypeScript: 통과
- Next.js production build: 통과
- RepoWiseAI story: 9 roles, 17 connections, 3 features
- p-map story: 3 roles, 3 features
- 두 gold fixture 모두 role recall·verified precision·evidence validity·feature mapping·narrative coverage `1.0`
- generic responsibility ratio `0.0`

검증 환경 메모:

- localhost API와 Worker를 새 코드로 재시작했고 API/DB/queue health를 확인했다.
- 인앱 브라우저 자동화 연결은 Codex 브라우저 런타임의 kernel asset 경로 오류로 실행되지 않았다. 따라서 실제 viewport 육안 검수와 사람 이해도 평가는 배포 전 운영 체크리스트로 남긴다.

## 1. 결론

이번 개편은 기존 화면에 구조도 탭을 더 크게 붙이는 작업이 아니다.

분석 완료 후 첫 화면을 다음 질문에 답하는 하나의 `Repository Story` 화면으로 바꾼다.

1. 이 저장소는 누구를 위해 무엇을 하는가?
2. 그 목적을 달성하려고 어떤 책임 영역들이 협업하는가?
3. 각 영역은 전체 목적에 어떤 방식으로 기여하는가?
4. 실제 기능 하나를 실행하면 어떤 순서로 움직이는가?
5. 더 자세히 알고 싶거나 변경하려면 어디에서 시작해야 하는가?

기본 그래프는 현재처럼 파일 20여 개를 직접 보여주지 않는다. 먼저 6~10개의 제품·시스템 역할을 보여주고, 사용자가 선택했을 때만 실제 모듈과 파일을 펼친다.

Code Focus, Feature Flow, Change Brief, 학습, 원본 코드는 독립된 최상위 화면이 아니라 선택한 구조 요소를 더 이해하거나 활용하는 보조 도구가 된다.

## 2. 현재 구현 진단

### 2.1 UI 잘림과 스크롤 문제

현재 레이아웃은 데스크톱 IDE 형태를 기준으로 만들어져 일반 웹페이지와 다른 스크롤 규칙을 갖는다.

| 현재 구조 | 발생 가능한 문제 |
| --- | --- |
| `body { overflow: hidden }` | 페이지 내용이 viewport보다 길어져도 document scroll이 생기지 않는다. |
| `.app-shell { height: 100dvh; overflow: hidden }` | 헤더, 저장소 입력, 모드 탭, 그래프 높이의 합이 화면을 넘으면 아래쪽이 잘린다. |
| 구조도 panel의 `minmax(560px, 1fr)` | 높이가 작은 노트북 화면에서 toolbar와 footer를 포함해 viewport를 초과한다. |
| panel과 canvas 모두 `overflow: hidden` | 잘린 control을 사용자가 스크롤로 복구할 수 없다. |
| toolbar에 기능 선택, 실패 경로, 비교, AI 라벨, Mermaid, PNG 버튼을 한 줄에 배치 | 중간 너비에서 버튼이 지나치게 줄거나 여러 줄이 되면서 panel 높이 계산이 불안정해진다. |
| inspector 고정 폭 `292px` | 그래프 영역이 좁은 화면에서 지나치게 작아진다. |
| 모바일 대응이 폭 기준 `850px` 하나에 집중 | 낮은 높이, 태블릿 landscape, 브라우저 확대 상태를 처리하지 못한다. |
| 노드 설명 8px, 2줄 강제 clamp | 핵심 설명이 작고 잘려 구조도를 확대해도 의미를 읽기 어렵다. |

### 2.2 정보구조 문제

현재 분석 완료 후에는 다음 최상위 모드가 서로 경쟁한다.

- 프로젝트 지도
- 기능 흐름
- 원본 코드 탐색
- 변경 영향
- 깊이 배우기

프로젝트 지도 안에서도 `요약`과 `구조도`를 다시 선택해야 한다. 따라서 대표 기능이 분명하지 않고 구조도는 사용자가 찾아 들어가야 하는 보조 탭처럼 보인다.

### 2.3 그래프 의미 문제

현재 `architecture-graph-v2`는 핵심 파일을 골라 노드로 만든다.

- 장점: 모든 노드를 코드 evidence에 연결하기 쉽다.
- 한계: 비전공자에게 `repositories.py`, `schemas.py`, `RepositoryWorkbench.tsx`는 시스템 역할이 아니라 파일 이름이다.
- 한계: 파일마다 별도 노드가 생겨 전체 목적보다 구현 세부사항이 먼저 보인다.
- 한계: 책임 근거가 부족한 노드는 `OO module의 주요 책임과 경계를 나타냅니다` 같은 일반 문장으로 끝난다.
- 한계: `Client`, `Server`, `Domain`, `Data` 같은 기술 계층은 개발자에게는 익숙하지만 처음 보는 사용자가 서비스의 동작을 이해하는 순서와 다르다.

현재 품질 평가는 node·edge recall과 evidence에는 강하지만 다음을 아직 측정하지 않는다.

- 설명만 읽고 역할을 이해할 수 있는가?
- 저장소 목적과 노드의 기여가 연결되는가?
- 전문 용어 없이도 핵심 기능 흐름을 설명할 수 있는가?

### 2.4 프론트엔드 구조 문제

`RepositoryWorkbench.tsx`가 저장소 분석, 구조도, 기능 흐름, 코드 탐색, 학습, 변경 영향의 상태와 렌더링을 모두 소유한다. 대표 경험을 구조도 중심으로 재편할 때 이 컴포넌트를 계속 확장하면 다음 문제가 커진다.

- 상태 간 조건이 복잡해진다.
- 화면 전환 시 불필요한 데이터를 동시에 유지한다.
- 모바일 panel 동작과 데스크톱 inspector 동작을 분리하기 어렵다.
- 구조도에서 보조 도구를 drawer로 여는 상호작용을 테스트하기 어렵다.

## 3. 새 제품 개념: Repository Story

### 3.1 분석 전

메인 페이지는 저장소 입력에 집중한다.

- 한 문장 가치 제안: `코드를 읽기 전에, 이 저장소가 어떻게 일하는지 지도로 이해하세요.`
- GitHub URL과 branch 입력
- 분석 과정에서 무엇을 만들어 주는지 3단계로 설명
  1. 저장소 목적 파악
  2. 핵심 역할과 연결 구성
  3. 기능 흐름과 코드 근거 연결
- 대표 저장소 또는 최근 분석 결과 진입은 후속 범위로 둔다.

### 3.2 분석 중

빈 IDE shell 대신 분석 진행 story를 보여준다.

- 현재 단계와 사용자 관점 설명
- 발견된 언어, 패키지, 진입점의 점진적 표시
- 구조도가 완성되기 전에는 skeleton map 사용
- 실패 시 재시도와 실패 원인을 동일 위치에 표시

### 3.3 분석 완료 후

분석 완료 시 별도 탭 선택 없이 `Repository Story`가 기본 화면이다.

화면 순서는 다음과 같다.

1. Repository Purpose
2. 핵심 결과와 기술 문맥
3. Repository Structure 그래프
4. 선택 요소 설명 inspector
5. 기능 흐름·변경 영향·학습·코드 근거 보조 도구

### 3.4 핵심 사용자 문장

화면이 성공적이면 비전공자도 다음처럼 말할 수 있어야 한다.

> RepoWiseAI는 GitHub 저장소를 분석해 사람들이 코드 구조와 기능 흐름을 이해하도록 돕는 서비스다. 사용자가 주소를 입력하면 Web Workspace가 요청을 만들고, Analysis API가 작업을 접수하며, Worker가 코드를 분석한다. Navigation Engine이 그 결과를 구조도와 기능 흐름으로 정리하고, 저장된 결과는 학습과 변경 영향 분석에서 다시 사용된다.

## 4. 새 정보구조

### 4.1 최상위 navigation

상시 노출되는 최상위 navigation은 최소화한다.

- `Structure`: 기본 화면
- `Repository`: 저장소 교체, snapshot 및 분석 상태
- `More`: 고급 도구와 설정

현재의 Feature Flow, 원본 코드, 변경 영향, 깊이 배우기는 최상위 모드에서 제거하고 Structure 문맥 안으로 이동한다.

### 4.2 Structure 화면의 3단 구조

#### A. Purpose band

- 저장소 이름
- `이 저장소는 …을 위해 …을 하는 시스템입니다.` 형식의 목적 설명
- 주요 사용자 또는 호출 주체
- 최종 산출물
- confidence와 근거 링크
- commit, 분석 시각, 분석 품질은 보조 metadata로 표시

#### B. Story Map

기본 레벨은 `역할 보기`다.

- 역할 노드 6~10개
- 사용자나 외부 입력에서 결과까지 왼쪽에서 오른쪽으로 읽히는 방향
- 노드마다 자연어 역할 한 문장
- edge는 `요청을 전달합니다`, `분석 결과를 저장합니다`, `설명 재료를 제공합니다`처럼 문장형 관계를 사용
- 기술 계층 색상보다 기능적 역할과 흐름 강조

선택적으로 `구현 보기`로 전환하면 기존 파일 기반 architecture graph를 표시한다.

#### C. Context inspector

노드나 관계를 선택했을 때만 desktop side panel 또는 mobile bottom sheet로 연다.

inspector의 순서는 다음과 같다.

1. 이 요소가 하는 일
2. 전체 목적에 필요한 이유
3. 무엇을 받아서 무엇을 넘기는지
4. 참여하는 대표 기능
5. 실제 코드 근거
6. 보조 작업

## 5. 두 단계 그래프 모델

### 5.1 Level 1: Role Graph

비전공자 기본 화면이다. 파일이 아니라 책임을 노드로 삼는다.

예상 Role Graph node 예시:

- 사용자 작업 공간
- 분석 요청 접수
- 저장소 수집과 코드 분석
- 구조·기능 흐름 구성
- 분석 결과 저장
- 설명과 학습 제공
- 외부 GitHub·AI 서비스

node 개수:

- 권장 6~10개
- 최소 3개
- 최대 12개

### 5.2 Level 2: Implementation Graph

현재 `architecture-graph-v2`를 계승하는 개발자·상세 보기다.

- 실제 모듈과 파일
- 기술 계층
- semantic relation
- confidence와 evidence
- diff와 Change Brief 영향

Role node를 선택하고 `구현 상세 보기`를 눌렀을 때 해당 역할의 파일만 필터링해 표시한다. 전체 22개 파일을 처음부터 보여주지 않는다.

### 5.3 역할 clustering 규칙

v1은 결정론적으로 생성한다.

입력:

- Project Map purpose, capabilities, system areas
- Feature Flow의 trigger, step role, outcome
- Semantic Graph의 `REQUESTS`, `HANDLED_BY`, `CALLS`, `READS`, `WRITES`, `USES_EXTERNAL`, `RAISES`
- framework route와 worker entry point
- README와 manifest

clustering 우선순위:

1. 동일 feature flow에서 같은 역할을 수행하는 파일
2. 동일 server route·service·worker 경계
3. 동일 데이터 책임
4. 동일 사용자 화면 책임
5. 동일 외부 서비스 책임
6. 나머지는 shared/configuration 역할로 병합

모든 Role node는 최소 1개 이상의 member file과 evidence를 가져야 한다.

## 6. 자연어 설명 모델

### 6.1 새 응답 계약

기존 Project Map과 Architecture Graph를 합성하는 읽기 전용 endpoint를 추가한다.

```text
GET /api/snapshots/{snapshot_id}/repository-story
```

권장 응답:

```json
{
  "repository_name": "owner/repository",
  "snapshot_id": "snap_...",
  "analysis_version": "repository-story-v1",
  "purpose": {
    "one_liner": "이 저장소는 ...",
    "primary_audience": "...",
    "primary_outcome": "...",
    "how_it_works": ["...", "...", "..."],
    "confidence": "verified",
    "evidence": []
  },
  "roles": [
    {
      "id": "role_analysis_worker",
      "display_name": "저장소 수집과 코드 분석",
      "role_summary": "GitHub에서 코드를 가져와 구조를 읽을 수 있는 분석 데이터로 바꿉니다.",
      "why_it_exists": "구조도와 기능 설명이 추측이 아니라 실제 코드 근거를 사용하려면 이 과정이 필요합니다.",
      "contribution_to_goal": "서비스가 저장소를 이해하는 핵심 재료를 만듭니다.",
      "receives": ["저장소 주소와 commit 정보"],
      "produces": ["파일, 심볼, 관계, 분석 snapshot"],
      "member_file_ids": [],
      "capability_ids": [],
      "feature_flow_ids": [],
      "confidence": "verified",
      "evidence": []
    }
  ],
  "connections": [],
  "features": [],
  "limitations": []
}
```

### 6.2 설명 작성 원칙

각 설명은 다음 순서로 생성한다.

1. 기술 이름을 그대로 읽지 않고 행동으로 번역한다.
2. `무엇을 한다`와 `왜 필요한가`를 분리한다.
3. 저장소 전체 목적과 연결한다.
4. 입력과 결과를 구체적으로 표현한다.
5. 근거가 없는 사용자 가치나 의도를 만들지 않는다.
6. 전문 용어가 필요하면 쉬운 표현 뒤 괄호로 한 번만 사용한다.

나쁜 예:

> Repository Analysis worker의 주요 책임과 경계를 나타냅니다.

좋은 예:

> GitHub에서 받은 저장소를 실제로 내려받고 파일과 함수의 연결을 분석합니다. 이 결과가 구조도, 기능 흐름, 코드 설명의 공통 재료가 됩니다.

### 6.3 결정론적 설명 생성

기본 동작은 LLM 없이도 충분한 문장을 만든다.

- UI trigger + request 관계: `사용자의 행동을 서버 요청으로 바꿉니다.`
- server handler + queue 관계: `분석 요청을 확인하고 오래 걸리는 작업을 Worker에 넘깁니다.`
- worker + writes 관계: `코드를 분석하고 결과를 저장합니다.`
- navigation builder: `분석 결과를 사람이 읽을 수 있는 구조와 기능 흐름으로 정리합니다.`
- data model: `분석 결과를 나중에 다시 불러올 수 있도록 저장 형태를 정의합니다.`
- external service: `저장소 코드 또는 AI 설명을 외부 서비스에서 가져옵니다.`

파일 이름만 남는 generic fallback은 허용하지 않는다. 역할을 확정할 근거가 부족하면 `기타 구현 요소`로 합치고 limitation에 이유를 남긴다.

### 6.4 제한형 AI 보강

현재 optional AI label 기능을 `Repository Story narrative rewrite`로 확장할 수 있다.

AI가 할 수 있는 일:

- 결정론적으로 선택된 purpose와 role claim을 자연스럽게 다시 쓰기
- 전문 용어를 쉬운 표현으로 바꾸기
- 중복된 역할 설명을 합치기

AI가 할 수 없는 일:

- role 추가 또는 삭제
- member file 변경
- 관계 추가 또는 삭제
- evidence 변경
- 근거에 없는 사용자나 기능 추론

AI 응답은 기존 node·role ID만 선택할 수 있는 Structured Output으로 제한하고, 기본 feature flag는 off로 유지한다.

## 7. 보조 기능 통합

### 7.1 Feature Flow

독립 화면 대신 그래프 상단의 `기능 보기` selector로 제공한다.

- 기능 선택 시 관련 role과 connection만 강조
- 그래프 위에 1→2→3 순서 표시
- inspector에는 사용자 행동, 정상 결과, 실패 가능성 표시
- `전체 구조로 돌아가기`는 filter 초기화로 처리

### 7.2 Code Focus

코드는 설명의 evidence다.

- node inspector의 `코드 근거 보기`
- edge inspector의 `이 연결을 확인한 코드`
- 파일과 line을 side drawer에서 연다.
- 전체 IDE explorer는 `고급 코드 탐색`으로 이동한다.

### 7.3 Change Brief

선택한 node나 feature에서 시작한다.

- `이 부분을 바꾸면?`
- 직접 영향 role은 실선 강조
- 확인 필요 role은 점선 강조
- 위험, 확인할 파일, 테스트 포인트를 inspector tab으로 표시

### 7.4 학습과 DeepTask

현재 선택 문맥을 유지한다.

- `이 역할 배우기`
- `이 기능 흐름 배우기`
- `이 연결을 자세히 조사하기`
- 학습·DeepTask 결과는 구조도 위에 badge로 연결

### 7.5 snapshot diff와 export

상시 toolbar에서 제거하고 `More` menu로 이동한다.

- 버전 비교
- Mermaid 내보내기
- PNG 내보내기
- AI 설명 다듬기
- 원시 의존성 보기

## 8. 화면 레이아웃과 스크롤 규칙

### 8.1 공통 원칙

- 일반 웹사이트처럼 document가 세로로 스크롤되어야 한다.
- 전체 페이지에 `overflow: hidden`을 사용하지 않는다.
- graph canvas만 pan·zoom을 소유한다.
- inspector 내부만 별도 세로 scroll을 가진다.
- page scroll과 canvas zoom이 같은 wheel event를 경쟁하지 않게 한다.
- button label은 임의로 잘라 숨기지 않는다.

### 8.2 Desktop

- header는 sticky
- purpose band와 action bar는 page flow에 포함
- canvas 높이: `clamp(520px, calc(100dvh - header), 820px)`
- inspector: 360~420px side drawer
- inspector가 닫히면 canvas가 전체 폭 사용
- toolbar는 primary controls와 overflow menu로 분리

### 8.3 Tablet

- inspector는 오른쪽 overlay drawer
- graph 아래에 고정 panel을 항상 두지 않는다.
- 저장소 form은 2행으로 자연스럽게 wrap
- 상단 버튼은 icon-only가 아니라 label을 유지하거나 menu로 이동

### 8.4 Mobile

- purpose one-liner와 graph를 먼저 표시
- graph 높이 460~560px
- inspector는 accessible bottom sheet
- feature 선택은 full-width select
- export·diff·고급 기능은 More menu
- touch target 최소 44px
- horizontal page overflow는 0

### 8.5 높이가 낮은 화면

폭뿐 아니라 높이 media query를 둔다.

```css
@media (max-height: 720px) { ... }
```

- header와 metadata를 compact variant로 전환
- canvas 최소 높이를 viewport에서 계산
- inspector는 overlay 방식 사용
- page scroll로 모든 action에 접근 가능해야 한다.

## 9. 프론트엔드 구조 개편

`RepositoryWorkbench.tsx`를 orchestration 역할만 남기고 다음으로 분리한다.

```text
RepositoryWorkspace
├─ RepositoryHeader
├─ RepositoryAnalysisForm
├─ RepositoryStoryPage
│  ├─ RepositoryPurposeCard
│  ├─ StructureActionBar
│  ├─ RepositoryStoryCanvas
│  ├─ RoleNode
│  ├─ StoryConnection
│  └─ StructureInspector
│     ├─ OverviewTab
│     ├─ FeatureFlowTab
│     ├─ ChangeImpactTab
│     ├─ LearningTab
│     └─ EvidenceTab
├─ ImplementationGraphView
└─ AdvancedCodeWorkspace
```

상태는 다음 범위로 나눈다.

- repository lifecycle
- story graph selection
- active feature overlay
- inspector tool
- advanced workspace

URL query를 사용해 선택 문맥을 복원한다.

```text
/?snapshot=snap_...&role=role_analysis_worker&tool=evidence
```

## 10. 백엔드 구현 범위

### 10.1 신규

- `app/navigation/repository_story.py`
- `RepositoryStoryResponse` schema
- `repository-story-v1` version
- role clustering과 narrative validator
- `/repository-story` API
- `NavigationArtifact` cache
- story gold evaluator와 fixture

### 10.2 기존 변경

- Project Map capability fallback을 route 이름 나열이 아니라 feature flow 기반 사용자 기능으로 개선
- Architecture Graph node의 generic responsibility fallback 제거
- group label을 기술 계층과 사용자 관점 label로 동시에 제공
- Feature Flow를 Role node에 mapping
- Change Brief 결과를 Role node에 projection

### 10.3 데이터베이스

v1은 기존 `NavigationArtifact`를 재사용하므로 migration 없이 구현한다.

별도 사용자 편집 설명이나 수동 role merge를 저장해야 할 때만 후속 migration을 검토한다.

## 11. 단계별 구현

### Phase A — UI 안정화

목표: 현재 기능을 유지한 채 잘림과 스크롤 문제부터 제거한다.

- body/app shell의 전역 overflow 정책 수정
- graph panel 고정 최소 높이 제거
- toolbar primary/More 재배치
- inspector responsive drawer화
- 중간 폭과 낮은 높이 breakpoint 추가
- 모든 button과 select의 최소 크기 및 wrapping 정책 통일

완료 조건:

- 지원 viewport에서 가려진 action이 없다.
- 세로 page scroll로 모든 영역에 접근할 수 있다.
- horizontal page scroll이 없다.

### Phase B — Repository Story backend

- purpose contract
- Role Graph clustering
- 자연어 설명 template
- validator와 artifact cache
- 기존 feature·change mapping
- API와 evaluator

완료 조건:

- 모든 role에 `role_summary`, `why_it_exists`, `contribution_to_goal`, evidence가 있다.
- generic `주요 책임과 경계` 문장이 0개다.

### Phase C — Structure-first main page

- 분석 완료 기본 화면을 Repository Story로 변경
- purpose band
- Role Graph
- 선택 inspector
- overview/implementation level 전환
- empty/loading/error/reanalysis states

완료 조건:

- 분석 완료 후 추가 클릭 없이 목적과 구조도가 보인다.
- 파일 이름을 몰라도 역할을 선택할 수 있다.

### Phase D — 보조 기능 부착

- feature overlay
- evidence drawer
- Change Brief projection
- learning/DeepTask context
- diff/export/원시 graph More menu

완료 조건:

- 최상위 화면을 떠나지 않고 구조 이해→기능 확인→코드 근거→변경 영향으로 이동한다.

### Phase E — 반응형·접근성

- keyboard graph navigation
- focus management
- bottom sheet
- reduced motion
- screen reader label
- zoom 200%
- 색상만으로 confidence·impact를 구분하지 않기

### Phase F — 실저장소 평가와 rollout

- RepoWiseAI
- p-map
- 중형 Python API 저장소
- 대형 TypeScript monorepo
- README가 빈약한 저장소

기존 Architecture Graph는 `구현 보기` fallback으로 한 release 이상 유지한다.

## 12. 테스트 계획

### 12.1 UI 자동화

Playwright 기반 viewport 테스트를 추가한다.

필수 viewport:

- 1440×900
- 1280×720
- 1024×768
- 820×1180
- 768×1024
- 390×844
- 320×568

검증:

- viewport 밖으로 잘린 button 없음
- horizontal overflow 없음
- page scroll 가능
- toolbar More menu 접근 가능
- inspector 열기·닫기와 focus 복귀
- mobile bottom sheet scroll
- graph zoom과 page scroll 충돌 없음
- 200% browser zoom에서도 핵심 action 접근 가능

### 12.2 API

- stable role ID
- clustering 결정성
- role 수 제한
- member file과 evidence 유효성
- purpose evidence
- generic fallback 금지
- feature flow mapping coverage
- corrupt artifact fallback
- old snapshot 처리

### 12.3 사람 평가

비전공자 또는 해당 저장소를 처음 보는 검수자에게 다음 질문을 한다.

1. 이 저장소의 목적을 한 문장으로 설명할 수 있는가?
2. 핵심 역할 3개와 각 역할의 기여를 설명할 수 있는가?
3. 대표 기능 하나의 흐름을 설명할 수 있는가?
4. 변경을 시작할 위치를 찾을 수 있는가?

목표:

- 목적 이해 성공률 90% 이상
- 핵심 역할 이해 성공률 80% 이상
- 대표 기능 흐름 이해 성공률 80% 이상
- 첫 구조 이해까지 median 60초 이하

### 12.4 정량 품질 게이트

- purpose evidence validity `1.0`
- role evidence validity `1.0`
- feature-to-role mapping coverage `>= 0.90`
- verified role precision `>= 0.90`
- generic responsibility ratio `0`
- overview role count `3~12`
- UI critical overflow regression `0`

## 13. 완료 기준

다음 조건을 모두 만족해야 전체 개편 완료로 본다.

- Repository Structure가 분석 완료 후 기본 메인 화면이다.
- 요약과 구조도가 분리된 탭이 아니라 한 이야기로 연결된다.
- 비전공자가 파일명을 몰라도 각 요소의 역할과 전체 목적 기여를 이해할 수 있다.
- 그래프는 역할 레벨과 구현 레벨의 점진적 상세 보기를 제공한다.
- Feature Flow, Code Focus, Change Brief, 학습, DeepTask가 선택한 구조 요소 문맥을 유지한다.
- desktop, tablet, mobile, 낮은 높이 화면에서 button이 잘리거나 접근 불가능하지 않다.
- page, canvas, inspector의 scroll 소유권이 명확하다.
- 설명 문장마다 실제 코드 또는 저장소 문서 근거가 있다.
- 기존 API·Web 회귀 테스트와 새 UI·story evaluator가 모두 통과한다.

## 14. 예상 변경 파일

Backend:

- `apps/api/app/navigation/repository_story.py`
- `apps/api/app/navigation/architecture_graph.py`
- `apps/api/app/navigation/project_map.py`
- `apps/api/app/navigation/versions.py`
- `apps/api/app/navigation/architecture_validation.py`
- `apps/api/app/api/repositories.py`
- `apps/api/app/schemas.py`
- `apps/api/app/evaluation/repository_story.py`
- `apps/api/evaluation/fixtures/repository_story_*.json`

Frontend:

- `apps/web/src/components/RepositoryWorkbench.tsx`
- `apps/web/src/components/RepositoryStoryPage.tsx`
- `apps/web/src/components/RepositoryPurposeCard.tsx`
- `apps/web/src/components/RepositoryStoryCanvas.tsx`
- `apps/web/src/components/StructureInspector.tsx`
- `apps/web/src/components/StructureActionBar.tsx`
- `apps/web/src/components/RoleNode.tsx`
- `apps/web/src/components/ArchitectureMapPanel.tsx`
- `apps/web/src/app/globals.css`
- 관련 CSS module과 테스트

## 15. 권장 PR 분할

1. `fix web shell scrolling and responsive structure controls`
2. `add repository story schema, role graph builder, and evaluator`
3. `make repository story the default analyzed-repository page`
4. `attach feature flow, evidence, and change impact to structure context`
5. `add responsive drawer, accessibility, and viewport regression tests`
6. `roll out story-first experience and retire duplicate top-level navigation`

## 16. 이번 계획에서 제외하는 항목

- 사용자가 graph node를 직접 편집하는 기능
- 실시간 공동 편집
- runtime tracing 기반 동적 graph
- 모든 언어의 완전한 semantic analysis
- 구조도를 별도 문서 편집기로 만드는 기능

이 항목들은 Structure-first 경험과 설명 품질이 안정화된 뒤 검토한다.

## 17. 첫 구현 순서

1. UI overflow와 scroll ownership을 먼저 고쳐 현재 기능을 안정화한다.
2. `repository-story-v1` 계약과 RepoWiseAI gold fixture를 작성한다.
3. Role Graph 결정론적 builder와 자연어 template을 구현한다.
4. Repository Story 메인 화면을 기존 구조도와 feature flag 아래 병행한다.
5. Feature Flow와 evidence를 새 inspector에 연결한다.
6. Change Brief, 학습, DeepTask를 차례로 연결한다.
7. viewport 자동화와 사람 이해도 평가를 통과하면 기본 경험으로 전환한다.
