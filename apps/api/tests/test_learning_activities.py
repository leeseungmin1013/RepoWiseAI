import hashlib
from unittest.mock import MagicMock

from app.learning.activities import CallCandidate, build_activity_spec
from app.learning.mastery import apply_mastery_event, apply_mastery_projection
from app.models import CodeChunk, FileRecord, LearnerProfile, MasteryEvent


def source_models(content: str, *, language: str = "typescript"):
    digest = f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"
    file = FileRecord(
        id="file_1",
        snapshot_id="snap_1",
        path="src/user.ts",
        language=language,
        content=content,
        content_hash=digest,
        byte_size=len(content.encode()),
        line_count=len(content.splitlines()),
        is_documentation=language == "markdown",
    )
    chunk = CodeChunk(
        id="chk_1",
        snapshot_id="snap_1",
        file_id=file.id,
        chunk_type="symbol" if language != "markdown" else "file",
        ordinal=0,
        title="src/user.ts#run",
        language=language,
        start_line=1,
        end_line=file.line_count,
        content=content,
        search_text=content,
        embedding_model="local-hash-v1",
        content_hash=digest,
        metadata_json={},
    )
    return chunk, file


def correct_label(spec) -> str:
    return next(item["label"] for item in spec.choices if item["id"] == spec.answer_key)


def test_activity_prefers_verified_error_statement():
    chunk, file = source_models(
        """function run(input: string) {
  if (!input) {
    throw new Error('missing');
  }
  return input;
}"""
    )

    spec = build_activity_spec(
        chunk=chunk,
        file=file,
        concepts=["exception_handling"],
        other_paths=["src/index.ts"],
        symbol_names=["loadUser"],
    )

    assert spec.activity_type == "select_error_path"
    assert correct_label(spec).startswith("throw new Error")
    assert spec.evidence["start_line"] == 3
    assert spec.evidence["evidence_id"] == "ev_1"


def test_activity_uses_first_call_when_no_return_or_throw_exists():
    chunk, file = source_models(
        """function run() {
  prepare();
  finish();
}"""
    )

    spec = build_activity_spec(
        chunk=chunk,
        file=file,
        concepts=["function"],
        other_paths=["src/index.ts"],
        symbol_names=["prepare", "finish", "save"],
    )

    assert spec.activity_type == "predict_next_call"
    assert correct_label(spec) == "prepare"
    assert spec.evidence["start_line"] == 2


def test_non_code_activity_asks_for_verified_file_path():
    chunk, file = source_models("# Project\n\nRun the app", language="markdown")

    spec = build_activity_spec(
        chunk=chunk,
        file=file,
        concepts=[],
        other_paths=["package.json", "src/index.ts"],
        symbol_names=[],
    )

    assert spec.activity_type == "locate_source_file"
    assert correct_label(spec) == "src/user.ts"


def test_resolved_call_edge_wins_over_parser_fallback():
    chunk, file = source_models("function run() {\n  localName();\n}")

    spec = build_activity_spec(
        chunk=chunk,
        file=file,
        concepts=["function"],
        other_paths=[],
        symbol_names=["localName"],
        resolved_calls=[
            CallCandidate(
                target="ResolvedService",
                start_line=2,
                end_line=2,
                source="localName();",
                relation="CALLS",
                confidence=0.92,
            )
        ],
    )

    assert spec.activity_type == "predict_next_call"
    assert correct_label(spec) == "ResolvedService"
    assert spec.evidence["relation"] == "CALLS"
    assert spec.evidence["relation_confidence"] == 0.92


def test_resolved_import_edge_builds_dependency_activity():
    chunk, file = source_models("import { load } from './service';")

    spec = build_activity_spec(
        chunk=chunk,
        file=file,
        concepts=[],
        other_paths=["src/other.ts"],
        symbol_names=[],
        resolved_imports=[
            CallCandidate(
                target="src/service.ts",
                start_line=1,
                end_line=1,
                source="import { load } from './service';",
                relation="IMPORTS",
                confidence=1.0,
            )
        ],
    )

    assert spec.activity_type == "trace_dependency"
    assert correct_label(spec) == "src/service.ts"
    assert spec.evidence["relation"] == "IMPORTS"


def test_mastery_event_records_before_and_after_projection():
    db = MagicMock()
    profile = LearnerProfile(
        id="learn_1",
        anonymous_key="learner-test",
        concept_mastery={"function": {"score": 0.4, "confidence": 0.5}},
    )

    updates = apply_mastery_event(
        db,
        profile=profile,
        learning_session_id="session_1",
        concept_ids=["function"],
        event_type="activity_correct",
        source_type="activity_attempt",
        source_id="attempt_1",
        score_delta=0.12,
        confidence_delta=0.15,
        evidence={"evidence_id": "ev_1"},
    )

    assert updates[0].previous_score == 0.4
    assert updates[0].new_score == 0.52
    assert profile.concept_mastery["function"]["confidence"] == 0.65
    event = db.add.call_args.args[0]
    assert isinstance(event, MasteryEvent)
    assert event.previous_score == 0.4
    assert event.new_score == 0.52


def test_assessment_projection_is_recorded_as_absolute_mastery_event():
    db = MagicMock()
    profile = LearnerProfile(
        id="learn_1",
        anonymous_key="learner-test",
        concept_mastery={},
    )

    updates = apply_mastery_projection(
        db,
        profile=profile,
        projected_mastery={
            "async_await": {
                "score": 0.2,
                "confidence": 0.65,
                "source": "assessment:async_order",
            }
        },
        event_type="assessment_result",
        source_type="assessment",
        source_id="assessment_1",
    )

    assert updates[0].previous_confidence == 0.0
    assert updates[0].new_score == 0.2
    event = db.add.call_args.args[0]
    assert event.event_type == "assessment_result"
    assert event.source_id == "assessment_1"
