from app.learning.curriculum import CurriculumCandidate, plan_curriculum
from app.models import LearnerProfile


def candidate(
    index: int,
    *,
    path: str | None = None,
    chunk_type: str = "symbol",
    concepts: tuple[str, ...] = (),
    symbol_kind: str = "function",
) -> CurriculumCandidate:
    resolved_path = path or f"src/feature_{index}.ts"
    return CurriculumCandidate(
        chunk_id=f"chk_{index}",
        file_id=f"file_{index}",
        path=resolved_path,
        chunk_type=chunk_type,
        title=f"{resolved_path}#feature{index}",
        start_line=index + 1,
        end_line=index + 5,
        symbol_id=f"sym_{index}",
        symbol_name=f"feature{index}",
        symbol_kind=symbol_kind,
        signature=f"export function feature{index}()",
        concept_ids=concepts,
        degree=index % 4,
    )


def test_curriculum_covers_foundations_and_multiple_project_areas():
    profile = LearnerProfile(
        anonymous_key="learner-test",
        pace="careful",
        preferred_explanation=["line_by_line"],
        concept_mastery={"async_await": {"score": 0.2, "confidence": 0.7}},
    )
    candidates = [
        candidate(0, path="README.md", chunk_type="file", symbol_kind="file"),
        candidate(1, concepts=("async_await",)),
        candidate(2, path="src/services/userService.ts"),
        candidate(3, path="src/models/user.ts"),
        candidate(4, path="tests/user.test.ts"),
        *(candidate(index) for index in range(5, 28)),
    ]

    modules = plan_curriculum(candidates, profile, symbol_count=80)
    by_type = dict(modules)
    selected = [item for _, items in modules for item in items]

    assert "orientation" in by_type
    assert "foundations" in by_type
    assert by_type["foundations"][0].concept_ids == ("async_await",)
    assert "architecture" in by_type
    assert "feature_flow" in by_type
    assert "test_apply" in by_type
    assert len(selected) >= 15
    assert len({item.chunk_id for item in selected}) == len(selected)
