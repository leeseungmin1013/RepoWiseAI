# RepoWise AI

RepoWise AI는 GitHub 코드베이스를 실제 코드 근거와 검증된 학습자료에 연결하여, 배경지식이 없는 사용자도 문법부터 실행 흐름과 아키텍처까지 자신의 수준에 맞게 배울 수 있도록 안내하는 인터랙티브 AI 코드 학습 가이드입니다.

## 현재 구현 상태

다섯 번째 MVP vertical slice인 Concept Graph 기반 적응형 학습과 숙련도 추적까지 동작합니다.

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

## OpenAI 설정

`.env`의 `OPENAI_API_KEY`에 프로젝트용 API 키를 설정하고 `EMBEDDING_PROVIDER=auto`, `GENERATION_PROVIDER=auto`를 유지하면 OpenAI provider가 자동으로 활성화됩니다.

```dotenv
OPENAI_API_KEY=your_project_key
```

임베딩 공간은 snapshot별로 고정됩니다. 키를 설정하거나 `EMBEDDING_MODEL`을 바꾼 뒤에는 저장소를 다시 분석해 새 snapshot을 만들어야 semantic vector 검색에 새 모델이 반영됩니다. 기존 local snapshot은 exact·full-text 검색을 계속 사용할 수 있습니다.

## 로컬 실행

필수 도구:

- Docker Desktop
- Node.js와 pnpm
- Python 3.12를 설치할 수 있는 `uv`

환경 파일을 준비합니다.

```powershell
Copy-Item .env.example .env
Copy-Item apps/web/.env.local.example apps/web/.env.local
```

PostgreSQL과 Redis를 시작합니다.

```powershell
docker compose up -d postgres redis
```

API 의존성과 DB schema를 준비합니다.

```powershell
uv sync --project apps/api
pnpm db:migrate
```

API와 worker를 각각 실행합니다.

```powershell
# repository root
pnpm dev:api

# repository root, 별도 터미널
pnpm dev:worker
```

웹 앱을 실행합니다.

```powershell
# repository root
pnpm install
pnpm dev:web
```

- Web: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>
- API health: <http://localhost:8000/api/health>

## 검증

```powershell
uv run --project apps/api ruff check apps/api
uv run --project apps/api pytest -q
pnpm lint:web
pnpm test:web
pnpm build:web
pnpm eval:retrieval --fixture evals/retrieval/p-map.json
```

## 프로젝트 문서

- [전체 프로젝트 기획서](PROJECT_PLAN.md)
- [구현 계획서](IMPLEMENTATION_PLAN.md)
- [프로젝트 기획서 PDF](output/pdf/RepoWiseAI_Project_Plan.pdf)
