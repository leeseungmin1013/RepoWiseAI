# Production packaging 운영 계약

기준일은 2026-08-25이며 Phase 2 production packaging의 실행 계약과 검증 절차를 기록한다.

## Topology와 실행 명령

API와 worker는 repository root의 동일 Dockerfile과 동일 Git commit으로 빌드한다. USD 10 상한에 따라 Render API는 Singapore free, worker는 Singapore starter, Key Value는 free/noeviction/non-persistent plan을 사용한다. 분석 workspace는 /tmp/repowise/repositories이며 재시작 시 사라지는 작업 공간이다.

| 역할 | 명령 | 종료 계약 |
| --- | --- | --- |
| API | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*" --timeout-graceful-shutdown 240 --no-access-log` | Render가 SIGTERM 후 최대 300초 대기 |
| Worker | `python -m app.workers.runner` | deep queue를 먼저, analysis queue를 다음으로 구독하며 RQ warm shutdown 사용 |
| Migration | `python -m app.migrate` | direct URL 우선, PostgreSQL advisory lock으로 동시 배포 직렬화 |
| Maintenance | `python -m app.workers.maintenance` | advisory lock, JSON summary, 성공 0/실패 1 |
| Local smoke | `powershell -File scripts/container-smoke.ps1 -EnvFile <path>` | build, secret scan, migration, health, worker, maintenance, SIGTERM 확인 |

RQ의 DB 상태가 작업 상태의 source of truth다. process가 강제 종료되면 RQ의 started-job cleanup과 기존 idempotent job ID가 재실행을 제한하며, worker/API 배포 전 migration lock이 schema head를 보장한다.

## Health 계약

- `GET /api/health/live`: event loop/process 확인만 수행하며 dependency 장애에도 200을 반환한다.
- `GET /api/health/ready`: DB `SELECT 1`, Alembic head, Redis `PING`을 확인한다. 하나라도 실패하면 503이다.
- 응답에는 application version과 `RENDER_GIT_COMMIT` 또는 `RELEASE_SHA`만 포함한다. URL과 secret은 포함하지 않는다.
- dependency connect/query timeout 기본값은 2초다.

## 환경변수 매트릭스

| 변수 | API | Worker | Migration | Maintenance | 성격 |
| --- | :---: | :---: | :---: | :---: | --- |
| `DATABASE_URL` | 필수 | 필수 | fallback | 필수 | runtime session-pooler URL |
| `MIGRATION_DATABASE_URL` | pre-deploy | pre-deploy | 우선 | 불필요 | direct DB URL |
| `REDIS_URL` | 필수 | 필수 | 불필요 | 불필요 | Render Key Value 내부 URL |
| `APP_ENV`, `SERVICE_NAME` | 필수 | 필수 | 권장 | 권장 | log identity |
| `RENDER_GIT_COMMIT` / `RELEASE_SHA` | 자동/선택 | 자동/선택 | 자동/선택 | 선택 | release 추적 |
| `CORS_ORIGINS` | 필수 | 불필요 | 불필요 | 불필요 | Vercel 기본 URL |
| `SUPABASE_URL`, issuer, JWKS | 필수 | 필수 | 불필요 | 불필요 | auth 검증 |
| `OPENAI_API_KEY`, `GITHUB_TOKEN` | 필수 | 필수 | 불필요 | 불필요 | server secret |
| `MAINTENANCE_DATABASE_URL` | 불필요 | 불필요 | 불필요 | Actions secret | 최소권한 direct URL |

값은 Render/GitHub environment secret store에만 둔다. `.env`, repository 본문, authorization/cookie/token, DB/Redis URL, 사용자 질문 전문은 image와 기본 log에 넣지 않는다.

## 배포와 검증

1. 동일 release SHA로 API와 worker deploy를 시작한다.
2. 두 서비스의 pre-deploy가 advisory lock을 공유해 migration을 직렬화하고 head까지 올린다.
3. API readiness 200과 release SHA를 확인한다.
4. worker JSON log에서 `repowise-deep-learning`, `repowise-analysis` 순서를 확인한다.
5. 작은 공개 repository를 등록하고 snapshot이 pending→analyzing→ready인지 확인한다.
6. Deep Task를 생성해 queued→running/reasoning→completed 상태와 request/job ID 연결을 확인한다.
7. maintenance workflow를 수동 실행한 뒤 재실행하여 두 삭제·해제 값이 0인지 확인한다.
8. worker/API를 SIGTERM으로 종료하고 started/failed RQ registry, DB task 상태, usage reservation을 확인한다.
9. 잘못된 DB/Redis URL의 별도 local container에서 liveness 200, readiness 503을 확인한다.

## Rollback

기본 rollback은 이전에 검증한 image digest 재배포다. 현재 head `0016`은 ownership backfill과 duplicate fingerprint 변환을 완전히 되돌리지 못하므로 실제 데이터 rollback은 migration downgrade가 아니라 배포 직전 backup/PITR restore 또는 forward-fix다. release checklist에 backup 식별자, 복구 담당자, restore 검증 결과와 이전 image digest를 기록한다.
