from __future__ import annotations

from dataclasses import dataclass

from app.models import FileRecord
from app.schemas import RepositoryStoryResponse

GENERIC_RESPONSIBILITY_MARKERS = (
    "주요 책임과 경계를 나타냅니다",
    "module의 주요 책임",
    "api의 주요 책임",
)


@dataclass(frozen=True)
class RepositoryStoryValidation:
    valid: bool
    issues: tuple[str, ...]
    evidence_validity: float
    feature_mapping_coverage: float
    generic_responsibility_ratio: float


def validate_repository_story(
    story: RepositoryStoryResponse,
    *,
    files: list[FileRecord],
) -> RepositoryStoryValidation:
    issues: list[str] = []
    file_line_counts = {item.id: item.line_count for item in files}
    role_ids = {role.id for role in story.roles}
    evidence_count = 0
    valid_evidence_count = 0

    if not 1 <= len(story.roles) <= 12:
        issues.append("역할 수는 1개 이상 12개 이하여야 합니다.")
    if len(role_ids) != len(story.roles):
        issues.append("역할 ID는 중복될 수 없습니다.")

    generic_count = 0
    feature_ids = {feature.id for feature in story.features}
    mapped_feature_ids: set[str] = set()
    for role in story.roles:
        if not role.member_node_ids or not role.member_file_ids:
            issues.append(f"{role.id}에 구현 구성원이 없습니다.")
        if any(marker in role.role_summary.casefold() for marker in GENERIC_RESPONSIBILITY_MARKERS):
            generic_count += 1
        mapped_feature_ids.update(role.feature_flow_ids)
        for evidence in role.evidence:
            evidence_count += 1
            if (
                evidence.file_id in file_line_counts
                and 1
                <= evidence.start_line
                <= evidence.end_line
                <= file_line_counts[evidence.file_id]
            ):
                valid_evidence_count += 1

    for evidence in story.purpose.evidence:
        evidence_count += 1
        if (
            evidence.file_id in file_line_counts
            and 1
            <= evidence.start_line
            <= evidence.end_line
            <= file_line_counts[evidence.file_id]
        ):
            valid_evidence_count += 1

    for connection in story.connections:
        if connection.source not in role_ids or connection.target not in role_ids:
            issues.append(f"{connection.id}가 존재하지 않는 역할을 연결합니다.")
        for evidence in connection.evidence:
            evidence_count += 1
            if (
                evidence.file_id in file_line_counts
                and 1
                <= evidence.start_line
                <= evidence.end_line
                <= file_line_counts[evidence.file_id]
            ):
                valid_evidence_count += 1

    evidence_validity = valid_evidence_count / evidence_count if evidence_count else 0.0
    feature_mapping_coverage = (
        len(feature_ids & mapped_feature_ids) / len(feature_ids) if feature_ids else 1.0
    )
    generic_ratio = generic_count / len(story.roles) if story.roles else 1.0
    if evidence_validity < 1.0:
        issues.append("일부 설명 근거가 현재 snapshot 파일과 일치하지 않습니다.")
    if generic_ratio > 0:
        issues.append("일반적인 책임 fallback 문장이 남아 있습니다.")

    return RepositoryStoryValidation(
        valid=not issues,
        issues=tuple(issues),
        evidence_validity=round(evidence_validity, 4),
        feature_mapping_coverage=round(feature_mapping_coverage, 4),
        generic_responsibility_ratio=round(generic_ratio, 4),
    )
