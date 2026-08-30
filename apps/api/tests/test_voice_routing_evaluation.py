from app.core.config import REPOSITORY_ROOT
from app.evaluation.voice_routing import (
    DeterministicFakeRoutingProvider,
    VoiceRoutingFixture,
    evaluate_fixture,
    evaluate_provider,
)


def fixture() -> VoiceRoutingFixture:
    path = REPOSITORY_ROOT / "apps/api/evaluation/fixtures/voice_routing_ko_v1.json"
    return VoiceRoutingFixture.model_validate_json(path.read_text(encoding="utf-8"))


def test_voice_routing_fixture_has_required_100_case_distribution():
    loaded = fixture()
    report = evaluate_fixture(loaded)

    assert len(loaded.cases) == 100
    assert report["category_counts_match"] is True
    assert report["category_counts"] == loaded.expected_category_counts


def test_mini_and_full_fake_provider_pass_same_contract_fixture():
    loaded = fixture()
    for model in ("gpt-realtime-2.1-mini", "gpt-realtime-2.1"):
        report = evaluate_provider(loaded, DeterministicFakeRoutingProvider(model))
        assert report["passed"] is True
        assert report["metrics"] == {
            "route_accuracy": 1.0,
            "tool_accuracy": 1.0,
            "forbidden_direct_answer_rate": 0.0,
            "required_context_recall": 1.0,
        }
