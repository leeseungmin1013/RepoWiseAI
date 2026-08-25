# Phase 2. Production 패키징 계획

- 기준일: 2026-08-22
- 상태: 설계 완료, 구현 필요
- 목표: 동일 image로 API, 두 queue를 구독하는 RQ worker, migration, maintenance를 재현 가능하게 실행한다.
- 예상 기간: 2~3일
- 선행 조건: Phase 1 release candidate 또는 검증 가능한 작업 branch

## 1. 구현 대상

| 대상 | 파일/명령 | 요구사항 |
| --- | --- | --- |
| 공용 image | 루트 `Dockerfile` | Python 3.12, `apps/api/uv.lock` 기반 고정 설치, non-root 실행 |
| build context | `.dockerignore` | `.git`, `.env*`, `.data`, node_modules, cache, output 제외 |
| API | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | proxy header, timeout, graceful shutdown |
| Worker | `python -m app.workers.runner` | deep queue 우선, analysis queue 동시 구독 |
| Migration | `alembic -c apps/api/alembic.ini upgrade head` | runtime pooler가 아닌 direct DB URL 사용 가능 구조 |
| Maintenance | `python -m app.workers.maintenance` | JSON summary, 0/비0 exit code, 중복 실행 안전성 |
| Blueprint | `render.yaml` | API, worker, cron과 환경변수 계약 정의 |

## 2. 세부 작업

### 2.1 Docker image

- repository root를 build context로 사용하되 API runtime 파일만 복사한다.
- lockfile을 먼저 복사해 dependency layer cache를 사용하고 production dependency를 고정한다.
- compiler가 필요한 wheel은 builder stage에서 만들고 runtime stage에는 최소 shared library만 둔다.
- `PYTHONUNBUFFERED=1`, 명시적 working directory와 unprivileged user를 설정한다.
- source archive 작업 공간은 ephemeral임을 인정하고 영속 데이터로 취급하지 않는다.
- image에 `.env`, Git history, test output, Supabase/OpenAI key가 들어가지 않는지 검사한다.

### 2.2 실행 진입점과 종료

`app.workers.runner`가 SIGTERM에서 새 job 수신을 멈추고 진행 중 job의 RQ 정책에 맞게 종료되는지 확인한다. API는 Render 종료 유예 시간 안에 HTTP 요청을 마치며 새 connection을 받지 않아야 한다. 장시간 Deep Task와 분석 job은 재시작 뒤 상태가 복구되거나 명확하게 failed/requeued 되어야 한다.

`app.workers.maintenance`에는 다음을 추가한다.

- `main()`과 `if __name__ == "__main__"` 진입점
- 실행 시작/종료 시각과 삭제·해제 건수 출력
- 예외 시 rollback, 구조화 오류 로그, exit code 1
- concurrent cron 실행 시 중복 삭제·정산을 막는 DB advisory lock 또는 동등한 guard

### 2.3 health와 readiness

현재 `/api/health`는 DB와 Redis 실패에도 HTTP 200 + `degraded`를 반환한다. 다음 계약으로 분리하는 방안을 구현한다.

- liveness: process event loop만 확인, dependency 장애로 재시작 폭주를 만들지 않음
- readiness: DB `SELECT 1`, Redis `PING`, migration head 호환을 확인하고 실패 시 HTTP 503
- response에 version/release SHA를 포함하되 secret·내부 URL은 노출하지 않음

Render health check는 readiness 경로를 사용하고, dependency timeout을 짧게 제한한다.

### 2.4 structured logging

- JSON 로그 공통 필드: timestamp, level, service, environment, release, request_id, organization_id(가능한 경우), job_id, task/snapshot id, duration_ms, outcome
- access token, cookie, authorization header, DB/Redis URL, repository source 본문, 사용자 질문 전문은 기본 로그에서 제외한다.
- API `X-Request-Id`를 worker job metadata까지 전달해 enqueue→처리를 추적한다.
- exception은 stack trace와 안정된 error code를 남기되 응답에는 내부 세부사항을 숨긴다.

### 2.5 Render Blueprint

API와 worker는 같은 image/release를 사용한다. `render.yaml`에는 secret 값 대신 환경변수 이름과 `sync: false` 성격의 입력 계약만 둔다. staging/production은 별도 리소스와 환경변수를 사용하고, migration은 배포 전 단일 실행되어 worker/API보다 먼저 schema 호환을 확보해야 한다.

## 3. 로컬 검증 절차

1. image를 clean build하고 이미지 내부 secret 패턴을 검색한다.
2. 새 PostgreSQL/pgvector와 Redis에 연결해 migration을 수행한다.
3. API container를 실행하고 liveness/readiness 200을 확인한다.
4. worker를 실행해 `repowise-deep-learning`, `repowise-analysis` 두 queue 구독을 확인한다.
5. 작은 repository 분석과 Deep Task test job을 enqueue하고 DB 상태 전이를 확인한다.
6. maintenance를 두 번 실행해 두 번째 결과가 안전한 no-op인지 확인한다.
7. API/worker에 SIGTERM을 보내 유실·고아 reservation·중복 과금이 없는지 검사한다.
8. 잘못된 DB/Redis URL에서 readiness 503과 명확한 startup/runtime 로그를 확인한다.

## 4. 산출물과 완료 게이트

- `Dockerfile`, `.dockerignore`, `render.yaml`
- production 실행 명령과 환경변수 매트릭스
- maintenance CLI와 테스트
- liveness/readiness 계약과 container smoke test script
- logging/redaction 설정

- [ ] clean build가 lockfile만으로 재현된다.
- [ ] 새 DB migration 후 readiness가 200이다.
- [ ] worker가 두 queue를 올바른 우선순위로 구독한다.
- [ ] maintenance가 exit code와 JSON summary를 제공한다.
- [ ] SIGTERM·재시작 시 작업과 usage reservation이 일관된다.
- [ ] image와 로그에 secret이 없다.

rollback은 이전 image digest 재배포를 기본으로 하되, 새 코드가 비가역 migration에 의존하면 DB restore 또는 forward-fix 절차를 release checklist에 명시한다.
