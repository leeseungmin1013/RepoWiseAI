# Phase 3. Supabase·Redis 인프라 구축 계획

- 기준일: 2026-08-22
- 상태: Phase 0 승인 후 실행
- 목표: staging/production에 완전히 분리된 Auth·PostgreSQL/pgvector·Redis를 만들고 애플리케이션 연결을 검증한다.
- 예상 기간: 1~2일
- 선행 조건: region·예산 결정, Phase 2 실행 계약

## 0. 2026-08-25 승인 예외와 실행 기준

이 절은 2026-08-25 프로젝트 소유자의 승인을 반영하며, 아래 항목에 한해 본 계획의 staging/production 완전 분리·Redis persistence·Supabase PITR 요구보다 우선한다.

- cloud에는 production-like 환경 하나만 둔다. staging은 local Docker Compose 또는 배포 시점의 ephemeral 환경으로 운영하며 production credential을 사용하지 않는다.
- 새 Seoul project를 만들지 않고 2026-08-25 확인된 기존 RepoWiseAI Supabase project(ap-south-1, Mumbai, Free)를 production-like 환경으로 재사용한다. 이는 Phase 0의 Seoul 동일 권역 원칙에 대한 승인된 지역 예외이며, Render Singapore와의 cross-region latency 가능성을 임시로 수용한다.
- Supabase 무료 plan에 없는 자동 backup/PITR 대신 매일 수동 logical custom-format dump와 checksum을 만들고, 분기마다 격리된 pgvector PostgreSQL에서 restore drill을 수행한다.
- Render는 Singapore의 무료 Key Value 하나를 사용한다. maxmemoryPolicy=noeviction, persistenceMode=off, 외부 IP 차단, 내부 URL 연결을 적용한다.
- Key Value 인스턴스가 재시작·점검·업그레이드되면 모든 RQ 데이터가 사라질 수 있음을 승인된 임시 위험으로 수용한다. API/worker 프로세스만 재시작되고 Key Value가 유지되는 경우에는 이 위험이 발생하지 않는다.
- queue 복구의 source of truth는 PostgreSQL의 AnalysisJob과 DeepTask다. worker 시작 시 queued 작업과 timeout을 넘긴 running 작업을 deterministic job ID로 다시 enqueue한다.
- 월 총예산 상한은 USD 10을 유지한다. Render API는 free, worker는 starter, Key Value와 Supabase는 free를 기준으로 한다.
- Render는 월 전체 청구액 hard cap을 제공하지 않음을 확인했다. build pipeline 추가 spend limit은 USD 0으로 설정하고 API/worker를 각각 1 instance, preview off, autoscaling off로 고정한다. 결제수단 등록 시 포함량을 넘은 outbound bandwidth에 소액 추가 과금될 가능성은 2026-08-25 프로젝트 소유자가 승인한 예외로 수용하되, 월 USD 10 도달 전에 billing 알림을 확인하고 서비스를 suspend한다.
- 백업 dump에는 사용자 데이터와 secret 성격의 내용이 포함될 수 있으므로 Git에 넣지 않고 접근 통제된 외장 또는 암호화 저장소에 보관한다.
- Render는 IPv4-only이므로 Supabase direct IPv6 endpoint 대신 session pooler(5432)를 runtime과 migration에 사용한다. session mode의 전용 연결에서 Alembic DDL과 advisory lock을 실행한다.
- Google/GitHub OAuth는 Client ID/Secret 미보유로 보류하고 email/password를 우선 사용한다. Render에는 승인된 OPENAI_API_KEY만 저장하며 GITHUB_TOKEN 없이 public repository 분석만 제공한다.

예외 해제 조건은 월 예산 상향 승인이다. 해제 시 우선순위는 production Key Value의 유료 persistent plan 전환, Supabase 자동 backup, cloud staging 분리, PITR 순이다.

## 1. 리소스 원칙

- staging과 production은 Supabase project, Render Key Value, password, URL, JWT 설정을 공유하지 않는다.
- 모든 리소스는 Phase 0에서 선택한 동일 권역에 둔다.
- 값은 GitHub/Vercel/Render의 환경별 secret store에 저장하고 문서에는 이름과 소유자만 적는다.
- migration은 direct connection URL, API/worker runtime은 호환되는 session pooler URL을 사용한다. SQLAlchemy의 sync psycopg, pgvector, transaction/advisory lock 요구와 pooler mode의 호환성을 검증한다.

## 2. Supabase 구축

### 2.1 프로젝트와 데이터베이스

1. staging, production project를 명명 규칙에 따라 생성한다.
2. 강한 database password를 password manager에 저장하고 접근자를 제한한다.
3. `vector` extension과 migration에 필요한 extension/권한을 확인한다.
4. direct migration URL과 runtime pooler URL을 각각 발급한다.
5. staging에 `0016`까지 migration하고 `alembic current`와 주요 index를 확인한다.
6. production backup/PITR 보존, RPO/RTO, 복구 담당자를 설정하되 production migration은 Phase 5에서 실행한다.

### 2.2 Supabase Auth

- 이메일 가입, 이메일 확인, 비밀번호 재설정과 필요한 OAuth provider만 활성화한다.
- staging Site URL과 `/auth/callback`, `/forgot-password` redirect를 등록한다.
- asymmetric signing key를 사용하고 issuer, audience=`authenticated`, JWKS URL을 기록한다.
- Web에는 `NEXT_PUBLIC_SUPABASE_URL`, publishable key만 제공한다.
- API에는 `SUPABASE_URL`, issuer/audience/JWKS 설정만 제공하고 브라우저에 service/secret key를 노출하지 않는다.
- key rotation 시 JWKS TTL 600초와 cache refresh 동작을 시험한다.

### 2.3 DB 안전 설정

- 네트워크 접근 범위, TLS 요구, connection limit과 pool size를 서비스 plan에 맞춘다.
- 애플리케이션 table 접근은 FastAPI DB credential로만 수행한다. Supabase Data API를 쓸 계획이 없다면 노출 surface를 최소화한다.
- 매일 backup 성공 여부와 분기별 restore drill 일정을 정한다.
- slow query, storage, connection saturation 경고선을 설정한다.

## 3. Render Key Value 구축

1. staging과 production 인스턴스를 각각 만들고 API/worker와 같은 region에 둔다.
2. persistence 정책과 재시작 시 데이터 보존 기대치를 문서화한다.
3. RQ job을 보존할 수 있는 eviction 정책을 선택하고 memory full 시 동작을 검증한다.
4. 공개 URL 대신 가능한 경우 Render 내부 URL을 API/worker에 연결한다.
5. `repowise-analysis`, `repowise-deep-learning` queue의 enqueue/dequeue와 job status round trip을 시험한다.
6. queue depth, used memory, connection, failed job 감시 기반을 만든다.

Redis는 cache만이 아니라 작업 전달 계층이므로 임의 eviction으로 대기 job이 사라지지 않아야 한다. 장애 시 DB의 `AnalysisJob`/`DeepTask` 상태가 복구의 source of truth가 되도록 smoke test한다.

## 4. 연결·보안 검증

- 가입→이메일 확인→로그인으로 실제 access token을 발급한다.
- FastAPI가 signature, `iss`, `aud`, `exp`, `sub`를 검증하고 잘못된 token을 401로 거부하는지 확인한다.
- 첫 인증 요청이 user, personal organization, membership을 idempotent하게 생성하는지 확인한다.
- staging DB에 migration `0016`이 적용되고 pgvector query가 성공하는지 확인한다.
- API가 job을 enqueue하고 worker가 동일 Redis에서 받아 DB 상태를 완료로 바꾸는지 확인한다.
- staging credential로 production 접속이 불가능한지 negative test한다.
- secret이 Vercel client bundle, API 응답, build log에 노출되지 않는지 검사한다.

## 5. 환경변수 매트릭스

필수 서버 변수는 `DATABASE_URL`, 필요 시 별도 `MIGRATION_DATABASE_URL`, `REDIS_URL`, Supabase issuer/audience/JWKS, `AUTH_REQUIRED=true`다. Web에는 `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`를 환경별로 둔다. OpenAI/GitHub key는 server/worker에만 제공한다.

## 6. 완료 게이트와 복구

- [x] 승인 예외에 따라 cloud production-like 1개와 local/ephemeral staging으로 분리했다.
- [x] 실제 access token을 FastAPI JWKS 검증으로 승인했다.
- [x] 자동 검증에서 만료·잘못된 audience·다른 issuer token을 거부했다.
- [x] production-like migration `0016`과 격리 restore의 pgvector smoke test가 성공했다.
- [x] 실제 Render의 두 RQ queue에서 enqueue/dequeue가 성공했다.
- [x] backup/PITR 예외, Redis persistence/eviction 예외, secret 소유자를 기록했다.

Google/GitHub OAuth와 production Web redirect는 OAuth credential과 production Web URL이 없으므로 승인된 보류 항목이다. email/password 실제 인증과 identity bootstrap은 검증했다.

credential 노출 시 해당 환경 key/password를 즉시 회전하고 배포를 재시작한다. migration 실패 시 API/worker를 올리지 않고 staging DB를 재생성하거나 backup으로 복구한 뒤 원인을 수정한다.
