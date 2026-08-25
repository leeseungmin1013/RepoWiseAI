# RepoWise AI

RepoWise AI는 GitHub 코드베이스를 실제 코드 근거와 검증된 학습자료에 연결하여, 배경지식이 없는 사용자도 문법부터 실행 흐름과 아키텍처까지 자신의 수준에 맞게 배울 수 있도록 안내하는 인터랙티브 AI 코드 학습 가이드입니다.

## 현재 구현 상태

Repository Structure 중심 탐색, 구조·기능·코드·변경 영향 연결과 Concept Graph 기반 적응형 학습까지 동작합니다.

- public GitHub repository URL 등록
- branch와 commit SHA가 고정된 repository snapshot
- GitHub archive 크기·경로·symlink·비밀 파일 안전 필터
- TypeScript/JavaScript Tree-sitter 분석
- 함수, 클래스, 컴포넌트, route와 import/call 후보 추출
- PostgreSQL 기반 파일·심볼·관계·계층형 코드 chunk 저장
- symbol/file/block chunk와 부모 근거 연결
- PostgreSQL full-text lexical search와 pgvector 검색
- exact/lexical/vector/selection retriever와 RRF 융합
- 한국어 개발 용어 query expansion과 구조 기반 경량 reranking
- retrieval run과 후보 순위 trace
- evidence ID allowlist, 원문 hash·라인 검증, 서버 조립 citation
- OpenAI Structured Outputs 기반 grounded answer와 키 없는 로컬 retrieval fallback
- 기초·표준·심화 설명 깊이 선택과 세션별 학습 스타일 유지
- Redis와 RQ 기반 durable analysis worker
- 분석 단계와 진행 상태 API
- 파일 트리, Monaco Editor, import graph, Start Here 화면
- 코드 질문, 선택 범위 맥락, citation warp와 라인 highlight
- snapshot별 3~5단계 deterministic Guided Code Tour
- 검증된 code chunk 기반 단계 목표, 개념 tag, 예상 학습 시간
- Tour session 진행률과 `opened`, `understood`, `needs_help` 이벤트 저장
- “어려워요” 피드백에 따른 설명 깊이 하향과 새로고침 후 진행 복구
- Tour 단계 이동과 Monaco code warp 자동 동기화
- anonymous learner profile과 저장소별 6~7문항 목표·배경지식 진단
- 진단 skip, 객관식 deterministic score, concept별 score·confidence projection
- 프로젝트 크기와 사용자 이해도를 반영한 최대 40단계 계층형 curriculum
- 방향 잡기, 선수 개념, 구조, 핵심 기능, 데이터·오류, 테스트 영역별 module
- Start Here, 현재 lesson, Monaco 선택 범위, AI 질문이 공유하는 Learning Session
- lesson의 `opened`, `understood`, `needs_help`, `skip` 이벤트와 숙련도 업데이트
- 실제 `throw`, `return`, resolved `CALLS`·`IMPORTS` 근거로 만드는 4지선다 checkpoint activity
- activity 정오 판정, 근거 라인 warp, concept score·confidence 변화 이력
- 버전이 고정된 TypeScript·웹 핵심 Concept Graph 17개 node와 20개 prerequisite edge
- 현재 lesson과 숙련도를 비교해 가장 가까운 선수 개념만 고르는 최소 gap resolver
- 진단·lesson feedback·activity별 점수 전후 값과 code evidence를 보여 주는 Mastery 화면
- 완료 lesson을 보존하고 미완료 경로만 다시 만드는 revision 기반 재계획
- 분석 중 뒤늦게 감지된 React·Next.js 진단 문항의 idempotent late binding
- Tree-sitter AST statement 기반 문장별 설명과 source hash 재검증
- 선수 개념 micro-lesson, 작은 예제, MDN·TypeScript·React·Next.js 공식 자료 추천
- 보충 학습 return stack과 원래 lesson 복귀
- 현재 module·lesson·concept를 검색 query와 OpenAI Structured Output prompt에 주입
- 데스크톱·모바일 반응형 작업공간
- 분석 완료 직후 저장소 목적과 핵심 역할을 자연어로 설명하는 Repository Story
- 파일 이름 대신 사용자·시스템 역할로 먼저 보여 주고 구현 파일로 점진적으로 펼치는 Repository Structure
- 역할별 `왜 필요한가`, `전체 목적 기여`, 입력·결과와 실제 코드 line 근거
- 기능별 정상·실패 흐름 오버레이, Code Focus 이동, Change Brief 영향 강조와 구조 학습 연결
- 데스크톱 inspector와 모바일 bottom sheet를 포함한 일반 웹 문서형 반응형 레이아웃
- Python/FastAPI·DB SDK·cross-file request helper를 포함한 `semantic-ts-v2` 관계 분석
- Architecture/Repository Story gold 평가 CLI, commit 구조 diff, PNG·Mermaid export

다음 vertical slice는 공식 문서 freshness 검증, 최근 질문·활동·보충 경로 복구, 학습 품질 평가 fixture와 운영 관측성 강화에 집중합니다. 기존 Guided Code Tour API는 호환성을 위해 유지하지만 기본 UI는 Adaptive Learning Journey를 사용합니다.

## 구조

```text
apps/
  api/    FastAPI, SQLAlchemy, Alembic, RQ, Tree-sitter
  web/    Next.js, Monaco Editor, React Flow
evals/    후속 RAG 평가 데이터
output/   프로젝트 기획서 PDF
```

로컬 인프라는 PostgreSQL/pgvector와 Redis를 사용합니다.

`OPENAI_API_KEY`가 없으면 deterministic local hash vector로 검색·citation 흐름을 실행합니다. 키를 설정하면 `text-embedding-3-small`의 768차원 embedding과 `gpt-5.4-mini` Structured Outputs가 semantic retrieval과 근거 기반 설명을 담당합니다. 모델명과 provider는 `.env`에서 교체할 수 있습니다.

## 인증, 분석 재사용, 사용량 설정

보호 API는 Supabase access token을 FastAPI에서 JWKS로 검증하고, 모든 자원을 application organization에 연결합니다. 브라우저에는 `NEXT_PUBLIC_SUPABASE_URL`과 publishable key만 설정하며 service-role key는 절대 전달하지 않습니다.

운영 전환 순서는 다음과 같습니다.

1. Supabase redirect URL에 `/auth/callback`을 등록하고 asymmetric signing key를 사용합니다.
2. `.env`에 `SUPABASE_URL`을 설정하고 웹 환경에 publishable key를 설정합니다.
3. migration `0010`부터 `0016`까지 적용합니다.
4. cache는 write/shadow 관측 후 read를 켭니다.
5. quota는 `off`, `shadow`, `enforce` 순서로 올립니다.
6. 보호 전환 시 `AUTH_REQUIRED=true`로 설정합니다.

동일 commit과 analysis fingerprint는 기존 snapshot/job을 재사용합니다. 작은 변경은 manifest diff, dependency closure, content-addressed parse/chunk/embedding cache를 사용하며 영향 범위가 30%를 넘으면 full 분석으로 전환합니다. 계정 화면 `/account`에서 월간 allowance, bonus, 예약, 잔여량, 기능별 hard limit, cache hit 원장을 확인할 수 있습니다.

운영 rollback은 각 feature flag를 끄는 방식으로 수행합니다. incremental 실패 시 full 경로가 유지되고, semantic cache read를 꺼도 write/기존 원장은 보존됩니다. stale reservation과 만료 cache 정리는 maintenance worker 함수로 수행합니다.
## OpenAI 설정

`.env`의 `OPENAI_API_KEY`에 프로젝트용 API 키를 설정하고 `EMBEDDING_PROVIDER=auto`, `GENERATION_PROVIDER=auto`를 유지하면 OpenAI provider가 자동으로 활성화됩니다.

```dotenv
OPENAI_API_KEY=your_project_key
```

임베딩 공간은 snapshot별로 고정됩니다. 키를 설정하거나 `EMBEDDING_MODEL`을 바꾼 뒤에는 저장소를 다시 분석해 새 snapshot을 만들어야 semantic vector 검색에 새 모델이 반영됩니다. 기존 local snapshot은 exact·full-text 검색을 계속 사용할 수 있습니다.

## 로컬 전체 스택 실행

아래 명령은 Windows PowerShell과 repository root에서 실행하는 것을 기준으로 합니다. 전체 스택은 다음 프로세스로 구성됩니다.

| 구성 요소 | 역할 | 주소 또는 포트 | 실행 방식 |
| --- | --- | --- | --- |
| PostgreSQL + pgvector | 저장소 분석 결과, 학습 상태, vector 저장 | `localhost:5432` | Docker Compose |
| Redis | RQ 작업 queue | `localhost:6379` | Docker Compose |
| FastAPI | REST API와 OpenAPI 문서 | `http://localhost:8000` | `pnpm dev:api` |
| RQ worker | 저장소 분석과 deep learning task 처리 | 별도 포트 없음 | `pnpm dev:worker` |
| Next.js | 사용자 웹 UI | `http://localhost:3000` | `pnpm dev:web` |

### 1. 필수 도구 확인

다음 도구가 필요합니다.

- Docker Desktop
- Node.js와 pnpm 11
- Python 3.12를 설치하고 가상환경을 관리할 수 있는 `uv`

설치 여부와 Docker engine 상태를 확인합니다.

```powershell
docker --version
docker compose version
node --version
pnpm --version
uv --version
docker info
```

`docker info`가 engine 연결 오류를 출력하면 Docker Desktop을 먼저 실행하고 engine이 준비될 때까지 기다립니다. 일부 Windows 환경에서 `docker compose`가 인식되지 않고 `docker-compose`만 제공되는 경우에는 이 문서의 `docker compose`를 `docker-compose`로 바꾸어 실행하면 됩니다.

### 2. 환경 파일 준비

최초 1회만 example 파일을 복사합니다. 아래 명령은 이미 존재하는 `.env`와 `.env.local`을 덮어쓰지 않습니다.

```powershell
if (!(Test-Path .env)) {
  Copy-Item .env.example .env
}

if (!(Test-Path apps/web/.env.local)) {
  Copy-Item apps/web/.env.local.example apps/web/.env.local
}
```

기본 설정은 다음 로컬 주소를 사용합니다.

```dotenv
# .env
DATABASE_URL=postgresql+psycopg://repowise:repowise@localhost:5432/repowise
REDIS_URL=redis://localhost:6379/0

# apps/web/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

`OPENAI_API_KEY`는 선택 사항입니다. 키가 없어도 local hash vector와 deterministic fallback으로 기본 검색·citation 흐름을 검토할 수 있습니다. 키를 사용할 때는 `.env`의 `OPENAI_API_KEY`에만 저장하고 환경 파일을 Git에 commit하지 않습니다.

### 3. 의존성 설치

최초 실행, lockfile 변경 또는 dependency 변경 후 실행합니다.

```powershell
pnpm install --frozen-lockfile
uv sync --project apps/api
```

### 4. PostgreSQL과 Redis 시작

인프라 컨테이너는 background에서 실행합니다.

```powershell
docker compose up -d postgres redis
docker compose ps
```

`docker compose ps`에서 두 서비스가 모두 `healthy`가 될 때까지 기다립니다. 처음 실행하면 container image를 내려받아 시간이 더 걸릴 수 있습니다.

### 5. DB migration 적용

PostgreSQL이 `healthy`가 된 뒤 현재 schema까지 migration합니다. 이미 적용된 migration은 다시 실행해도 안전합니다.

```powershell
pnpm db:migrate
```

### 6. API, worker, 웹 실행

개발 서버 세 개는 계속 실행되는 프로세스이므로 각각 별도 PowerShell 터미널에서 실행합니다.

터미널 1 — FastAPI:

```powershell
pnpm dev:api
```

터미널 2 — RQ worker:

```powershell
pnpm dev:worker
```

worker가 정상적으로 Redis에 연결되면 `Listening on repowise-deep-learning, repowise-analysis`와 비슷한 메시지가 표시됩니다. worker를 실행하지 않으면 웹과 API는 열리지만 새 저장소 분석 작업은 처리되지 않습니다.

터미널 3 — Next.js:

```powershell
pnpm dev:web
```

Next.js가 `Ready`를 출력하면 다음 주소에서 검토할 수 있습니다.

- Web: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>
- API health: <http://localhost:8000/api/health>

첫 웹 요청에서는 Next.js가 페이지를 compile하므로 응답까지 몇 초 걸릴 수 있습니다.

### 7. 실행 상태 확인

PowerShell에서 API, DB, Redis 상태를 한 번에 확인합니다.

```powershell
$health = Invoke-RestMethod http://localhost:8000/api/health
$health | ConvertTo-Json -Depth 4
docker compose ps
```

정상적인 API 응답은 `status`, `checks.database`, `checks.queue`가 모두 `ready`입니다.

```json
{
  "status": "ready",
  "version": "0.1.0",
  "checks": {
    "database": "ready",
    "queue": "ready"
  }
}
```

포트 충돌이나 예상하지 않은 프로세스가 의심되면 다음 명령으로 확인합니다.

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -In 3000, 5432, 6379, 8000 |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

### 평소 재실행 순서

의존성과 migration이 이미 준비된 개발 환경에서는 다음 순서만 반복하면 됩니다.

1. Docker Desktop을 실행합니다.
2. `docker compose up -d postgres redis`를 실행합니다.
3. 별도 터미널에서 `pnpm dev:api`, `pnpm dev:worker`, `pnpm dev:web`을 실행합니다.
4. <http://localhost:8000/api/health>와 <http://localhost:3000>을 확인합니다.

### 종료와 데이터 초기화

API, worker, 웹 터미널에서는 각각 `Ctrl+C`로 프로세스를 종료합니다. PostgreSQL과 Redis를 중지하려면 다음 명령을 실행합니다.

```powershell
docker compose stop
```

컨테이너와 Compose network를 정리하되 DB와 Redis volume 데이터는 보존하려면 다음 명령을 사용합니다.

```powershell
docker compose down
```

로컬 DB와 Redis 데이터를 완전히 초기화해야 할 때만 `-v`를 사용합니다. 이 명령은 저장된 repository snapshot과 학습 상태를 복구할 수 없게 삭제합니다.

```powershell
docker compose down -v
```

### 자주 발생하는 문제

- `docker compose`가 unknown command인 경우: `docker-compose` 명령을 사용합니다.
- Docker API 또는 named pipe 연결 오류가 나는 경우: Docker Desktop을 실행하고 `docker info`가 성공하는지 확인합니다.
- API health에서 database 또는 queue가 ready가 아닌 경우: `docker compose ps`의 health와 `.env`의 `DATABASE_URL`, `REDIS_URL`을 확인한 뒤 API를 재시작합니다.
- 웹은 열리지만 API 요청이 실패하는 경우: `apps/web/.env.local`의 `NEXT_PUBLIC_API_URL`을 확인하고 Next.js를 재시작합니다. Next.js는 시작할 때 환경 파일을 읽습니다.
- 저장소 분석이 대기 상태에 머무는 경우: worker 터미널이 실행 중인지, Redis가 `healthy`인지 확인합니다.
- `5432`, `6379`, `8000`, `3000` 포트가 이미 사용 중인 경우: 위의 `Get-NetTCPConnection` 명령으로 점유 프로세스를 확인하거나 `.env`, Compose port, 실행 명령을 함께 변경합니다.

## 검증

```powershell
uv run --project apps/api ruff check apps/api
uv run --project apps/api pytest -q
pnpm lint:web
pnpm test:web
pnpm build:web
pnpm eval:retrieval --fixture evals/retrieval/p-map.json
pnpm eval:story
```

## 프로젝트 문서

- [프로젝트 종합 현황과 남은 구현 계획](docs/PROJECT_OVERVIEW.md)
- [시간순 문서 인덱스](docs/README.md)
- [전체 프로젝트 기획서](docs/plans/01_2026-07-06_PROJECT_PLAN.md)
- [구현 계획서](docs/plans/02_2026-07-06_IMPLEMENTATION_PLAN.md)
- [Repository Structure First UI 개편 계획과 구현 결과](docs/plans/07_2026-07-30_REPOSITORY_STRUCTURE_FIRST_UI_REDESIGN_PLAN.md)
- [프로젝트 기획서 PDF](output/pdf/RepoWiseAI_Project_Plan.pdf)
