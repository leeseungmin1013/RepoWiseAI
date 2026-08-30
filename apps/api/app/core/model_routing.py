from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings

ModelRole = Literal[
    "general",
    "realtime",
    "realtime_fallback",
    "deep",
    "deep_escalation",
    "research",
]


@dataclass(frozen=True)
class ModelRoute:
    model: str
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class ModelRoutingPolicy:
    release_policy: Literal["alias", "snapshot"]
    routes: dict[ModelRole, ModelRoute]

    @classmethod
    def from_settings(cls, settings: Settings) -> ModelRoutingPolicy:
        configured: dict[ModelRole, ModelRoute] = {
            "general": ModelRoute(settings.generation_model),
            "realtime": ModelRoute(
                settings.realtime_model,
                settings.realtime_reasoning_effort,
            ),
            "realtime_fallback": ModelRoute(settings.realtime_quality_fallback_model),
            "deep": ModelRoute(settings.deep_model, settings.deep_reasoning_effort),
            "deep_escalation": ModelRoute(
                settings.deep_escalation_model,
                settings.deep_escalation_reasoning_effort,
            ),
            "research": ModelRoute(
                settings.research_model,
                settings.research_reasoning_effort,
            ),
        }
        _validate_routes(configured)
        if settings.model_release_policy == "alias":
            return cls(release_policy="alias", routes=configured)
        try:
            overrides = json.loads(settings.model_snapshot_overrides_json)
        except json.JSONDecodeError as exc:
            raise ValueError("MODEL_SNAPSHOT_OVERRIDES_JSON must be valid JSON") from exc
        if not isinstance(overrides, dict):
            raise ValueError("MODEL_SNAPSHOT_OVERRIDES_JSON must be an object")
        missing = sorted(set(configured) - set(overrides))
        if missing:
            raise ValueError("Snapshot model policy requires overrides for: " + ", ".join(missing))
        pinned = {
            role: ModelRoute(str(overrides[role]).strip(), route.reasoning_effort)
            for role, route in configured.items()
        }
        _validate_routes(pinned)
        return cls(release_policy="snapshot", routes=pinned)

    def for_role(self, role: ModelRole) -> ModelRoute:
        return self.routes[role]


def _validate_routes(routes: dict[ModelRole, ModelRoute]) -> None:
    allowed_efforts = {None, "none", "minimal", "low", "medium", "high", "xhigh"}
    for role, route in routes.items():
        if not route.model or any(character.isspace() for character in route.model):
            raise ValueError(f"Model for role {role} is invalid")
        if route.reasoning_effort not in allowed_efforts:
            raise ValueError(f"Reasoning effort for role {role} is invalid")
