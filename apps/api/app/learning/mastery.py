from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import LearnerProfile, MasteryEvent

POLICY_VERSION = "mastery-policy-v1"


@dataclass(frozen=True)
class MasteryUpdate:
    concept_id: str
    previous_score: float
    new_score: float
    previous_confidence: float
    new_confidence: float

    def payload(self) -> dict:
        return {
            "concept_id": self.concept_id,
            "previous_score": self.previous_score,
            "new_score": self.new_score,
            "previous_confidence": self.previous_confidence,
            "new_confidence": self.new_confidence,
        }


def apply_mastery_event(
    db: Session,
    *,
    profile: LearnerProfile,
    learning_session_id: str | None,
    concept_ids: list[str],
    event_type: str,
    source_type: str,
    source_id: str | None,
    score_delta: float,
    confidence_delta: float,
    evidence: dict | None = None,
) -> list[MasteryUpdate]:
    mastery = {key: dict(value) for key, value in (profile.concept_mastery or {}).items()}
    updates: list[MasteryUpdate] = []
    for concept_id in list(dict.fromkeys(item for item in concept_ids if item)):
        current = mastery.get(concept_id) or {}
        previous_score = float(current.get("score", 0.5))
        previous_confidence = float(current.get("confidence", 0.35))
        new_score = round(_bounded(previous_score + score_delta), 3)
        new_confidence = round(_bounded(previous_confidence + confidence_delta), 3)
        mastery[concept_id] = {
            "score": new_score,
            "confidence": new_confidence,
            "source": f"{source_type}:{source_id or event_type}",
        }
        update = MasteryUpdate(
            concept_id=concept_id,
            previous_score=previous_score,
            new_score=new_score,
            previous_confidence=previous_confidence,
            new_confidence=new_confidence,
        )
        updates.append(update)
        db.add(
            MasteryEvent(
                learner_profile_id=profile.id,
                learning_session_id=learning_session_id,
                concept_id=concept_id,
                event_type=event_type,
                source_type=source_type,
                source_id=source_id,
                previous_score=previous_score,
                new_score=new_score,
                previous_confidence=previous_confidence,
                new_confidence=new_confidence,
                evidence=evidence or {},
                policy_version=POLICY_VERSION,
            )
        )
    profile.concept_mastery = mastery
    return updates


def apply_mastery_projection(
    db: Session,
    *,
    profile: LearnerProfile,
    projected_mastery: dict,
    event_type: str,
    source_type: str,
    source_id: str | None,
    evidence: dict | None = None,
) -> list[MasteryUpdate]:
    current_mastery = {key: dict(value) for key, value in (profile.concept_mastery or {}).items()}
    next_mastery = {key: dict(value) for key, value in projected_mastery.items()}
    updates: list[MasteryUpdate] = []
    for concept_id, next_value in next_mastery.items():
        previous = current_mastery.get(concept_id) or {}
        previous_score = float(previous.get("score", 0.5))
        previous_confidence = float(previous.get("confidence", 0.0))
        new_score = float(next_value.get("score", previous_score))
        new_confidence = float(next_value.get("confidence", previous_confidence))
        if previous and previous_score == new_score and previous_confidence == new_confidence:
            continue
        update = MasteryUpdate(
            concept_id=concept_id,
            previous_score=previous_score,
            new_score=new_score,
            previous_confidence=previous_confidence,
            new_confidence=new_confidence,
        )
        updates.append(update)
        db.add(
            MasteryEvent(
                learner_profile_id=profile.id,
                learning_session_id=None,
                concept_id=concept_id,
                event_type=event_type,
                source_type=source_type,
                source_id=source_id,
                previous_score=previous_score,
                new_score=new_score,
                previous_confidence=previous_confidence,
                new_confidence=new_confidence,
                evidence=evidence or {},
                policy_version=POLICY_VERSION,
            )
        )
    profile.concept_mastery = next_mastery
    return updates


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, value))
