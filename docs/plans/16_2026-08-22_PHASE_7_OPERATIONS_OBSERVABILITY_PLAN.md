# Phase 7. 운영 자동화·관측성 강화 계획

- 기준일: 2026-08-22
- 상태: production 직후 시작, 지속 개선
- 목표: 장애·비용·복구 문제를 사용자 신고나 수동 로그 검색 전에 탐지한다.
- 예상 기간: 초기 1~2주, 이후 상시
- 사용자 검토 필요: 알림 채널/수신자, SLO, 로그 보존, RPO/RTO, 자동 차단 권한

## 1. 표준과 지표

API request ID를 RQ job, DB usage event, provider 호출까지 전달한다. 공통 차원은 environment, service, release, endpoint/job type, outcome이다. email, token, 질문 전문은 넣지 않는다. 고유 user/snapshot/repository는 metric label이 아니라 접근 제한 로그/trace에서 찾는다.

| 영역 | 핵심 지표 |
| --- | --- |
| API | request, 4xx/5xx, p50/p95/p99, 401/403/429 |
| Worker | queue depth/age, heartbeat, 처리 시간, retry, failed job |
| 분석 | exact/incremental/full, artifact 재사용률, 실패 단계 |
| Cache | hit/shadow, invalid/citation failure, TTL 삭제 |
| DB/Auth | JWT 실패, connection/storage, slow query, migration head |
| Usage | 비용, reservation age, reject, ledger/provider 차이 |

## 2. 자동화

- stale usage reservation release
- semantic cache TTL cleanup
- daily usage rollup
- provider cost reconciliation
- DB 상태와 RQ registry의 stuck/failed job reconciliation

각 job은 idempotent, advisory lock, 실행 ID, 처리 건수, watermark, 실패 exit code를 제공한다. 연속 실패가 다음 실행의 처리 구간을 영구 누락시키지 않아야 한다.

## 3. 알림과 비용 제어

- allowance 70/90/100% 알림은 중복 방지 key를 사용한다.
- OpenAI 일/월 budget forecast가 상한 전에 운영자를 알린다.
- 자동 차단은 승인된 정책과 quota enforce 이후에만 한다.
- model price 변경은 자동 반영하지 않고 review task를 만든다.

최소 alert는 readiness/5xx, p95/queue age, worker heartbeat/failed job, citation·tenant 이상 1건, stale reservation/원장 차이, DB/Redis 포화, backup/cron/TLS 실패다. alert에 severity, owner, dashboard/runbook, escalation 시간을 연결한다.

## 4. Backup·복구·보안

- backup을 매일 확인하고 분기별 격리 restore drill을 한다.
- restore 뒤 migration, row count, tenant 경계, pgvector와 smoke flow를 검증한다.
- Redis 전체 유실 후 DB pending/running job을 재조정하는 절차를 훈련한다.
- JWT signing key, DB/Redis/OpenAI/GitHub key의 owner·rotation 주기·순서를 기록한다.
- JWKS rotation 중 구/신 token, session refresh, 무중단을 확인한다.
- 접근 권한을 분기별 review하고 역할 변경 시 회수한다.

## 5. 필수 Runbook

`docs/operations/runbooks/`에 다음을 작성한다.

1. API 5xx/latency와 dependency 장애
2. worker 정지, stuck/failed job, Redis 유실
3. migration 실패와 DB restore
4. OpenAI 장애·rate limit·budget
5. quota 오차·이중 과금·stale reservation
6. cache invalid citation/tenant incident
7. JWT/secret rotation
8. Render/Vercel/DNS rollback
9. 개인정보·credential 노출

각 runbook은 탐지, 영향, 즉시 완화, 진단, 복구, 검증, 공지 기준과 owner를 포함한다.

## 6. 훈련과 완료 조건

- 월 1회 staging 장애 주입, 분기 1회 DB restore와 key rotation을 한다.
- alert 수신·acknowledgement·escalation을 확인한다.
- rollback 후 job, reservation, session, DNS를 smoke test한다.
- MTTD/MTTM/MTTR을 기록하고 runbook을 갱신한다.

- [ ] 장애·비용 이상을 alert로 먼저 발견한다.
- [ ] cron이 idempotent하고 연속 실패 알림이 있다.
- [ ] 70/90/100%와 budget alert가 동작한다.
- [ ] DB restore, Redis 복구, JWT rotation을 리허설했다.
- [ ] dashboard→alert→runbook→owner가 연결된다.
- [ ] SLO, RPO/RTO, 보존 기간, 심각도 기준이 승인되었다.

Phase 7은 일회성 종료가 아니라 운영 기준선 확정을 완료 조건으로 삼는다.
