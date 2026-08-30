from copy import deepcopy

from app.evaluation.learning import LearningGoldFixture, evaluate_learning_output


def _fixture() -> LearningGoldFixture:
    return LearningGoldFixture(
        name="learning quality",
        repository="owner/repository",
        required_module_types=["orientation", "feature_flow"],
        required_activity_types=["trace_value", "select_error_path"],
        allowed_source_domains=["developer.mozilla.org"],
        thresholds={
            "curriculum_module_coverage": 1.0,
            "lesson_evidence_coverage": 1.0,
            "activity_type_coverage": 1.0,
            "activity_evidence_validity": 1.0,
            "statement_span_validity": 1.0,
            "source_policy_precision": 1.0,
            "source_concept_coverage": 1.0,
            "learning_context_retrieval_coverage": 1.0,
        },
    )


def _output() -> dict:
    evidence = {
        "evidence_id": "ev_1",
        "file_id": "file_1",
        "start_line": 2,
        "end_line": 2,
    }
    return {
        "modules": [
            {"module_type": "orientation"},
            {"module_type": "feature_flow"},
        ],
        "lessons": [
            {
                "evidence_ids": ["ev_1"],
                "required_concept_ids": ["function"],
            }
        ],
        "activities": [
            {
                "activity_type": "trace_value",
                "verification_status": "verified",
                "source_hash": "sha256:source",
                "evidence": evidence,
                "file_line_count": 10,
            },
            {
                "activity_type": "select_error_path",
                "verification_status": "verified",
                "source_hash": "sha256:source",
                "evidence": evidence,
                "file_line_count": 10,
            },
        ],
        "artifacts": [
            {
                "verification_status": "verified",
                "source_hash": "sha256:source",
                "chunk_source_hash": "sha256:source",
                "chunk_start_line": 1,
                "chunk_end_line": 5,
                "segments": [
                    {
                        "start_line": 2,
                        "end_line": 2,
                        "source": "return value;",
                    }
                ],
            }
        ],
        "sources": [
            {
                "concept_id": "function",
                "canonical_url": "https://developer.mozilla.org/functions",
                "source_tier": "official",
                "freshness_status": "current",
            }
        ],
        "learning_retrievals": [
            {
                "query_text": "질문\n현재 학습 단계: 함수",
                "learning_session_id": "learnses_1",
                "concept_ids": ["function"],
            }
        ],
    }


def test_learning_quality_report_passes_all_grounded_invariants():
    report = evaluate_learning_output(_output(), _fixture())

    assert report["passed"] is True
    assert report["failed_thresholds"] == []
    assert report["statement_span_validity"] == 1.0
    assert report["learning_context_retrieval_coverage"] == 1.0


def test_learning_quality_report_exposes_span_source_and_context_regressions():
    output = deepcopy(_output())
    output["artifacts"][0]["segments"][0]["end_line"] = 99
    output["sources"][0]["canonical_url"] = "https://example.com/invented"
    output["learning_retrievals"][0]["concept_ids"] = []

    report = evaluate_learning_output(output, _fixture())

    assert report["passed"] is False
    assert set(report["failed_thresholds"]) == {
        "statement_span_validity",
        "source_policy_precision",
        "learning_context_retrieval_coverage",
    }