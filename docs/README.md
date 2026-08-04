# RepoWise AI 문서 인덱스

이 디렉터리는 RepoWise AI의 현재 상태와 과거 의사결정 문서를 관리한다.

- 현재 프로젝트의 단일 기준 문서: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- 과거 기획·구현 계획: [`plans/`](plans/)
- 실행 방법과 빠른 시작: [루트 README](../README.md)

## 시간순 문서 목록

| 순서 | 최초 작성일 | 문서 | 성격 | 현재 해석 |
| --- | --- | --- | --- | --- |
| 1 | 2026-07-06 | [전체 프로젝트 기획서](plans/01_2026-07-06_PROJECT_PLAN.md) | 제품 비전·전체 범위 | 초기 제품 정의와 장기 방향 참고 |
| 2 | 2026-07-06 | [구현 계획서](plans/02_2026-07-06_IMPLEMENTATION_PLAN.md) | 전체 기술 설계·단계별 계획 | 구현 기반과 아직 남은 학습·운영 과제 참고 |
| 3 | 2026-07-13 | [실시간 음성 학습 파이프라인 계획](plans/03_2026-07-13_VOICE_LEARNING_PIPELINE_PLAN.md) | 음성·심층 작업 확장 | 일부 구현, 나머지는 `PROJECT_OVERVIEW.md`의 백로그 기준 |
| 4 | 2026-07-19 | [저장소 내비게이션 중심 제품 개혁 기획](plans/04_2026-07-19_NAVIGATION_REFORM_PLAN.md) | 제품 방향 전환 | 학습 선행형에서 구조 탐색 선행형으로 바꾼 근거 |
| 5 | 2026-07-19 | [저장소 내비게이션 개혁 상세 구현 계획](plans/05_2026-07-19_NAVIGATION_REFORM_IMPLEMENTATION_PLAN.md) | 내비게이션 구현 계획·결과 | Phase 1~5 구현 결과와 평가 기록 |
| 6 | 2026-07-20 | [Repository Structure Visualization 구현 계획](plans/06_2026-07-20_REPO_STRUCTURE_VISUALIZATION_IMPLEMENTATION_PLAN.md) | 구조 시각화 설계·결과 | Architecture Graph 구현 근거 |
| 7 | 2026-07-30 | [Repository Structure First UI 개편 계획](plans/07_2026-07-30_REPOSITORY_STRUCTURE_FIRST_UI_REDESIGN_PLAN.md) | 최신 UI 개편 계획·결과 | Repository Story 중심 UI 구현 근거 |

## 관리 원칙

1. `plans/` 문서는 당시 판단을 보존하는 이력 문서다. 링크 오류나 명백한 오탈자 외에는 현재 상태에 맞춰 다시 쓰지 않는다.
2. 구현 상태, 현재 구조, 기술 스택, 우선순위와 남은 작업은 `PROJECT_OVERVIEW.md`만 기준으로 판단한다.
3. 기능 구현을 완료한 변경에는 코드와 테스트뿐 아니라 `PROJECT_OVERVIEW.md` 갱신을 Definition of Done에 포함한다.
4. 문서에 완료라고 기록할 때는 구현 파일과 검증 명령 또는 테스트를 함께 남긴다.

