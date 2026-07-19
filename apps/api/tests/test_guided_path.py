from app.guidance.path_builder import TourCandidate, select_guided_steps
from app.guidance.progress import apply_progress_event


def test_selects_entry_core_support_error_and_test_steps() -> None:
    candidates = [
        TourCandidate(
            chunk_id="chk_entry",
            file_id="file_index",
            path="index.js",
            language="javascript",
            chunk_type="file",
            start_line=1,
            end_line=100,
            title="index.js",
        ),
        TourCandidate(
            chunk_id="chk_pmap",
            file_id="file_index",
            path="index.js",
            language="javascript",
            chunk_type="symbol",
            start_line=10,
            end_line=80,
            title="index.js#pMap",
            symbol_id="sym_pmap",
            symbol_name="pMap",
            symbol_kind="function",
            signature="export default async function pMap()",
            concept_ids=("async_await", "promise"),
        ),
        TourCandidate(
            chunk_id="chk_worker",
            file_id="file_index",
            path="index.js",
            language="javascript",
            chunk_type="symbol",
            start_line=20,
            end_line=40,
            title="index.js#next",
            symbol_id="sym_next",
            symbol_name="next",
            symbol_kind="function",
            signature="async function next()",
            parent_chunk_id="chk_pmap",
        ),
        TourCandidate(
            chunk_id="chk_error",
            file_id="file_error",
            path="lib/error.js",
            language="javascript",
            chunk_type="symbol",
            start_line=1,
            end_line=14,
            title="lib/error.js#handleError",
            symbol_id="sym_error",
            symbol_name="handleError",
            symbol_kind="function",
            concept_ids=("exception_handling",),
        ),
        TourCandidate(
            chunk_id="chk_test",
            file_id="file_test",
            path="test.js",
            language="javascript",
            chunk_type="file",
            start_line=1,
            end_line=80,
            title="test.js",
        ),
    ]

    steps = select_guided_steps(candidates, {"sym_pmap": ["sym_next"]})

    assert [step.step_type for step in steps] == [
        "orientation",
        "core_flow",
        "supporting_flow",
        "error_path",
        "test",
    ]
    assert [step.chunk_id for step in steps] == [
        "chk_entry",
        "chk_pmap",
        "chk_worker",
        "chk_error",
        "chk_test",
    ]
    assert "function" in steps[1].concept_ids
    assert "async_await" in steps[1].concept_ids


def test_progress_feedback_lowers_depth_and_advances_without_duplicates() -> None:
    needs_help = apply_progress_event(
        ordered_step_ids=["step_1", "step_2"],
        current_step_ordinal=1,
        completed_step_ids=[],
        needs_help_step_ids=[],
        preferred_style="advanced",
        step_id="step_1",
        event_type="needs_help",
    )
    assert needs_help.preferred_style == "standard"
    assert needs_help.current_step_ordinal == 1
    assert needs_help.needs_help_step_ids == ["step_1"]

    understood = apply_progress_event(
        ordered_step_ids=["step_1", "step_2"],
        current_step_ordinal=1,
        completed_step_ids=[],
        needs_help_step_ids=needs_help.needs_help_step_ids,
        preferred_style=needs_help.preferred_style,
        step_id="step_1",
        event_type="understood",
    )
    assert understood.status == "active"
    assert understood.current_step_ordinal == 2
    assert understood.completed_step_ids == ["step_1"]

    completed = apply_progress_event(
        ordered_step_ids=["step_1", "step_2"],
        current_step_ordinal=2,
        completed_step_ids=understood.completed_step_ids,
        needs_help_step_ids=understood.needs_help_step_ids,
        preferred_style=understood.preferred_style,
        step_id="step_2",
        event_type="understood",
    )
    assert completed.status == "completed"
    assert completed.completed_step_ids == ["step_1", "step_2"]

    reopened = apply_progress_event(
        ordered_step_ids=["step_1", "step_2"],
        current_step_ordinal=2,
        completed_step_ids=completed.completed_step_ids,
        needs_help_step_ids=completed.needs_help_step_ids,
        preferred_style=completed.preferred_style,
        step_id="step_1",
        event_type="opened",
    )
    assert reopened.status == "completed"
