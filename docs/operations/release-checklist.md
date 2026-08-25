# Phase 1 릴리스 기준선 체크리스트

- 기준일: 2026-08-22
- 기준 branch: `codex/repository-structure-visualization`
- 기준 commit: `d1a6703`
- 현재 상태: 코드 검증 완료, PostgreSQL integration 검증 대기
- 관련 계획: `docs/plans/10_2026-08-22_PHASE_1_RELEASE_BASELINE_PLAN.md`
- 변경 분류: `docs/operations/phase-1-change-inventory.md`
- 실행 증빙: `docs/operations/phase-1-validation-record.md`

이 문서는 release candidate를 고정하기 전에 반드시 끝내야 하는 실행 절차다. 실패한 항목은 skip이나 xfail로 바꾸지 않는다. DB·외부 서비스가 없어 실행하지 못한 항목은 `미실행`으로 남기며 RC를 확정하지 않는다.

## 1. 작업 트리 동결

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff --name-status
git diff --check
```

확인 사항:

- `output/project-status/*.docx`, `.env`, `.data/`, `.pytest-tmp/`, `tmp/`는 commit하지 않는다.
- 기존 사용자 변경을 되돌리거나 자동 포맷으로 무관한 파일을 다시 쓰지 않는다.
- 새 변경이 생기면 분류표와 검증 SHA를 갱신한다.
- `git diff --check`가 whitespace 오류 없이 끝나야 한다.

## 2. 논리 commit 경계

다음 순서를 유지한다. 각 commit 직후 `pnpm lint:api`, `pnpm test:api`, 해당 Web 검증을 실행해 독립 import/build 가능성을 확인한다.

1. `auth-organization-authorization`: 인증, identity, ownership 모델/API, migration `0010`~`0011`, tenant 보안 테스트
2. `snapshot-incremental-analysis`: snapshot resolver, manifest, artifact cache, incremental worker, migration `0012`~`0013`
3. `semantic-cache`: semantic cache와 retrieval/chat 연결, migration `0014`
4. `usage-quota-admin`: provider gateway, usage ledger, usage/admin API, maintenance, migration `0015`
5. `web-auth-account`: proxy, Supabase client/server, auth routes/form, account UI
6. `backfill-release-docs`: migration `0016`, 환경 예제, README, operations 문서와 계획

한 파일에 여러 기능이 섞인 경우 전체 파일을 임의로 한 commit에 넣지 말고 `git add -p`로 hunk를 검토한다. 커밋 전 staged diff에 대해 아래를 실행한다.

```powershell
git diff --cached --check
git diff --cached --stat
git diff --cached --name-status
```

## 3. migration 검증

### 3.1 정적·offline 검증

```powershell
uv run --project apps/api alembic -c apps/api/alembic.ini heads
uv run --project apps/api alembic -c apps/api/alembic.ini history -r 0009_navigation_change_briefs:head
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head --sql > tmp/alembic-head.sql
```

기대값은 head 하나(`0016_backfill_and_constraints`)다.

### 3.2 빈 PostgreSQL

검증 전용 빈 DB를 만들고 `DATABASE_URL`을 그 DB로 설정한다. 공유·production DB에 실행하지 않는다.

```powershell
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini current
uv run --project apps/api alembic -c apps/api/alembic.ini heads
```

검사 SQL:

```sql
SELECT version_num FROM alembic_version;
SELECT extname FROM pg_extension WHERE extname = 'vector';
SELECT indexname FROM pg_indexes
WHERE indexname IN ('uq_snapshot_identity', 'uq_semantic_cache_exact_scope',
                    'uq_usage_event_idempotency', 'uq_usage_reservation_idempotency');
```

### 3.3 `0009` 대표 데이터 upgrade

1. production dump가 아닌 비식별 대표 복제본을 검증 전용 DB에 복원한다.
2. `alembic current`가 `0009_navigation_change_briefs`인지 확인한다.
3. row count와 중복 수를 기록한 뒤 `upgrade head`를 실행한다.
4. 다음 결과가 모두 `0`이어야 한다.

```sql
SELECT count(*) FROM learner_profiles
WHERE user_id IS NULL OR organization_id IS NULL;
SELECT count(*) FROM chat_sessions
WHERE user_id IS NULL OR organization_id IS NULL;
SELECT count(*) FROM deep_tasks
WHERE user_id IS NULL OR organization_id IS NULL;
SELECT count(*) FROM repository_snapshots
WHERE analysis_fingerprint IS NULL;
SELECT count(*)
FROM (
  SELECT repository_id, commit_sha, analysis_fingerprint
  FROM repository_snapshots
  WHERE commit_sha IS NOT NULL AND analysis_fingerprint IS NOT NULL
  GROUP BY 1, 2, 3 HAVING count(*) > 1
) duplicates;
```

추가 확인:

```sql
SELECT count(*) FROM organization_repositories WHERE organization_id = 'org_legacy';
SELECT count(*) FROM snapshot_canonical_mappings;
SELECT status, count(*) FROM repository_snapshots GROUP BY status ORDER BY status;
```

### 3.4 rollback

- `0010`~`0015`의 downgrade는 생성 schema를 제거하므로 검증 DB에서만 실행한다.
- `0016` downgrade는 unique index와 mapping table을 제거하지만 legacy ownership backfill과 duplicate snapshot fingerprint 변환을 원복하지 않는다.
- 따라서 `0016`이 적용된 실제 데이터의 rollback은 migration downgrade가 아니라 적용 직전 backup/PITR restore다.
- 배포 전 backup 식별자, 생성 시각, 복구 담당자, restore 검증 결과를 PR에 기록한다.

## 4. 인증·tenant 경계

- `/api/health`만 anonymous로 유지한다.
- 나머지 router는 `authorize_scope` 또는 `require_admin` dependency를 가져야 한다.
- repository/snapshot, chat/message/retrieval run, learner/profile/path/session, deep task, usage/admin 경로에서 organization 또는 user ownership을 확인한다.
- SSE와 polling endpoint는 동일한 `task_id` ownership 검사를 사용한다.
- admin reconciliation은 현재 organization으로만 집계한다.
- semantic generation cache는 organization scope이며 public retrieval cache만 `public` scope를 허용한다.

검증:

```powershell
uv run --project apps/api pytest -q apps/api/tests/test_cache_auth_usage_plan.py
rg -n "include_router|authorize_scope|require_admin" apps/api/app/api/router.py
rg -n "ensure_(organization|repository|snapshot|chat|learning|deep_task|profile).*access" apps/api/app
```

## 5. secret·개인정보 검사

검사는 tracked diff와 untracked source/config 파일 모두를 대상으로 한다. 발견 문자열을 증빙 문서나 CI log에 복사하지 않고 파일·줄 위치만 기록한다.

```powershell
git diff --check
rg -n --hidden -g '!node_modules/**' -g '!.git/**' -g '!output/**' -g '!*.lock' `
  '(sk-(proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|postgres(ql)?://[^[:space:]]+:[^[:space:]@]+@)' .
```

허용 항목은 placeholder뿐이다. 실제 `.env`, JWT, database URL, OpenAI/GitHub key, 실사용자 이메일은 diff·fixture·log에 없어야 한다.

## 6. 자동 검증

```powershell
pnpm lint:api
uv run --project apps/api pytest -q --basetemp tmp/pytest-phase1
pnpm lint:web
pnpm test:web
pnpm build:web
pnpm eval:retrieval --fixture evals/retrieval/p-map.json
pnpm eval:navigation
pnpm eval:architecture
pnpm eval:story
```

DB 기반 eval은 ready snapshot이 있는 PostgreSQL을 요구한다. fixture가 기대하는 repository snapshot이 없으면 실패로 기록하고 먼저 검증 fixture DB를 복원한다.

추가 integration 시나리오:

- 정상·만료·잘못된 issuer/audience JWT, 미등록 JWKS key
- 동일 SHA 동시 등록의 unique constraint와 RQ idempotency
- file/byte change ratio 30% 경계의 incremental/full 전환
- semantic cache organization 격리와 citation 재검증 실패 miss
- reservation reserve/settle/release/retry/stale release와 다른 organization reservation 거부
- 과거·현재 model price가 함께 있을 때 usage type별 최신 단가만 적용

## 7. PR과 release candidate

PR 본문에 다음을 포함한다.

- 기준 SHA와 6개 commit 목록
- migration 순서, 빈 DB/`0009` upgrade 결과, backup/rollback
- 추가·변경 환경변수와 feature flag 기본값
- 배포 순서: DB expand/backfill → API/worker → Web → smoke test
- rollback 순서와 irreversible data migration 경고
- 각 검증 명령의 종료 코드와 CI 링크
- 남은 예외의 issue, 소유자, 만료일, 승인자

RC는 모든 필수 검증이 성공한 뒤에만 기록한다.

```text
release_candidate_sha: <40-char SHA>
verified_at_utc: <ISO-8601>
verified_by: <name>
reviewed_by: <name>
ci_run: <URL>
database_evidence: <URL or artifact path>
```

코드나 migration이 바뀌면 위 기록을 폐기하고 전체 검증 후 새 SHA를 발급한다.
