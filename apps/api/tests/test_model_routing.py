import json

import pytest

from app.core.config import Settings
from app.core.model_routing import ModelRoutingPolicy


def test_alias_model_policy_exposes_role_routes():
    policy = ModelRoutingPolicy.from_settings(Settings())

    assert policy.release_policy == "alias"
    assert policy.for_role("realtime").model == "gpt-realtime-2.1-mini"
    assert policy.for_role("deep").reasoning_effort == "medium"
    assert policy.for_role("realtime_fallback").model == "gpt-realtime-2.1"


def test_snapshot_policy_requires_every_role_and_preserves_effort():
    roles = {
        "general": "general-2026-08-30",
        "realtime": "realtime-2026-08-30",
        "realtime_fallback": "realtime-full-2026-08-30",
        "deep": "deep-2026-08-30",
        "deep_escalation": "deep-high-2026-08-30",
        "research": "research-2026-08-30",
    }
    policy = ModelRoutingPolicy.from_settings(
        Settings(
            model_release_policy="snapshot",
            model_snapshot_overrides_json=json.dumps(roles),
        )
    )

    assert policy.release_policy == "snapshot"
    assert policy.for_role("deep").model == roles["deep"]
    assert policy.for_role("deep").reasoning_effort == "medium"


def test_snapshot_policy_rejects_partial_or_invalid_overrides():
    with pytest.raises(ValueError, match="requires overrides"):
        ModelRoutingPolicy.from_settings(
            Settings(
                model_release_policy="snapshot",
                model_snapshot_overrides_json='{"general":"pinned"}',
            )
        )
    with pytest.raises(ValueError, match="valid JSON"):
        ModelRoutingPolicy.from_settings(
            Settings(
                model_release_policy="snapshot",
                model_snapshot_overrides_json="not-json",
            )
        )
