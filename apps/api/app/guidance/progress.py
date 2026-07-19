from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FeedbackType = Literal["opened", "understood", "needs_help"]


@dataclass(frozen=True)
class ProgressUpdate:
    preferred_style: str
    status: str
    current_step_ordinal: int
    completed_step_ids: list[str]
    needs_help_step_ids: list[str]


def apply_progress_event(
    *,
    ordered_step_ids: list[str],
    current_step_ordinal: int,
    completed_step_ids: list[str],
    needs_help_step_ids: list[str],
    preferred_style: str,
    step_id: str,
    event_type: FeedbackType,
) -> ProgressUpdate:
    if step_id not in ordered_step_ids:
        raise ValueError("Step does not belong to this guided path")
    if not ordered_step_ids:
        raise ValueError("Guided path has no steps")

    completed = list(dict.fromkeys(completed_step_ids))
    needs_help = list(dict.fromkeys(needs_help_step_ids))
    current_index = min(max(current_step_ordinal - 1, 0), len(ordered_step_ids) - 1)
    current_step_id = ordered_step_ids[current_index]

    if event_type in {"understood", "needs_help"} and step_id != current_step_id:
        raise ValueError("Feedback can only update the current guided step")

    projected_status = "completed" if len(completed) == len(ordered_step_ids) else "active"
    if event_type == "needs_help":
        if step_id not in needs_help:
            needs_help.append(step_id)
        preferred_style = {"advanced": "standard", "standard": "beginner"}.get(
            preferred_style, "beginner"
        )
    elif event_type == "understood":
        if step_id not in completed:
            completed.append(step_id)
        remaining = [item for item in ordered_step_ids if item not in completed]
        if not remaining:
            return ProgressUpdate(
                preferred_style=preferred_style,
                status="completed",
                current_step_ordinal=len(ordered_step_ids),
                completed_step_ids=completed,
                needs_help_step_ids=needs_help,
            )
        current_step_ordinal = ordered_step_ids.index(remaining[0]) + 1

    return ProgressUpdate(
        preferred_style=preferred_style,
        status=projected_status,
        current_step_ordinal=current_step_ordinal,
        completed_step_ids=completed,
        needs_help_step_ids=needs_help,
    )
