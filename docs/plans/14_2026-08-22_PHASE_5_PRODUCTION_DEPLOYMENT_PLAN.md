# Phase 5. Production 제한 배포 계획

- 기준일: 2026-08-22
- 상태: staging gate 통과 후 실행
- 목표: 낮은 allowance와 보수적 flag로 production을 배포하고 실제 가입부터 분석·질문까지 검증한다.
- 예상 기간: 1~2일 + 48시간 집중 관찰
- 사용자 검토 필요: 도메인/DNS 전환 시각, 관리자, plan·가격·allowance, go/no-go 승인자

## 1. 변경 동결과 Go/No-Go

배포 24시간 전 SHA와 image digest를 동결한다. staging 증빙, 미해결 issue, backup restore, migration/rollback 리허설, 담당자 연락망을 검토한다. 권한·비용·데이터 무결성 P0/P1이 있으면 no-go다.

## 2. 기본 설정

```dotenv
APP_ENV=production
AUTH_REQUIRED=true
EXACT_SNAPSHOT_REUSE_ENABLED=true
INCREMENTAL_ANALYSIS_ENABLED=true
SEMANTIC_CACHE_WRITE_ENABLED=true
SEMANTIC_CACHE_READ_ENABLED=true
SEMANTIC_CACHE_SHADOW_MODE=true
QUOTA_ENFORCEMENT_MODE=off
NAVIGATION_LLM_LABELS_ENABLED=false
```

allowance는 사용자 승인값을 사용하고 임의의 무료 금액을 정하지 않는다. CORS는 정확한 production Web origin만 허용하며 preview/localhost wildcard를 넣지 않는다.

## 3. 배포 절차

### 3.1 데이터베이스

1. connection, migration head, storage 여유를 확인한다.
2. 수동 backup과 복구 식별자를 기록한다.
3. migration SQL과 lock을 검토하고 direct URL로 실행한다.
4. `alembic current`, row count, constraint/index, pgvector query를 확인한다.
5. schema가 다르면 API/worker 배포를 중단한다.

### 3.2 서비스·Web·DNS

1. Render API를 고정 digest로 배포하고 readiness를 확인한다.
2. 같은 digest의 worker와 maintenance cron을 배포한다.
3. Vercel Web을 고정 commit으로 배포한다.
4. Supabase Site URL/callback/reset URL을 등록한다.
5. `app.<domain>`, `api.<domain>` custom domain과 TLS를 확인한다.
6. 낮춰 둔 DNS TTL로 승인된 시각에 전환한다.

### 3.3 초기 데이터와 관리자

- 정상 가입·이메일 검증 뒤 감사 가능한 DB role 승격으로 관리자를 만든다.
- plan, feature limit, model price를 날짜·통화·micro-USD 단위와 출처까지 review 후 seed한다.
- 낮은 allowance의 테스트 사용자를 실제 사용자와 구분해 만든다.
- 공유 관리자 계정이나 브라우저의 service key를 만들지 않는다.

## 4. Production smoke test

1. 가입→이메일 확인→로그인→account/usage 조회
2. 작은 저장소 등록→분석→Story/graph 조회
3. 근거 질문→citation file/hash/line 이동
4. 같은 SHA 재등록→exact reuse
5. Deep Task→SSE/polling→완료 또는 취소
6. 로그아웃 후 401, 다른 사용자의 resource 접근 거부
7. ledger/provider usage와 queue/DB/Redis 지표 확인

## 5. Rollback

- Web/API: 이전 Vercel deployment/Render digest로 복귀한다.
- DNS: 이전 target을 유지하고 TTL 전파를 관찰한다.
- worker: enqueue를 제한하고 이전 digest로 복귀한 뒤 DB 상태를 재조정한다.
- DB: additive migration은 이전 app 호환을 유지한다. 비호환·손상은 쓰기를 중단하고 restore 또는 forward-fix를 incident commander가 선택한다.
- 보안: 노출 surface를 제한하고 credential을 회전한다.

결정 시각, 결정자, release, DB 상태와 유실 가능 job을 incident log에 기록한다.

## 6. 완료 게이트

- [ ] 가입부터 분석·질문까지 성공한다.
- [ ] domain, TLS, callback, exact CORS가 정상이다.
- [ ] API/worker/Redis/DB와 usage 지표가 정상이다.
- [ ] 관리자와 초기 plan/price/limit가 review되었다.
- [ ] 이전 image/Web/DNS와 DB 복구 식별자를 확인했다.
- [ ] 48시간 중 미해결 P0/P1이 없다.

배포 완료 후에도 semantic cache는 shadow, quota는 비차단으로 유지하고 Phase 6 gate를 따른다.
