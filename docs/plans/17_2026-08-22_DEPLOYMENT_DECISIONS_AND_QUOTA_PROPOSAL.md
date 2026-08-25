# 배포 확정 사항과 무료 사용량 정책 제안

- 기준일: 2026-08-22
- 적용 대상: Phase 0, 3, 4, 5, 6 계획
- 상태: 사용자 결정 1~4 반영 완료, 무료 allowance와 저비용 환경 분리 방식 승인 대기
- 우선순위: 사용자 확대보다 실제 배포와 end-to-end 검증

## 1. 확정 사항

| 항목 | 확정 내용 |
| --- | --- |
| 주 사용자 권역 | 대한민국과 가까운 아시아 region |
| Supabase | Seoul (`ap-northeast-2`) |
| Render | Singapore. Render의 가장 가까운 아시아 지원 region |
| 월 총예산 | 인프라와 OpenAI를 합쳐 USD 10 |
| Production URL | custom domain 없이 Vercel `*.vercel.app`, Render `*.onrender.com` 사용 |
| 로그인 | 이메일, Google OAuth, GitHub OAuth |

Phase 0·3의 일반적인 “동일 region” 원칙은 **Supabase Seoul + Render Singapore**로 구체화한다. custom domain과 DNS 전환은 초기 배포 범위에서 제외한다.

## 2. USD 10 실험 예산안

| 항목 | 월 목표 | 제약 |
| --- | ---: | --- |
| Vercel Web | $0 | 무료 범위·기본 URL 사용 |
| Supabase Auth/DB | $0 | Free project. 자동 backup/PITR·SLA 없음 |
| Render API | $0 | Free web service. idle sleep과 cold start 허용 |
| Render worker | 약 $7 | background worker Starter 1개 |
| Render cron | 약 $1 또는 $0 | Render cron 또는 GitHub Actions schedule 대체 |
| OpenAI | 최대 $2~3 | cron 선택에 따라 조정, provider cap 별도 설정 |
| Render Key Value | $0 | Free는 비영속이며 workspace당 1개 |

이 구성은 production 품질 서비스가 아니라 배포 검증용이다. 무료 API는 idle 시 sleep하고 무료 Key Value는 재시작 시 RQ job을 잃을 수 있다. DB의 `AnalysisJob`·`DeepTask` 상태를 복구 기준으로 삼되 queue 내구성을 보장하지 않는다.

## 3. 사용자 검토가 필요한 환경 구성

무료 Render Key Value가 workspace당 하나라서 원래 계획의 staging/production 완전 분리는 USD 10 안에서 어렵다.

1. **권장:** production-like cloud 환경 하나만 만들고 staging은 local/ephemeral로 운영한다.
2. staging/production이 같은 Key Value를 queue prefix/Redis DB로 공유한다. 장애·보안 격리가 약해 비권장이다.
3. 예산을 올려 staging/production Key Value와 항상 켜진 API를 분리한다.

## 4. 무료 사용자 제한 권장안

횟수만 제한하면 큰 저장소·긴 음성 1회의 비용을 통제하기 어렵고, 금액만 제한하면 사용자가 무엇을 체험할 수 있는지 이해하기 어렵다. 따라서 **기능별 횟수 + 사용자 비용 cap + 전체 provider cap**을 함께 둔다.

| 기능 | 사용자당 월 기본안 | 안전장치 |
| --- | ---: | --- |
| 새 repository full 분석 | 1회 | 현재 archive/file 크기 제한 유지 |
| exact snapshot reuse | 무제한 | 외부 모델 비용이 없을 때 횟수 미차감 |
| 일반 chat | 5회 | 입력 길이·출력 token 상한 |
| Deep Task | 1회 | timeout·최대 output 제한 |
| Realtime voice | 1 session | 최대 5분 |
| 구조 탐색·학습·cache hit | 비용이 없으면 무제한 | 외부 호출 시에만 비용 기록 |

초기값은 사용자별 월 `$0.25`, 전체 OpenAI 월 hard cap `$2`를 권장한다. chat을 1회가 아니라 5회로 둔 이유는 한 번의 질문만으로 RAG 제품 경험을 평가하기 어렵기 때문이다. 실제 usage 1~2주 후 기능별 원가를 보고 조정한다.

## 5. 사용량 원장이란

사용량 원장은 OpenAI 비용을 사용자·organization·기능별로 설명하기 위한 **서비스 내부 거래 장부**다. 사용자의 은행 계좌나 결제 장부가 아니다.

예를 들어 Deep Task 한 건을 시작하면 다음처럼 움직인다.

1. 호출 전 예상 최대 비용 `$0.10`을 `reserved`로 잡는다.
2. 성공 후 실제 비용이 `$0.04`이면 `$0.04`만 `settled`한다.
3. 남은 `$0.06`은 돌려놓는다.
4. 호출이 실패·취소되면 예약 전액을 `released`한다.
5. 같은 요청이 retry되어도 idempotency key로 한 번만 정산한다.

이 장부가 있어야 “누가 어떤 기능에서 얼마를 썼는지”, “월 한도를 넘었는지”, “실패한 요청에 잘못 비용을 매기지 않았는지”를 확인할 수 있다.

## 6. `QUOTA_ENFORCEMENT_MODE`

| 모드 | 원장 기록 | 초과 계산 | 실제 차단 |
| --- | --- | --- | --- |
| `off` | 기록 | 하지 않거나 참고만 함 | 없음 |
| `shadow` | 기록 | 실제처럼 계산 | 없음 |
| `enforce` | 기록 | 계산 | 외부 호출 전에 HTTP 429 |

권장 rollout은 `off → shadow → enforce`다.

- 첫 배포: `off`. 기능이 동작하는지와 원장 정확성부터 확인한다.
- 검증 단계: `shadow`. 제한했더라면 누가 막혔을지 관찰한다.
- 원장·가격·retry 검증 후: `enforce`. 실제 비용 초과를 차단한다.

## 7. 승인 대기 항목

- [ ] cloud 환경은 production-like 1개만 두고 staging은 local/ephemeral로 운영한다.
- [ ] 무료 사용자는 분석 1회, chat 5회, Deep Task 1회, voice 1회/5분으로 시작한다.
- [ ] 사용자별 월 cap `$0.25`, 전체 OpenAI cap `$2`로 시작한다.
- [ ] `off`에서도 원장은 기록하고, `shadow`부터 가상 초과를 계산한다.
- [ ] cron은 월 $1 Render cron 대신 GitHub Actions schedule을 우선 검토한다.

이 문서의 승인값은 기존 Phase 문서의 미확정 일반안보다 우선한다.
