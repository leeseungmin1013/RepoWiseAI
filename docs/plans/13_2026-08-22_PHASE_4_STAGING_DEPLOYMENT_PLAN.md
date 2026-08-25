# Phase 4. Staging 전체 배포·통합 검증 계획

- 기준일: 2026-08-22
- 상태: Phase 1~3 완료 후 실행
- 목표: production과 같은 topology를 staging에 배포하고 인증·권한·분석·캐시·비용·복구 흐름을 E2E 검증한다.
- 예상 기간: 3~5일
- 사용자 검토 필요: staging 접근 범위, 테스트 계정, 테스트할 실제 GitHub 저장소

## 1. 배포 순서

1. release candidate SHA와 image digest를 고정한다.
2. backup 확인 후 direct DB URL로 `alembic upgrade head`를 단일 실행한다.
3. Render API를 배포하고 readiness 200을 확인한다.
4. 같은 image로 worker를 배포해 두 queue 구독을 확인한다.
5. maintenance cron을 배포하고 첫 실행은 수동 검토한다.
6. Vercel staging Web을 배포한다.
7. Supabase callback, Web API URL, API CORS를 staging URL로 연결한다.

## 2. 기준 설정

```dotenv
APP_ENV=staging
AUTH_REQUIRED=true
EXACT_SNAPSHOT_REUSE_ENABLED=true
INCREMENTAL_ANALYSIS_ENABLED=true
SEMANTIC_CACHE_WRITE_ENABLED=true
SEMANTIC_CACHE_READ_ENABLED=true
SEMANTIC_CACHE_SHADOW_MODE=true
QUOTA_ENFORCEMENT_MODE=off
NAVIGATION_LLM_LABELS_ENABLED=false
```

shadow mode에서는 cache 후보·검증 지표만 기록하고 사용자 응답을 대체하지 않도록 테스트로 고정한다. `off`의 의미는 비용 원장은 기록하되 quota로 차단하지 않는 것으로 통일하는 것을 권장한다.

## 3. Smoke test

- readiness, release SHA, DB migration head, Redis ping, worker heartbeat 확인
- 이메일 가입·확인·로그인·로그아웃·비밀번호 재설정
- Bearer token 전달과 personal organization의 idempotent bootstrap
- 작은 공개 저장소 등록과 pending→analyzing→ready 상태 전이
- account/usage가 현재 organization 데이터만 표시하는지 확인

## 4. 통합 검증

### 4.1 인증·권한

- 익명 사용자는 health 외 보호 endpoint에서 401을 받는다.
- 만료 token은 refresh 1회 뒤 실패 시 로그인으로 이동한다.
- 사용자 A가 B의 repository, chat, learning, Deep Task, usage를 ID 추측으로 접근하지 못한다.
- SSE, polling fallback, Realtime offer도 동일 ownership을 강제한다.
- admin API는 일반 사용자에게 403이고 debug endpoint는 비활성이다.

### 4.2 분석 재사용

1. 새 SHA의 full 분석을 완료한다.
2. 같은 SHA를 반복·동시 등록해 같은 snapshot/job을 반환하는지 확인한다.
3. 1파일 변경에서 manifest diff, base snapshot, reuse metrics를 확인한다.
4. 변경률 29%, 30%, 31%에서 증분/full 경계를 검증하고 비교 연산 규칙을 기록한다.
5. parser/embedding fingerprint가 바뀌면 같은 SHA도 과거 artifact를 재사용하지 않는지 확인한다.

### 4.3 Semantic cache

- 동일·유사 질문의 후보, similarity, citation 재검증 결과를 기록한다.
- selection, learning context, intent, model/prompt version이 다르면 안전한 miss인지 확인한다.
- 다른 organization의 생성 답변이 후보나 응답으로 노출되지 않는지 검사한다.
- TTL 만료·invalid citation은 오류가 아닌 miss로 처리한다.

### 4.4 Usage·quota

- embedding, answer, Deep Task, research, label, Realtime이 공통 원장에 기록되는지 확인한다.
- 외부 호출 전 reservation, 성공 후 실제 usage 정산, 실패·취소 후 release를 검증한다.
- client/API/RQ retry에서 idempotency key로 이중 과금이 없는지 확인한다.
- cache hit 비용 0, stale reservation 정리 전후 금액을 확인한다.

### 4.5 장애·복구

- job 중 worker 재시작 후 DB/RQ 상태 복구
- OpenAI 429/5xx/timeout에서 reservation release
- Redis/DB 일시 장애에서 readiness와 제한된 retry
- SSE 단절 뒤 polling fallback·재연결·취소
- cron 중복 실행의 idempotency

## 5. 증빙과 완료 게이트

각 시나리오에 release SHA, 마스킹한 test organization, request/job ID, 기대/실제 결과와 issue를 남긴다. 최소 24시간 soak 동안 5xx, p95, queue depth, failed jobs, DB connection과 비용을 본다.

- [ ] 핵심 E2E가 통과한다.
- [ ] 권한 우회와 secret 노출이 0건이다.
- [ ] reuse/full 경계와 cache shadow가 설명 가능하다.
- [ ] 실패·취소·retry에서 작업·reservation이 복구된다.
- [ ] 24시간 동안 미해결 P0/P1이 없다.
- [ ] production 배포와 rollback을 staging에서 리허설했다.

권한 우회, secret 노출, 데이터 손상, 이중 과금은 즉시 production 차단 사유다.
