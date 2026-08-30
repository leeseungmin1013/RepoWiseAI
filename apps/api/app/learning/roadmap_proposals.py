from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.learning.curriculum import (
    CurriculumCandidate,
    append_curriculum_modules,
    load_curriculum_candidates,
    plan_curriculum,
    profile_fingerprint,
)
from app.models import (
    JourneyEvent,
    LearningLesson,
    LearningModule,
    LearningPath,
    LearningSession,
    RemediationBranch,
    RoadmapProposal,
    Symbol,
    utc_now,
)

MODULE_ORDER = (
    "orientation",
    "foundations",
    "architecture",
    "feature_flow",
    "data_failure",
    "test_apply",
)
MAX_PROPOSAL_LESSONS = 40


class RoadmapConflict(ValueError):
    pass


@dataclass(frozen=True)
class AppliedRoadmap:
    proposal_id: str
    path_id: str
    preserved_lesson_ids: list[str]
    revision: int


def create_roadmap_proposal(
    db: Session,
    *,
    session_id: str,
    focus_concept_ids: list[str] | None = None,
    max_lessons: int = MAX_PROPOSAL_LESSONS,
    selected_candidate_ids: list[str] | None = None,
) -> RoadmapProposal:
    learning_session = _load_session(db, session_id, lock=True)
    path = learning_session.path
    candidates = load_curriculum_candidates(db, learning_session.snapshot_id)
    if not candidates:
        raise ValueError("Snapshot has no verified curriculum candidates")
    symbol_count = (
        db.scalar(
            select(func.count(Symbol.id)).where(Symbol.snapshot_id == learning_session.snapshot_id)
        )
        or 0
    )
    planned = plan_curriculum(candidates, learning_session.profile, symbol_count=symbol_count)
    focus = set(focus_concept_ids or [])
    rows = _candidate_rows(planned, learning_session.profile.pace, focus)
    deterministic_ids = _deterministic_selection(rows, max_lessons=max_lessons)

    requested_ids = list(selected_candidate_ids or [])
    verification = verify_roadmap_selection(
        rows,
        requested_ids or deterministic_ids,
        max_lessons=max_lessons,
    )
    selected_ids = requested_ids or deterministic_ids
    if not verification["valid"]:
        selected_ids = deterministic_ids
        fallback_verification = verify_roadmap_selection(
            rows,
            selected_ids,
            max_lessons=max_lessons,
        )
        if not fallback_verification["valid"]:
            raise ValueError("Deterministic roadmap proposal failed verification")
        verification = {
            **fallback_verification,
            "fallback_used": True,
            "fallback_reason": "; ".join(verification["errors"]),
        }
    else:
        verification["fallback_used"] = False

    current = _current_incomplete_candidates(learning_session)
    diff = build_roadmap_diff(current, rows, selected_ids)
    revision = int((path.model_metadata or {}).get("revision", 1))
    proposal = RoadmapProposal(
        learning_session_id=learning_session.id,
        path_id=path.id,
        base_revision=revision,
        status="proposed",
        request_json={
            "focus_concept_ids": sorted(focus),
            "max_lessons": max_lessons,
            "requested_candidate_ids": requested_ids,
        },
        candidates_json=rows,
        selection_json=selected_ids,
        diff_json=diff,
        verification_json=verification,
    )
    db.add(proposal)
    db.flush()
    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type="roadmap_proposed",
            module_id=learning_session.current_module_id,
            lesson_id=learning_session.current_lesson_id,
            step_id=learning_session.current_step_id,
            payload={
                "proposal_id": proposal.id,
                "base_revision": revision,
                "estimated_minutes_delta": diff["estimated_minutes_delta"],
            },
        )
    )
    db.flush()
    return proposal


def get_roadmap_proposal(db: Session, proposal_id: str) -> RoadmapProposal:
    proposal = db.get(RoadmapProposal, proposal_id)
    if proposal is None:
        raise ValueError("Roadmap proposal not found")
    return proposal


def reject_roadmap_proposal(db: Session, *, proposal_id: str) -> RoadmapProposal:
    proposal = db.scalar(
        select(RoadmapProposal).where(RoadmapProposal.id == proposal_id).with_for_update()
    )
    if proposal is None:
        raise ValueError("Roadmap proposal not found")
    if proposal.status != "proposed":
        raise ValueError(f"Roadmap proposal is already {proposal.status}")
    proposal.status = "rejected"
    proposal.rejected_at = utc_now()
    db.add(
        JourneyEvent(
            learning_session_id=proposal.learning_session_id,
            event_type="roadmap_rejected",
            payload={"proposal_id": proposal.id, "base_revision": proposal.base_revision},
        )
    )
    db.flush()
    return proposal


def apply_roadmap_proposal(db: Session, *, proposal_id: str) -> AppliedRoadmap:
    proposal = db.scalar(
        select(RoadmapProposal).where(RoadmapProposal.id == proposal_id).with_for_update()
    )
    if proposal is None:
        raise ValueError("Roadmap proposal not found")
    if proposal.status != "proposed":
        raise ValueError(f"Roadmap proposal is already {proposal.status}")

    learning_session = _load_session(db, proposal.learning_session_id, lock=True)
    path = learning_session.path
    current_revision = int((path.model_metadata or {}).get("revision", 1))
    if proposal.base_revision != current_revision:
        proposal.status = "conflicted"
        proposal.failure_reason = (
            f"Path revision changed from {proposal.base_revision} to {current_revision}; "
            "generate a new proposal"
        )
        db.flush()
        raise RoadmapConflict(proposal.failure_reason)

    current_candidates = {
        candidate.chunk_id: candidate
        for candidate in load_curriculum_candidates(db, learning_session.snapshot_id)
    }
    stored_rows = list(proposal.candidates_json or [])
    verification = verify_roadmap_selection(
        stored_rows,
        list(proposal.selection_json or []),
        max_lessons=int((proposal.request_json or {}).get("max_lessons", MAX_PROPOSAL_LESSONS)),
    )
    selected_rows = {
        row["candidate_id"]: row
        for row in stored_rows
        if row.get("candidate_id") in set(proposal.selection_json or [])
    }
    stale = [
        candidate_id
        for candidate_id, row in selected_rows.items()
        if candidate_id not in current_candidates
        or row.get("evidence_ids") != [current_candidates[candidate_id].evidence_id]
    ]
    if stale:
        verification["valid"] = False
        verification["errors"] = [
            *verification["errors"],
            f"stale or missing evidence for: {', '.join(stale)}",
        ]
    if not verification["valid"]:
        raise ValueError(
            "Roadmap proposal verification failed: " + "; ".join(verification["errors"])
        )

    requested_completed = set(learning_session.completed_lesson_ids or [])
    all_lessons = [lesson for module in path.modules for lesson in module.lessons]
    valid_completed = [lesson for lesson in all_lessons if lesson.id in requested_completed]
    preserved_ids = [lesson.id for lesson in valid_completed]
    preserved_chunk_ids = {
        step.chunk_id for lesson in valid_completed for step in lesson.steps if step.chunk_id
    }
    preserved_minutes = sum(lesson.estimated_minutes for lesson in valid_completed)

    learning_session.current_module_id = None
    learning_session.current_lesson_id = None
    learning_session.current_step_id = None
    learning_session.return_stack = []
    learning_session.teaching_state = {}
    learning_session.current_selection = {}
    db.execute(
        delete(RemediationBranch).where(
            RemediationBranch.learning_session_id == learning_session.id
        )
    )

    for module in list(path.modules):
        completed_in_module = [
            lesson for lesson in module.lessons if lesson.id in requested_completed
        ]
        if not completed_in_module:
            db.delete(module)
            continue
        for lesson in list(module.lessons):
            if lesson.id not in requested_completed:
                db.delete(lesson)
        module.estimated_minutes = sum(lesson.estimated_minutes for lesson in completed_in_module)
    db.flush()

    selected_set = set(proposal.selection_json or [])
    grouped: dict[str, list[CurriculumCandidate]] = {key: [] for key in MODULE_ORDER}
    for candidate_id in proposal.selection_json or []:
        if candidate_id in preserved_chunk_ids:
            continue
        row = selected_rows[candidate_id]
        grouped[row["module_type"]].append(current_candidates[candidate_id])
    modules = [(key, grouped[key]) for key in MODULE_ORDER if grouped[key]]
    max_ordinal = (
        db.scalar(select(func.max(LearningModule.ordinal)).where(LearningModule.path_id == path.id))
        or 0
    )
    future_minutes = append_curriculum_modules(
        db,
        path=path,
        modules=modules,
        profile=learning_session.profile,
        start_ordinal=max_ordinal + 1,
        excluded_chunk_ids=preserved_chunk_ids,
    )
    db.flush()

    previous_metadata = dict(path.model_metadata or {})
    revision = current_revision + 1
    path.model_metadata = {
        **previous_metadata,
        "planner": "approval-gated-roadmap-planner-v1",
        "profile_fingerprint": profile_fingerprint(learning_session.profile),
        "profile_assessment_version": learning_session.profile.assessment_version,
        "candidate_count": len(stored_rows),
        "revision": revision,
        "preserved_lesson_count": len(preserved_ids),
        "applied_proposal_id": proposal.id,
    }
    path.generation_method = "verified-roadmap-proposal-v1"
    path.estimated_minutes = preserved_minutes + future_minutes
    module_types = [module_type for module_type, items in modules if items]
    path.coverage = {
        key: "covered" if key in module_types else path.coverage.get(key, "not_applicable")
        for key in MODULE_ORDER
    }
    learning_session.completed_lesson_ids = preserved_ids
    total_lessons = (
        db.scalar(
            select(func.count(LearningLesson.id))
            .join(LearningModule, LearningLesson.module_id == LearningModule.id)
            .where(LearningModule.path_id == path.id)
        )
        or 0
    )
    learning_session.status = "active" if total_lessons > len(preserved_ids) else "completed"
    proposal.status = "applied"
    proposal.applied_at = utc_now()
    proposal.verification_json = verification
    db.add(
        JourneyEvent(
            learning_session_id=learning_session.id,
            event_type="roadmap_applied",
            payload={
                "proposal_id": proposal.id,
                "base_revision": proposal.base_revision,
                "revision": revision,
                "preserved_lesson_ids": preserved_ids,
                "selected_candidate_ids": list(selected_set),
            },
        )
    )
    db.flush()
    return AppliedRoadmap(
        proposal_id=proposal.id,
        path_id=path.id,
        preserved_lesson_ids=preserved_ids,
        revision=revision,
    )


def verify_roadmap_selection(
    candidates: list[dict],
    selected_ids: list[str],
    *,
    max_lessons: int,
) -> dict:
    errors: list[str] = []
    by_id = {row.get("candidate_id"): row for row in candidates}
    if len(selected_ids) != len(set(selected_ids)):
        errors.append("duplicate candidate IDs")
    unknown = [candidate_id for candidate_id in selected_ids if candidate_id not in by_id]
    if unknown:
        errors.append(f"unknown candidate IDs: {', '.join(unknown)}")
    if len(selected_ids) > min(MAX_PROPOSAL_LESSONS, max_lessons):
        errors.append("selected lesson count exceeds the proposal limit")
    missing_evidence = [
        candidate_id
        for candidate_id in selected_ids
        if candidate_id in by_id and not by_id[candidate_id].get("evidence_ids")
    ]
    if missing_evidence:
        errors.append(f"missing evidence: {', '.join(missing_evidence)}")
    required = [
        str(row["candidate_id"])
        for row in candidates
        if row.get("required") and row.get("candidate_id") not in selected_ids
    ]
    if required:
        errors.append(f"required coverage missing: {', '.join(required)}")
    positions = {candidate_id: index for index, candidate_id in enumerate(selected_ids)}
    broken_prerequisites: list[str] = []
    for candidate_id in selected_ids:
        row = by_id.get(candidate_id)
        if row is None:
            continue
        for prerequisite_id in row.get("prerequisite_ids") or []:
            if (
                prerequisite_id not in positions
                or positions[prerequisite_id] > positions[candidate_id]
            ):
                broken_prerequisites.append(f"{prerequisite_id}->{candidate_id}")
    if broken_prerequisites:
        errors.append(f"prerequisite order invalid: {', '.join(broken_prerequisites)}")
    return {
        "valid": not errors,
        "errors": errors,
        "candidate_count": len(candidates),
        "selected_count": len(selected_ids),
        "max_lessons": max_lessons,
        "verifier": "roadmap-coverage-evidence-prerequisite-v1",
    }


def build_roadmap_diff(
    current: list[dict],
    candidates: list[dict],
    selected_ids: list[str],
) -> dict:
    current_ids = [row["candidate_id"] for row in current]
    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    selected = [candidate_by_id[item] for item in selected_ids if item in candidate_by_id]
    selected_set = set(selected_ids)
    current_set = set(current_ids)
    added = [row for row in selected if row["candidate_id"] not in current_set]
    removed = [row for row in current if row["candidate_id"] not in selected_set]
    shared_current = [item for item in current_ids if item in selected_set]
    shared_selected = [item for item in selected_ids if item in current_set]
    current_minutes = sum(int(row.get("estimated_minutes", 0)) for row in current)
    selected_minutes = sum(int(row.get("estimated_minutes", 0)) for row in selected)
    return {
        "added_lessons": [
            {
                "candidate_id": row["candidate_id"],
                "title": row["title"],
                "reason": row["reason"],
            }
            for row in added
        ],
        "removed_lessons": [
            {"candidate_id": row["candidate_id"], "title": row["title"]} for row in removed
        ],
        "selected_lessons": [
            {
                "candidate_id": row["candidate_id"],
                "title": row["title"],
                "module_type": row["module_type"],
            }
            for row in selected
        ],
        "order_changed": shared_current != shared_selected,
        "previous_order": current_ids,
        "proposed_order": selected_ids,
        "previous_estimated_minutes": current_minutes,
        "proposed_estimated_minutes": selected_minutes,
        "estimated_minutes_delta": selected_minutes - current_minutes,
    }


def _load_session(db: Session, session_id: str, *, lock: bool) -> LearningSession:
    statement = (
        select(LearningSession)
        .where(LearningSession.id == session_id)
        .options(
            selectinload(LearningSession.profile),
            selectinload(LearningSession.path)
            .selectinload(LearningPath.modules)
            .selectinload(LearningModule.lessons)
            .selectinload(LearningLesson.steps),
        )
    )
    if lock:
        statement = statement.with_for_update()
    learning_session = db.scalar(statement)
    if learning_session is None:
        raise ValueError("Learning session not found")
    return learning_session


def _candidate_rows(
    planned: list[tuple[str, list[CurriculumCandidate]]],
    pace: str,
    focus: set[str],
) -> list[dict]:
    rows: list[dict] = []
    previous_required_id: str | None = None
    for module_type, items in planned:
        ranked = sorted(
            items,
            key=lambda item: (
                0 if focus.intersection(item.concept_ids) else 1,
                items.index(item),
            ),
        )
        required_id = ranked[0].chunk_id if ranked else None
        for item in ranked:
            concepts = list(item.concept_ids)
            matched = sorted(focus.intersection(concepts))
            rows.append(
                {
                    "candidate_id": item.chunk_id,
                    "module_type": module_type,
                    "title": item.symbol_name or item.path,
                    "path": item.path,
                    "evidence_ids": [item.evidence_id],
                    "concept_ids": concepts,
                    "estimated_minutes": _estimated_minutes(item, pace),
                    "required": item.chunk_id == required_id,
                    "prerequisite_ids": [previous_required_id] if previous_required_id else [],
                    "reason": (
                        f"취약 개념 {', '.join(matched)} 보강"
                        if matched
                        else f"{module_type} 범위의 검증된 코드 근거"
                    ),
                }
            )
        if required_id:
            previous_required_id = required_id
    return rows


def _deterministic_selection(candidates: list[dict], *, max_lessons: int) -> list[str]:
    limit = min(MAX_PROPOSAL_LESSONS, max_lessons)
    required = [row["candidate_id"] for row in candidates if row.get("required")]
    selected = set(required)
    for row in candidates:
        if len(selected) >= limit:
            break
        selected.add(row["candidate_id"])
    return [row["candidate_id"] for row in candidates if row["candidate_id"] in selected]


def _current_incomplete_candidates(learning_session: LearningSession) -> list[dict]:
    completed = set(learning_session.completed_lesson_ids or [])
    result: list[dict] = []
    for module in sorted(learning_session.path.modules, key=lambda item: item.ordinal):
        for lesson in sorted(module.lessons, key=lambda item: item.ordinal):
            if lesson.id in completed:
                continue
            chunk_id = next((step.chunk_id for step in lesson.steps if step.chunk_id), None)
            if chunk_id is None:
                continue
            result.append(
                {
                    "candidate_id": chunk_id,
                    "title": lesson.title,
                    "module_type": module.module_type,
                    "estimated_minutes": lesson.estimated_minutes,
                }
            )
    return result


def _estimated_minutes(candidate: CurriculumCandidate, pace: str) -> int:
    base = 4 if candidate.chunk_type == "symbol" else 3
    if pace == "careful":
        return base + 2
    if pace == "fast":
        return max(2, base - 1)
    return base
