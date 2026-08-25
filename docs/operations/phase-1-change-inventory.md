# Phase 1 변경 분류표

- 조사 기준: 2026-08-22, branch `codex/repository-structure-visualization`, base `d1a6703`
- 소유권 원칙: 계획서에 열거된 auth/cache/usage/Web/migration 변경은 Phase 1 기능 변경으로 분류한다. `output/project-status` 문서는 사용자 기존 산출물로 간주해 제외한다.
- 상태 코드는 조사 시점의 `git status --short` 값이다.
- hunk 검토 항목은 여러 기능이 같은 기존 파일을 수정하므로 파일 전체 staging을 금지하고 `git add -p`로 나눈다.

| 경로 | 상태 | 분류/소유권 | 권장 commit | 처리 |
| --- | --- | --- | ---: | --- |
| `.env.example` | `M` | Backfill/docs/config | 6 | 포함 |
| `README.md` | `M` | Backfill/docs/config | 6 | 포함 |
| `apps/api/app/ai/answers.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/ai/embeddings.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/assessment.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/chat.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/debug.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/deep_tasks.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/learning.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/repositories.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/router.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/api/voice.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/core/config.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/evaluation/navigation.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/learning/explanations.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/main.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/models.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/navigation/architecture_labels.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/navigation/artifacts.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/queue.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/retrieval/hybrid.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/schemas.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/services/grounded_chat.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/services/research_materials.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/workers/deep_tasks.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/app/workers/repository_analysis.py` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/api/pyproject.toml` | `M` | 의존성/lockfile | 관련 기능 commit | 쌍으로 포함 |
| `apps/api/uv.lock` | `M` | 의존성/lockfile | 관련 기능 commit | 쌍으로 포함 |
| `apps/web/.env.local.example` | `M` | Web auth/account | 5 | 포함 |
| `apps/web/package.json` | `M` | 의존성/lockfile | 관련 기능 commit | 쌍으로 포함 |
| `apps/web/src/app/globals.css` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/web/src/components/RepositoryWorkbench.tsx` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/web/src/hooks/useDeepLearningTask.ts` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/web/src/hooks/useRealtimeLearningSession.ts` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `apps/web/src/lib/api.ts` | `M` | Phase 1 공통 통합 | hunk 검토 후 1~6 | 포함 |
| `output/project-status/RepoWiseAI_프로젝트_진행_상황_보고서.docx` | `M` | 사용자 기존 산출물 | - | 제외·수정 금지 |
| `pnpm-lock.yaml` | `M` | 의존성/lockfile | 관련 기능 commit | 쌍으로 포함 |
| `.pytest-tmp/` | `??` | 실행 중 생성한 임시 파일 | - | 제외·삭제 완료 |
| `apps/api/app/ai/gateway.py` | `??` | Usage/quota/admin | 4 | 포함 |
| `apps/api/app/analysis/artifact_cache.py` | `??` | Snapshot/incremental | 2 | 포함 |
| `apps/api/app/analysis/incremental.py` | `??` | Snapshot/incremental | 2 | 포함 |
| `apps/api/app/analysis/manifest.py` | `??` | Snapshot/incremental | 2 | 포함 |
| `apps/api/app/api/account.py` | `??` | Auth/organization/authorization | 1 | 포함 |
| `apps/api/app/api/admin.py` | `??` | Usage/quota/admin | 4 | 포함 |
| `apps/api/app/api/usage.py` | `??` | Usage/quota/admin | 4 | 포함 |
| `apps/api/app/core/auth.py` | `??` | Auth/organization/authorization | 1 | 포함 |
| `apps/api/app/core/authorization.py` | `??` | Auth/organization/authorization | 1 | 포함 |
| `apps/api/app/services/identity.py` | `??` | Auth/organization/authorization | 1 | 포함 |
| `apps/api/app/services/semantic_cache.py` | `??` | Semantic cache | 3 | 포함 |
| `apps/api/app/services/snapshot_resolver.py` | `??` | Snapshot/incremental | 2 | 포함 |
| `apps/api/app/services/usage.py` | `??` | Usage/quota/admin | 4 | 포함 |
| `apps/api/app/workers/maintenance.py` | `??` | Usage/quota/admin | 4 | 포함 |
| `apps/api/migrations/versions/0010_identity_and_organizations.py` | `??` | Auth/organization/authorization | 1 | 포함 |
| `apps/api/migrations/versions/0011_resource_ownership.py` | `??` | Auth/organization/authorization | 1 | 포함 |
| `apps/api/migrations/versions/0012_snapshot_lineage_and_fingerprint.py` | `??` | Snapshot/incremental | 2 | 포함 |
| `apps/api/migrations/versions/0013_analysis_artifact_cache.py` | `??` | Snapshot/incremental | 2 | 포함 |
| `apps/api/migrations/versions/0014_semantic_cache.py` | `??` | Semantic cache | 3 | 포함 |
| `apps/api/migrations/versions/0015_usage_quota_ledger.py` | `??` | Usage/quota/admin | 4 | 포함 |
| `apps/api/migrations/versions/0016_backfill_and_constraints.py` | `??` | Backfill/docs/config | 6 | 포함 |
| `apps/api/tests/test_cache_auth_usage_plan.py` | `??` | 교차 기능 회귀 테스트 | 1~4 | git add -p |
| `apps/web/proxy.ts` | `??` | Web auth/account | 5 | 포함 |
| `apps/web/src/app/account/` | `??` | Web auth/account | 5 | 포함 |
| `apps/web/src/app/auth/` | `??` | Web auth/account | 5 | 포함 |
| `apps/web/src/app/forgot-password/` | `??` | Web auth/account | 5 | 포함 |
| `apps/web/src/app/login/` | `??` | Web auth/account | 5 | 포함 |
| `apps/web/src/app/signup/` | `??` | Web auth/account | 5 | 포함 |
| `apps/web/src/components/AuthForm.tsx` | `??` | Web auth/account | 5 | 포함 |
| `apps/web/src/lib/supabase/` | `??` | Web auth/account | 5 | 포함 |
| `docs/operations/` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/08_2026-08-16_CACHE_AUTH_USAGE_IMPLEMENTATION_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/09_2026-08-22_PHASE_0_DEPLOYMENT_DECISIONS_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/10_2026-08-22_PHASE_1_RELEASE_BASELINE_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/11_2026-08-22_PHASE_2_PRODUCTION_PACKAGING_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/12_2026-08-22_PHASE_3_SUPABASE_REDIS_INFRA_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/13_2026-08-22_PHASE_4_STAGING_DEPLOYMENT_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/14_2026-08-22_PHASE_5_PRODUCTION_DEPLOYMENT_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/15_2026-08-22_PHASE_6_PROGRESSIVE_ROLLOUT_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/16_2026-08-22_PHASE_7_OPERATIONS_OBSERVABILITY_PLAN.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/17_2026-08-22_DEPLOYMENT_DECISIONS_AND_QUOTA_PROPOSAL.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/plans/18_2026-08-22_DEPLOYMENT_DECISIONS_FINAL.md` | `??` | Backfill/docs/config | 6 | 포함 |
| `docs/operations/phase-1-change-inventory.md` | `??` | Backfill/docs/config | 6 | 포함 |

## 제외·생성물 정책

- `.env`와 `apps/**/.env*` 실제 값은 제외하며 `.env.example` 계열 placeholder만 포함한다.
- `output/`, `.data/`, `tmp/`, `.pytest-tmp/`, `node_modules/`, `.next/`는 release commit에서 제외한다.
- `output/project-status/*.docx`는 사용자 기존 변경이다. 복원·재생성·포맷·삭제하지 않는다.
- lockfile은 대응 manifest(`pyproject.toml` 또는 `package.json`)와 같은 commit에 둔다.

## 교차 기능 파일 staging 기준

다음 파일은 한 기능으로 자동 분류하지 않는다.

- `apps/api/app/models.py`, `schemas.py`, `core/config.py`, `api/router.py`, `main.py`
- `apps/api/app/api/repositories.py`, `chat.py`, `learning.py`, `deep_tasks.py`, `voice.py`
- `apps/api/app/services/grounded_chat.py`, `workers/repository_analysis.py`
- `apps/web/src/lib/api.ts`, `RepositoryWorkbench.tsx`, realtime/deep-task hooks

각 hunk의 import 의존성과 migration 도입 순서를 보고 commit 1~5에 배치한다. 분리하면 import/build가 깨지는 hunk는 더 이른 기반 commit에 함께 두고 PR에 이유를 기록한다.
