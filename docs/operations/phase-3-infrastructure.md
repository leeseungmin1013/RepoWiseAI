# Phase 3 production-like 인프라 운영 기록

- 기준일: 2026-08-25
- 소유자: 프로젝트 소유자
- 적용 결정: cloud production-like 1개, local/ephemeral staging, 월 USD 10 상한
- secret 기록 원칙: 이 문서에는 값·project ref·URL·token·password를 기록하지 않는다.

## 리소스 계약

| 리소스 | 이름 | 권역/plan | 내구성 | 접근 |
| --- | --- | --- | --- | --- |
| Supabase Auth/PostgreSQL | 기존 RepoWiseAI project | Mumbai(ap-south-1), Free | provider 자동 backup/PITR 없음 | API/worker runtime pooler, migration/backup direct URL |
| local staging PostgreSQL | docker-compose postgres | local, pgvector pg17 | Docker volume | localhost only |
| local staging Redis | docker-compose redis | local, Redis 7 | AOF volume | localhost only |
| Render Key Value | repowise-queue | Singapore, Free | persistence off, 재시작 시 전량 소실 가능 | 외부 IP 차단, Render 내부 URL |
| Render API | repowise-api | Singapore, Free | stateless | HTTPS public |
| Render worker | repowise-worker | Singapore, Starter | stateless | private outbound |

Render에는 전체 청구액 hard cap이 없다. build pipeline 추가 spend limit은 USD 0으로 설정하고 API/worker는 각각 1 instance, preview off, autoscaling off로 고정한다. 포함량을 넘은 outbound bandwidth 추가 과금 가능성은 프로젝트 소유자가 승인한 임시 예외다. 월 비용이 USD 10에 도달하기 전에 billing 알림을 확인하고 유료 worker를 suspend한다.

이 통제는 초과 청구를 기술적으로 완전히 차단하지 못하므로 billing page를 정기 확인한다.

Render Key Value는 queue 용도이므로 maxmemoryPolicy=noeviction을 사용한다. memory full에서는 기존 job을 제거하지 않고 신규 write가 실패한다. DB의 AnalysisJob/DeepTask가 작업 상태의 source of truth다.

## Supabase 설정

2026-08-25 프로젝트 소유자 승인으로 새 Seoul project 대신 기존 RepoWiseAI Free project(Mumbai, ap-south-1)를 재사용한다. 이는 동일 권역 원칙의 임시 예외이며 Render Singapore와의 cross-region latency 가능성을 수용한다. 새 project 생성 비용과 운영 분산은 피하고, latency가 운영 SLO를 충족하지 못하면 Seoul 이전을 재검토한다.

1. 기존 RepoWiseAI project의 강한 DB password를 password manager에 보관하고 접근자를 제한한다.
2. vector extension을 활성화하고 migration 계정이 extension 생성·DDL·advisory lock을 실행할 수 있는지 확인한다.
3. local migration은 direct connection URL을 사용한다. Render와 IPv4-only Docker backup은 Supabase 권장 session pooler URL(5432)을 사용한다. Render는 IPv4-only이므로 worker의 MIGRATION_DATABASE_URL도 session pooler로 설정하며, session mode의 전용 연결에서 DDL과 advisory lock을 실행한다.
4. API/worker DATABASE_URL에는 SQLAlchemy sync psycopg가 사용할 session pooler URL을 사용한다. transaction pooler는 advisory lock 계약과 맞지 않으므로 사용하지 않는다.
5. Auth에서 email/password, email confirmation, password reset을 활성화한다. Google/GitHub OAuth는 2026-08-25 현재 Client ID/Secret이 없어 보류하며 자격 증명 확보 후 활성화한다.
6. asymmetric signing key를 current로 두고 audience=authenticated, issuer, JWKS URL을 server secret store에 설정한다.
7. local redirect는 http://localhost:3000/auth/callback 및 forgot-password 흐름을 허용한다. Vercel production URL이 생기면 해당 origin의 /auth/callback과 /forgot-password만 추가한다.
8. 브라우저에는 NEXT_PUBLIC_SUPABASE_URL과 publishable key만 제공한다. secret/service-role key는 만들거나 배포할 필요가 없다.

## Render Blueprint

render.yaml은 repowise-queue를 free, noeviction, persistence off, ipAllowList=[]로 선언한다. API와 worker의 REDIS_URL은 fromService.connectionString으로 연결되어 외부 URL을 사용하지 않는다.

API free plan은 pre-deploy command를 지원하지 않는다. migration은 유료 starter worker의 preDeployCommand가 direct URL과 advisory lock으로 실행한다. API readiness는 DB schema head가 0016이 아니면 503을 반환한다.
2026-08-25 임시 배포는 로컬 OPENAI_API_KEY를 Render secret으로 저장하고 GITHUB_TOKEN 없이 public repository만 분석한다. private repository 지원은 별도 GitHub token을 발급한 뒤 활성화한다.


worker 시작 시 app.workers.queue_recovery.recover_queue_jobs가 다음을 수행한다.

- queued AnalysisJob/DeepTask를 deterministic RQ job ID로 idempotent하게 enqueue
- timeout보다 긴 stale window를 넘긴 running/reasoning 작업만 queued로 되돌린 뒤 enqueue
- PostgreSQL advisory lock과 row skip-locked로 여러 worker의 중복 복구 방지
- 완료·실패·취소 작업은 건드리지 않음

수동 실행:

    uv run --project apps/api --locked python -m app.workers.queue_recovery

## 매일 수동 logical backup

백업 담당자는 매일 session pooler URL을 MIGRATION_DATABASE_URL로 현재 shell 환경에만 설정하고, 암호화된 외장/동기화 저장소를 OutputDirectory로 지정한다.

    $env:MIGRATION_DATABASE_URL = '<direct-url>'
    powershell -File scripts/backup-supabase.ps1 -OutputDirectory 'E:\RepoWiseBackups\daily'
    Remove-Item Env:MIGRATION_DATABASE_URL

스크립트는 pgvector/pgvector:pg17 컨테이너의 pg_dump로 custom-format archive를 만들고 pg_restore --list로 구조를 검증한다. 같은 위치에 SHA-256, 크기, 생성 시각 manifest를 만든다. dump와 manifest는 Git에 넣지 않는다.

보존안:

- daily 7개
- weekly 4개
- quarterly restore drill에 성공한 archive 4개
- 삭제는 저장소 소유자가 checksum과 보존 세대를 확인한 뒤 수행

## 분기별 restore drill

    powershell -File scripts/restore-drill.ps1 -BackupFile 'E:\RepoWiseBackups\daily\repowise-YYYYMMDDTHHMMSSZ.dump'

archive에는 Supabase 관리 스키마와 application public 스키마가 함께 들어 있다. 일반 pgvector PostgreSQL에는 supabase_vault 같은 platform extension이 없으므로 drill은 pgcrypto와 archive column type에 맞춘 public.vector를 먼저 만들고 public만 복원한다. alembic head=0016, vector extension, vector distance query를 확인한 뒤 임시 컨테이너를 제거한다. auth/storage/vault까지 포함한 platform 전체 복구는 새 Supabase project를 대상으로 별도 수행한다. 결과 JSON과 대상 archive checksum을 release 기록에 남긴다.

## 완료 검증

- [x] 기존 Supabase production-like project가 Mumbai(ap-south-1)/Free로 확인되고 지역 예외가 승인됨
- [ ] email confirmation, reset, Google/GitHub OAuth, asymmetric key/JWKS가 설정됨
- [ ] direct migration과 session pooler runtime URL이 각 secret store에 분리 저장됨
- [ ] migration 0016, vector extension/index/query가 성공함
- [ ] Render repowise-queue가 Singapore/Free/noeviction/off/외부 차단으로 생성됨
- [ ] 두 RQ queue enqueue/dequeue 및 DB 완료 상태 round trip이 성공함
- [ ] Redis flush 후 queued/stale job 재큐잉 smoke test가 성공함
- [ ] 정상·만료·잘못된 audience·다른 issuer token 검증이 성공함
- [ ] 최초 인증의 user/personal organization/membership bootstrap이 idempotent함
- [ ] 실제 production-like dump 1개와 restore drill이 성공함
- [ ] client bundle/API/log secret scan이 성공함

credential 노출 시 해당 환경 DB password 또는 signing/OAuth key를 회전하고 API/worker/Web을 재배포한다. queue 소실은 credential 사고가 아니며 DB 기반 복구를 먼저 실행한다.

## 2026-08-25 local/기존 Auth 검증 기록

| 검증 | 결과 |
| --- | --- |
| 격리 PostgreSQL migration | 0001부터 0016_backfill_and_constraints까지 성공 |
| pgvector | extension 0.8.5, distance query 성공 |
| RQ round trip | repowise-analysis와 repowise-deep-learning 모두 finished |
| Key Value 소실 시뮬레이션 | Redis 전량 초기화 후 DB queued 작업 2개 재큐잉 성공 |
| stale 복구 | analysis running과 deep reasoning을 stale 처리 후 queued 재큐잉 성공 |
| logical backup | custom-format dump 179432 bytes와 SHA-256 manifest 생성 성공 |
| restore drill | 임시 pgvector DB 복원, migration 0016, vector query 성공 |
| 기존 Supabase Auth | password login, 실제 JWKS 승인, identity bootstrap 2회 idempotency 성공 |
| 인증 negative | 무토큰 401, 변조 signature 401 성공 |
| 회귀 테스트 | API 163 passed, Web 102 passed, lint 성공 |

위 Supabase 결과는 기존 Phase 1 테스트 프로젝트에 대한 검증이다. 해당 프로젝트를 production-like로 재사용할지 새 프로젝트를 만들지는 프로젝트 소유자 확인 전까지 완료 처리하지 않는다.
