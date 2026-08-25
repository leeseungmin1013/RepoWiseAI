# Phase 0. 배포 의사결정 확정 계획

- 기준일: 2026-08-22
- 상태: 실행 전 의사결정 필요
- 목표: 이후 단계에서 되돌리기 비싼 인프라·보안·비용 정책을 문서와 승인 기록으로 고정한다.
- 예상 기간: 0.5~1일
- 선행 조건: 없음
- 후속 단계: Phase 1 코드 기준선 확정

## 1. 범위와 기본안

| 영역 | 기본안 | 확정해야 할 값 |
| --- | --- | --- |
| Web | Vercel | staging/production 프로젝트와 소유 팀 |
| API·worker·cron | Render | workspace, service plan, region |
| Auth·DB·pgvector | Supabase | staging/production project, region, backup 정책 |
| Queue | Render Key Value | plan, persistence, eviction, region |
| CI·코드 | GitHub | 보호 브랜치, required checks, 배포 승인자 |
| 도메인 | `app.<domain>`, `api.<domain>` | 실제 도메인, DNS 관리자, TTL |

현재 구성은 FastAPI, Next.js 16, PostgreSQL/pgvector, Redis/RQ를 유지한다. Supabase는 Auth와 PostgreSQL을 제공하되 애플리케이션 스키마의 source of truth는 SQLAlchemy/Alembic으로 유지한다.

## 2. 의사결정 작업

### 2.1 리전과 네트워크

1. 주 사용자 위치와 데이터 거주 요구를 적는다.
2. Supabase와 Render에서 동시에 제공되는 가장 가까운 region을 비교한다.
3. API↔DB, API↔Redis, worker↔DB의 왕복 지연을 우선해 같은 권역을 선택한다.
4. Vercel 함수는 API의 주 실행 계층으로 사용하지 않고 브라우저가 `api.<domain>`을 호출하도록 확정한다.
5. 선택 region, 대안, 예상 지연, 이전 난이도를 ADR에 기록한다.

### 2.2 예산과 용량

월 고정비와 변동비를 분리한다. 고정비에는 Supabase, Render API/worker/cron/Key Value, Vercel plan을 포함하고 변동비에는 OpenAI token·embedding·Realtime, egress, backup 초과분을 포함한다.

| 정책 | 기록할 내용 |
| --- | --- |
| 월 인프라 상한 | staging과 production 각각의 상한 |
| OpenAI 상한 | 조직 전체 hard budget과 경고선 70/90/100% |
| 무료 allowance | `DEFAULT_MONTHLY_ALLOWANCE_MICRO_USD` 초기값 |
| 기능별 예약액 | chat, analysis, deep task, realtime의 보수적 예약액 |
| 확장 기준 | queue depth, p95 latency, DB/Redis 사용률 임계값 |

### 2.3 인증과 사용자 정책

- 1차 로그인 제공자를 이메일만으로 할지 Google/GitHub OAuth까지 열지 확정한다.
- 이메일 검증 전 허용 기능, 비밀번호 재설정, 계정 정지·삭제 절차를 정한다.
- 개인 organization 자동 생성과 초기 단일 workspace 노출 정책을 승인한다.
- 공개 저장소 snapshot은 공유하되 chat, 학습, 생성 cache는 organization/user 경계를 유지한다.
- 관리자 계정 생성자와 break-glass 절차를 정한다.

### 2.4 도메인·보안·운영 책임

- production/staging URL, DNS 소유자, TLS 자동 갱신 책임자를 지정한다.
- 브라우저 공개값과 서버 secret을 구분하고 저장 위치를 정한다.
- migration 실행 권한, production 배포 승인, 장애 지휘, 비용 담당자를 지정한다.
- 로그 보존 기간, 개인정보 취급 범위, DB backup/PITR 목표(RPO/RTO)를 결정한다.

## 3. 산출물

- `docs/operations/ADR-001-hosting-and-region.md`: 서비스 구성·region 결정과 대안
- `docs/operations/ADR-002-auth-and-tenancy.md`: 로그인 제공자와 tenant 경계
- `docs/operations/ADR-003-budget-and-allowance.md`: 예산, allowance, 경고·차단 기준
- staging/production URL·리소스명·소유자를 담은 환경 매트릭스
- secret inventory. 값 자체는 Git에 넣지 않고 이름, 저장 위치, rotation 주기만 기록한다.

## 4. 승인 체크리스트

- [ ] Supabase와 Render region이 확정되었다.
- [ ] production 도메인과 DNS 변경 권한자가 확정되었다.
- [ ] 월 고정비·OpenAI budget·무료 allowance가 승인되었다.
- [ ] 이메일/OAuth 범위와 callback URL 패턴이 확정되었다.
- [ ] staging과 production의 리소스·secret이 완전히 분리된다.
- [ ] RPO/RTO, backup/PITR, 로그 보존 정책이 정해졌다.
- [ ] 배포·migration·rollback 승인자가 지정되었다.

## 5. 완료 조건과 중단 조건

모든 결정에 담당자, 날짜, 근거가 있고 미정값 없이 ADR이 승인되면 완료다. region, production 도메인, 월 예산 중 하나라도 미정이면 Phase 3 이후 비용 또는 데이터 이전을 유발하므로 인프라 생성을 중단한다. Phase 1과 로컬 Phase 2 작업은 병행할 수 있다.
