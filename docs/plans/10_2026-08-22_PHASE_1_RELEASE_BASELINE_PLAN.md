# Phase 1. 코드 기준선과 릴리스 준비 계획

## 구현 상태 (2026-08-25)

- 코드 경계 보강: 완료 — debug/admin/usage tenant 격리, 가격 중복 계산 방지, atomic audit, route inventory 회귀 테스트
- API/Web 정적·단위 검증: 완료 — API 153 tests, Web 102 tests, lint/build 성공
- migration 선형 chain/offline SQL, fresh DB, `0009` legacy backfill, downgrade/re-upgrade: 완료
- 신규 snapshot 기반 retrieval/navigation/architecture/story eval과 실제 Redis/RQ worker: 완료
- Supabase 실제 JWT·refresh·인증 강제·동일 SHA 병렬 요청·ES256 signing-key 회전/폐기: 완료
- 논리 commit/PR/RC SHA: 진행 — 모든 기술 integration gate 통과

실행 절차는 `docs/operations/release-checklist.md`, 파일별 소유권과 commit 경계는
`docs/operations/phase-1-change-inventory.md`를 기준으로 한다. 미완료 gate를 통과 처리하지 않는다.

- 기준일: 2026-08-22
- 상태: 즉시 착수 가능
- 목표: 현재 대규모 작업 트리를 검증 가능한 commit 묶음으로 정리하고 배포 후보 SHA를 확정한다.
- 예상 기간: 2~4일
- 선행 조건: Phase 0의 배포 구조 기본안
- 주요 위험: 사용자 변경 유실, migration 순서 오류, 인증 우회, 비용 이중 기록

## 1. 현재 기준선

현재 branch는 `codex/repository-structure-visualization`, 기준 commit은 `d1a6703`이다. 인증·organization, snapshot 재사용, semantic cache, usage/quota, Web 인증 화면과 migration `0010`~`0016`이 미커밋 상태다. 기존 사용자 변경을 임의로 되돌리거나 하나의 대형 commit으로 합치지 않는다.

## 2. 실행 순서

### 2.1 변경 목록과 소유권 확정

1. `git status --short`, `git diff --stat`, `git diff --name-status`를 보존한다.
2. 파일별로 사용자 기존 변경, 이번 기능 변경, 생성 artifact, 제외 대상을 표시한다.
3. `.env`, output 문서, 로컬 데이터와 secret은 commit 대상에서 제외한다.
4. 각 기능 commit이 독립적으로 import/build 가능한지 의존 순서를 만든다.

권장 commit 순서는 다음과 같다.

1. Auth·organization·authorization: `core/auth.py`, `core/authorization.py`, `services/identity.py`, API ownership 변경, migration `0010`~`0011`
2. Snapshot reuse·incremental analysis: `snapshot_resolver.py`, `analysis/manifest.py`, `incremental.py`, migration `0012`~`0013`
3. Semantic cache: `semantic_cache.py`, retrieval/chat 연동, migration `0014`
4. Usage·quota·admin: `ai/gateway.py`, `services/usage.py`, usage/admin API, migration `0015`
5. Web auth·account UI: `proxy.ts`, Supabase client/server, auth routes, `AuthForm`, account 화면
6. Backfill·문서·설정: migration `0016`, env examples, README, 배포 준비 문서

### 2.2 migration 검증

- `0010`부터 `0016`까지 revision/down_revision이 단일 head인지 확인한다.
- 빈 PostgreSQL에서 `alembic upgrade head`를 수행한다.
- `0009` 상태의 대표 데이터베이스 복제본에 upgrade하고 backfill 결과와 제약 조건을 검사한다.
- nullable→not-null/unique 전환 전에 orphan, duplicate, legacy row 처리 순서를 검증한다.
- 가능한 migration은 downgrade 또는 별도 복구 SQL을 준비한다. 데이터 변환이 비가역이면 backup restore가 rollback임을 명시한다.
- `alembic current`, `alembic heads`, 핵심 테이블·인덱스 조회 결과를 PR 증빙에 남긴다.

### 2.3 보안·데이터 경계 검토

- `health`, 로그인 callback 외 보호 API가 인증 dependency를 거치는지 route inventory로 검사한다.
- repository/snapshot, chat, learning, deep task, voice에서 URL ID만 신뢰하지 않고 organization ownership을 조회하는지 확인한다.
- SSE와 polling fallback 모두 같은 인증·소유권 규칙을 적용한다.
- `.env`, JWT, database URL, OpenAI/GitHub key, 사용자 이메일이 Git diff·로그·fixture에 없는지 정적 검색한다.
- cache key와 조회 조건에 organization/user scope가 포함되고 공개 snapshot만 전역 공유되는지 검사한다.

### 2.4 자동 검증

루트에서 다음을 실행하고 결과를 SHA와 함께 보관한다.

```powershell
pnpm lint:api
pnpm test:api
pnpm lint:web
pnpm test:web
pnpm build:web
pnpm eval:retrieval --fixture evals/retrieval/p-map.json
pnpm eval:navigation
pnpm eval:architecture
pnpm eval:story
```

추가 integration 검증은 PostgreSQL+pgvector와 Redis를 사용해 수행한다.

- 실제 JWT와 만료·잘못된 audience·key rotation 시나리오
- 동일 SHA 동시 등록의 unique constraint/RQ idempotency
- 30% 경계 전후 증분→전체 분석 전환
- semantic cache tenant 격리와 citation 재검증 실패 시 miss 처리
- reservation 성공/실패/취소/retry 정산과 stale release

### 2.5 브랜치·PR·릴리스 후보

- `codex/` prefix의 배포 준비 branch를 만들고 논리 commit을 순서대로 올린다.
- PR 설명에 migration, 환경변수, feature flag 기본값, 배포·rollback 순서를 적는다.
- required checks와 최소 1회 diff review를 통과한 merge commit 또는 tag를 release candidate SHA로 기록한다.
- 코드 변경이 생기면 전체 검증을 다시 실행해 후보 SHA를 갱신한다.

## 3. 산출물

- 파일별 변경 분류표와 secret scan 결과
- 6개 안팎의 논리 commit과 배포 PR
- `docs/operations/release-checklist.md`
- migration upgrade/backfill/복구 검증 기록
- 배포 후보 commit SHA와 테스트 결과 링크

## 4. 완료 게이트

- [ ] 추적 대상 변경과 제외 대상이 설명되어 있다.
- [ ] migration `0010`~`0016`이 빈 DB와 기존 DB에서 성공한다.
- [ ] API/Web lint, test, production build, 핵심 eval이 통과한다.
- [ ] organization 간 접근 성공이 0건이다.
- [ ] secret·개인정보가 commit과 빌드 산출물에 없다.
- [ ] 논리 commit과 PR review가 완료되었다.
- [ ] 하나의 변경 불가능한 release candidate SHA가 확정되었다.

실패한 검증을 skip하거나 xfail로 바꿔 기준선을 만들지 않는다. 실패 이유가 배포 범위 밖이면 issue, 소유자, 만료일과 함께 명시적인 예외 승인을 받는다.
