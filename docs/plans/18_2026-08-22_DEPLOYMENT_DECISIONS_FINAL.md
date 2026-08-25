# 배포·무료 사용량 정책 최종 결정

- 결정일: 2026-08-22
- 상태: 최종 승인
- 승인자: 프로젝트 소유자
- 관련 문서: `17_2026-08-22_DEPLOYMENT_DECISIONS_AND_QUOTA_PROPOSAL.md`
- 적용 대상: Phase 0, 3, 4, 5, 6, 7

이 문서는 관련 Phase 계획의 미확정안과 17번 제안서의 승인 대기 항목을 대체하는 최종 기준이다.

## 1. 인프라·환경

- cloud에는 production-like 환경 하나만 구축한다.
- staging은 local 또는 배포 시점에만 만드는 ephemeral 환경으로 운영한다.
- staging과 production이 동일 Render Key Value를 공유하지 않는다.
- Supabase는 Seoul (`ap-northeast-2`), Render는 Singapore를 사용한다.
- custom domain 없이 Vercel `*.vercel.app`, Render `*.onrender.com` 기본 URL을 사용한다.
- 로그인은 이메일, Google OAuth, GitHub OAuth를 제공한다.
- 인프라와 OpenAI를 합친 월 예산 상한은 USD 10이다.

## 2. 무료 사용자 월 제한

| 기능 | 사용자당 월 제한 | 비고 |
| --- | ---: | --- |
| 새 repository full 분석 | 1회 | exact snapshot reuse는 비용이 없으면 미차감 |
| 일반 chat | 5회 | 입력·출력 token 상한 적용 |
| Deep Task | 1회 | timeout·출력 상한 적용 |
| Realtime voice | 1 session | 최대 5분 |
| 구조 탐색·학습·cache hit | 외부 모델 비용이 없으면 무제한 | 외부 호출 시 원장 기록 |

- 사용자별 OpenAI 월 비용 cap: USD 0.25
- 서비스 전체 OpenAI 월 hard cap: USD 2
- 전체 cap 도달 시 개별 사용자 잔여 allowance와 관계없이 신규 유료 provider 호출을 차단한다.

## 3. Quota·사용량 원장

- `QUOTA_ENFORCEMENT_MODE=off`에서도 모든 유료 provider 호출을 사용량 원장에 기록한다.
- `off`에서는 기록만 하고 사용자 요청을 차단하지 않는다.
- `shadow`에서는 실제와 동일하게 초과 여부를 계산하지만 차단하지 않는다.
- `enforce`에서는 사용자별 또는 서비스 전체 cap 초과가 예상되면 provider 호출 전에 차단한다.
- rollout 순서는 `off → shadow → enforce`로 고정한다.
- 실패·취소는 reservation을 해제하고 retry는 idempotency key로 이중 정산을 방지한다.

## 4. Maintenance 실행

- Render 유료 cron은 초기 구성에서 사용하지 않는다.
- GitHub Actions scheduled workflow로 maintenance CLI를 실행한다.
- workflow는 수동 실행(`workflow_dispatch`)도 지원한다.
- 동시 실행 방지, 실패 exit code, secret masking, 실행 결과 보존과 실패 알림을 구성한다.
- GitHub Actions에서 production DB에 접근하는 권한은 maintenance에 필요한 최소 범위로 제한한다.

## 5. 구현 시 필수 설정

```dotenv
DEFAULT_MONTHLY_ALLOWANCE_MICRO_USD=250000
QUOTA_ENFORCEMENT_MODE=off
REALTIME_MAX_DURATION_SECONDS=300
NEXT_PUBLIC_REALTIME_MAX_DURATION_SECONDS=300
```

서비스 전체 OpenAI 월 hard cap USD 2와 기능별 횟수 제한은 현재 설정에 대응 필드가 없으면 별도 configuration과 원장 query 기반 guard로 추가한다. 단순히 사용자별 `DEFAULT_MONTHLY_ALLOWANCE_MICRO_USD`만 설정해서 전체 cap이 구현되었다고 간주하지 않는다.

## 6. 승인 체크리스트

- [x] production-like cloud 환경 하나 + local/ephemeral staging
- [x] 무료 사용자 월 분석 1회, chat 5회, Deep Task 1회, voice 1회/5분
- [x] 사용자별 월 USD 0.25, 서비스 전체 OpenAI 월 USD 2
- [x] `off`에서도 사용량 원장 기록
- [x] maintenance는 GitHub Actions schedule 사용

위 값을 변경하려면 예산·기능 영향과 적용일을 기록한 새로운 결정 문서를 만들고 Phase 6 rollout 절차에 따라 변경한다.
