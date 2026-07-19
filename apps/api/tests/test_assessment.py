from app.assessment.question_bank import merge_questions_for_stack, questions_for_stack
from app.assessment.scoring import project_profile, score_response


def test_stack_questions_add_one_project_specific_item():
    questions = questions_for_stack(["TypeScript", "React", "Next.js"])

    assert questions[-1].id == "react_experience"
    assert len(questions) == 7


def test_objective_answers_override_lower_confidence_self_report():
    questions = [item.stored_payload() for item in questions_for_stack(["TypeScript"])]
    projection = project_profile(
        questions=questions,
        answers={
            "goal": "learn_programming",
            "preferred_explanation": "line_by_line",
            "javascript_experience": "none",
            "function_flow": "called_function",
            "async_order": "stop_app",
            "pace": "careful",
        },
    )

    assert projection["goal"] == "learn_programming"
    assert projection["concept_mastery"]["function"]["score"] == 0.78
    assert projection["concept_mastery"]["async_await"]["score"] == 0.2


def test_scoring_does_not_mark_preferences_correct_or_incorrect():
    scored = score_response({"category": "preference"}, "careful")

    assert scored.is_correct is None
    assert scored.score == 0.0


def test_stack_question_late_binding_is_idempotent():
    common = [item.stored_payload() for item in questions_for_stack([])]

    with_react = merge_questions_for_stack(common, ["TypeScript", "React", "Next.js"])
    repeated = merge_questions_for_stack(with_react, ["TypeScript", "React", "Next.js"])

    assert len(with_react) == len(common) + 1
    assert with_react[-1]["id"] == "react_experience"
    assert repeated == with_react
