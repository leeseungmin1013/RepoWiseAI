# Phase 6. 기능 점진 활성화 계획

- 기준일: 2026-08-22
- 상태: production 안정화 후 실행
- 목표: 분석 재사용, semantic cache, quota를 독립 flag와 측정 가능한 gate로 활성화한다.
- 예상 기간: 최소 2~4주
- 사용자 검토 필요: organization allowlist, 품질 승인자, enforce 날짜와 고객 안내

## 1. 공통 원칙

- 한 번에 한 기능 축만 승격하고 최소 표본 수와 관측 기간을 둔다.
- allowlist/cohort는 안정된 organization key로 결정한다.
- 변경자, 시각, 이전/새 값, 근거 dashboard와 rollback 조건을 기록한다.
- code rollback 없이 기능별로 즉시 끌 수 있어야 한다.

## 2. 분석 재사용

관측 지표는 exact/incremental/full 비율·이유, resolve/queue/처리 p95, 변경/영향 비율, parse/chunk/embedding 재사용률과 full 결과 동등성이다.

1. exact reuse만 활성화해 SHA, fingerprint, ready 상태와 tenant association을 검증한다.
2. 내부 organization에서 incremental을 켠다.
3. 29/30/31% 경계, rename/delete, parser version 변경을 관찰한다.
4. 대표 Python/TypeScript/monorepo를 full 결과와 비교한다.
5. 이상이 없으면 cohort를 확대한다.

잘못된 snapshot, 누락 symbol/chunk, stale citation이 1건이라도 나오면 `INCREMENTAL_ANALYSIS_ENABLED=false`로 내린다. exact reuse가 안전하면 독립 유지할 수 있다.

## 3. Semantic cache

### 3.1 Shadow

candidate, similarity, intent/context, tenant scope, TTL, citation 검증과 새 생성 대비 품질을 기록하되 응답은 대체하지 않는다. 질문 원문 대신 최소화된 평가 metadata를 저장한다.

### 3.2 승격

1. 최소 1주 또는 합의된 후보 수까지 shadow를 수집한다.
2. citation 실패 0, tenant 격리 100%, intent/context 오탐 0을 확인한다.
3. 내부 organization에 retrieval read를 켠다.
4. 더 높은 threshold로 generation cache를 별도 활성화한다.
5. 제한 cohort→25%→50%→100%로 확대한다.
6. false hit/miss, latency, 비용 절감으로 threshold/TTL을 하나씩 조정한다.

cross-tenant, invalid citation, 다른 snapshot 근거, 중대 품질 저하는 즉시 read rollback 조건이다. write/shadow는 원인 분석을 위해 유지할 수 있다.

## 4. Quota

| 모드 | 기록·정산 | 가상 초과 | 실제 차단 |
| --- | --- | --- | --- |
| `off` | 유지 권장 | 선택 | 없음 |
| `shadow` | 수행 | 수행 | 없음 |
| `enforce` | 수행 | 수행 | 외부 호출 전 429 |

코드 의미가 표와 다르면 rollout 전에 이름/구현/운영 문서를 일치시킨다.

### Shadow gate

- 모든 OpenAI 경로가 provider/model/usage/비용을 기록한다.
- cache hit 비용은 0이고 local fallback과 구분된다.
- 실패·취소·timeout·API/RQ retry 이중 charge가 없다.
- stale reservation과 bonus 만료/차감이 규칙대로 동작한다.
- model price에 출처와 effective date가 있다.
- provider와 내부 원장 일별 차이가 초기 목표 2% 이하다.

### Enforce

내부→제한 cohort→전체 순으로 올린다. 70/90/100% 알림, account 표시, 429 reset/remaining, 지원·bonus 절차를 먼저 검증한다. 차단 오류나 원장 불일치는 shadow로 즉시 복귀한다.

## 5. 완료 조건

- [ ] incremental이 full과 안전하게 일치한다.
- [ ] cache citation 실패와 tenant 누출이 0건이다.
- [ ] 원장/provider 오차가 목표 안이고 이중 과금이 없다.
- [ ] 사용자 알림과 429 UX가 검증되었다.
- [ ] 독립 rollback을 production에서 시험했다.

각 승격은 `docs/operations/rollouts/`에 날짜, cohort, 표본, 지표, 승인자와 rollback 결과를 남긴다.
