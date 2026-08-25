# Phase 1 검증 기록

- 실행일: 2026-08-25 (Asia/Seoul)
- branch: `codex/repository-structure-visualization`
- base SHA: `d1a6703`
- release candidate SHA: 미확정
- 판정: **기술 검증 통과 — migration, snapshot eval, Redis/RQ, 실제 JWT·동시성·signing-key 회전 완료; commit/PR/RC 확정 대기**

RC는 아직 확정하지 않는다. 아래 성공 결과는 현재 working tree에 대한 로컬 결과이며 불변 commit SHA에 연결되지 않았다.

## 완료된 검증

| 영역 | 명령 | 결과 |
| --- | --- | --- |
| API lint | `pnpm lint:api` | 성공 |
| API test | `uv run --project apps/api pytest -q --basetemp tmp/pytest-phase1-jwt-final` | 성공, 153 passed, warning 1 |
| Web lint | `pnpm lint:web` | 성공 |
| Web test | `pnpm test:web` | 성공, 20 files / 102 tests |
| Web production build | `pnpm build:web` | 성공, `/`, `/account`, auth routes 생성 |
| Alembic head | `alembic heads` | 성공, `0016_backfill_and_constraints` 단일 head |
| Alembic history | `alembic history -r 0009_navigation_change_briefs:head` | 성공, `0010`~`0016` 선형 chain |
| Offline migration compile | `alembic upgrade head --sql` | 성공, `0001`~`0016` SQL 생성 |
| Fresh PostgreSQL migration | 임시 `pgvector/pgvector:pg17` DB에서 `upgrade head` | 성공, version `0016`, vector extension, 핵심 index 4개 |
| Migration downgrade/re-upgrade | fresh DB `0016 → 0009 → 0016` | 성공 |
| Legacy data backfill | 별도 `0009` DB에 profile/chat/task와 duplicate snapshot seed 후 `upgrade head` | 성공, orphan 0, canonical mapping 1, duplicate identity 0 |
| Compose runtime | `docker compose up -d postgres redis`, `pnpm db:migrate` | PostgreSQL/Redis healthy, DB head migration 성공 |
| 실제 RQ worker 분석 | 로컬 embedding provider로 p-map/RepoWiseAI 신규 snapshot enqueue·consume | 두 snapshot 모두 `ready`, RQ 지원 문자만 쓰는 deterministic job ID 회귀 수정 |
| Retrieval eval | `pnpm eval:retrieval --fixture evals/retrieval/p-map.json --snapshot-id snap_bac3f9c7743742ebbcde162ccb61a9f1` | 성공, recall@k 1.0, MRR 0.8667, 5 cases |
| Navigation eval | `pnpm eval:navigation --snapshot-id snap_4eb84f4201a34abebb21b9b4818d9c4f` | 성공, feature/step recall 1.0, verified precision 1.0 |
| Architecture eval | `pnpm eval:architecture --snapshot-id snap_4eb84f4201a34abebb21b9b4818d9c4f` | 성공, node/edge/feature mapping 1.0, noise ratio 0.0455, evidence 1.0 |
| Supabase issuer/JWKS | root `.env`의 `SUPABASE_URL`에서 파생한 공개 JWKS 조회 | HTTP 200, ES256 key 1개 |
| 실제 Supabase JWT | password login·refresh·JWKS 서명 검증·보호 API 호출 | 정상 JWT 200, 무토큰/변조/audience/만료 401, 타 organization 403, identity bootstrap 성공 |
| 인증된 동일 SHA 병렬 등록 | RepoWiseAI 등록 2요청 동시 실행 | 최초 organization link unique race 재현·수정 후 202/202, 동일 snapshot, `exact_snapshot`, identity row 1 |
| Supabase signing-key 회전·폐기 | ES256 standby→current 회전 후 previous key revoke | kid 변경, 전환 중 old/new 200, 폐기 후 JWKS 신규 키 1개·old 로컬 401/Supabase 403·new 200 |
| Repository Story eval | `pnpm eval:story` | p-map·RepoWiseAI 모두 성공, 모든 threshold 통과 |
| whitespace | `git diff --check` | 오류 없음; Windows LF→CRLF 경고만 존재 |
| high-confidence secret scan | `rg` key/JWT/private-key 패턴 | 실제 secret 없음 |
| email scan | source/docs/evals/scripts 전체 | 실사용자 이메일 없음 |

API test의 warning은 Starlette `TestClient`가 `httpx` 대신 `httpx2` 설치를 권고하는 dependency deprecation warning이다. 테스트 실패나 skip은 없다.

## 보안·데이터 경계 구현 결과

이번 기준선 검토에서 다음을 수정하고 회귀 테스트를 추가했다.

- debug retrieval run 조회가 admin role뿐 아니라 연결된 chat session의 organization/user ownership을 확인한다.
- admin usage reconciliation이 현재 organization의 reservation/event/cache만 집계한다.
- usage settlement가 현재 organization에 속하지 않은 reservation ID를 거부한다.
- model price history가 여러 행일 때 usage type별 최신 effective row만 과금한다.
- bonus grant와 audit event가 하나의 transaction으로 commit되도록 service 내부 조기 commit을 제거했다.
- health 외 모든 API router에 auth dependency가 존재하는지 inventory test로 고정했다.
- `shadow` quota 모드는 feature limit 초과를 `shadow_exceeded`로 기록하되 요청을 차단하지 않는다.
- 승인 기본값을 월 `250000` micro-USD와 realtime `300`초로 API/Web/환경 예제에 일치시켰다.
- `pnpm eval:navigation`이 인자 없이 RepoWiseAI 기본 fixture를 읽도록 CLI 기본값을 수정했다.
- RQ 2.x가 거부하는 colon 포함 repository analysis job ID를 dash 기반 ID로 수정했다.
- snapshot commit에 따라 달라지는 feature flow ID를 골드 픽스처가 고정 비교하지 않도록 architecture/story eval을 근거·고유 흐름 수 기준으로 수정했다.
- architecture eval이 threshold 실패 시 종료 코드 1을 반환하도록 수정했다.

## secret·개인정보 scan 예외 검토

고신뢰 key scan에서 다음 문자열만 발견했고 모두 redaction 동작을 확인하기 위한 고정 테스트 sentinel이다.

- `apps/web/src/components/ProjectMapPanel.test.tsx`: `sk-this-must-never-render`

이메일 scan에서 발견된 `example.com` 값은 URL credential/query redaction을 검증하는 fixture다.

- `apps/api/tests/test_feature_flow.py`
- `apps/api/tests/test_typescript_analysis.py`

실제 `.env`는 검사·commit 대상에서 제외했고 값은 이 기록에 복사하지 않았다.

## 미완료 릴리스 작업

| 작업 | 상태 | blocker | 해제 후 실행 |
| --- | --- | --- | --- |
| 논리 commit·PR·RC SHA | 대기 | working tree가 아직 불변 commit에 연결되지 않음 | 변경 분류표대로 commit 후 최종 SHA에서 검증·review |

Docker Desktop의 compose PostgreSQL/Redis를 시작하고 head migration을 적용했다. 새 분석 snapshot은 다음과 같다.

- p-map: `snap_bac3f9c7743742ebbcde162ccb61a9f1`, commit `bc26cf03f81292325236a1188063dac8e7a4de0f`, 10 files / 59 chunks
- RepoWiseAI: `snap_4eb84f4201a34abebb21b9b4818d9c4f`, commit `cb78164fc6cc3212a671412956079fea9f273040`, 196 files / 1880 chunks

숨김 RQ worker는 검증 후 종료하고 PostgreSQL/Redis는 후속 integration을 위해 healthy 상태로 유지한다. `.env` 값 자체는 기록하거나 출력하지 않았다.

## RC 확정 조건

1. 위 미완료 항목이 모두 성공한다.
2. 변경을 6개 안팎의 논리 commit으로 분리하고 각 commit SHA를 기록한다.
3. 전체 검증을 최종 commit에서 다시 실행한다.
4. required checks와 diff review가 완료된다.
5. 최종 40자 SHA, CI URL, DB 증빙, 검토자를 `release-checklist.md` 형식으로 기록한다.
