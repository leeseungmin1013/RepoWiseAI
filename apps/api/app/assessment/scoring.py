from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoredResponse:
    is_correct: bool | None
    score: float
    confidence: float


SELF_REPORT_SCORES = {
    "none": 0.15,
    "basic": 0.45,
    "comfortable": 0.78,
}


def score_response(question: dict, answer: str) -> ScoredResponse:
    category = question.get("category")
    answer_key = question.get("answer_key")
    if category == "objective" and answer_key:
        correct = answer == answer_key
        return ScoredResponse(
            is_correct=correct,
            score=0.78 if correct else 0.2,
            confidence=0.65,
        )
    if category == "self_report":
        return ScoredResponse(
            is_correct=None,
            score=SELF_REPORT_SCORES.get(answer, 0.35),
            confidence=0.3,
        )
    return ScoredResponse(is_correct=None, score=0.0, confidence=0.15)


def project_profile(
    *,
    questions: list[dict],
    answers: dict[str, str],
    previous_mastery: dict | None = None,
) -> dict:
    goal = answers.get("goal", "understand_whole_project")
    preference = answers.get("preferred_explanation", "line_by_line")
    pace = answers.get("pace", "careful")
    mastery = dict(previous_mastery or {})
    for question in questions:
        item_id = question.get("id")
        answer = answers.get(item_id)
        concept_id = question.get("concept_id")
        if not answer or not concept_id:
            continue
        scored = score_response(question, answer)
        existing = mastery.get(concept_id)
        if existing and existing.get("confidence", 0) > scored.confidence:
            continue
        mastery[concept_id] = {
            "score": scored.score,
            "confidence": scored.confidence,
            "source": f"assessment:{item_id}",
        }
    return {
        "goal": goal,
        "preferred_explanation": [preference],
        "pace": pace,
        "concept_mastery": mastery,
    }
