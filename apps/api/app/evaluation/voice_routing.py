from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import REPOSITORY_ROOT
from app.voice.commands import VoiceCommandContext, parse_deterministic_command

Route = Literal[
    "learning_command",
    "short_conversation",
    "grounded_question",
    "deep_task",
]


class VoiceRoutingCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    utterance: str
    category: str
    expected_route: Route
    allowed_tool: str | None
    forbidden_direct_answer: bool
    required_context: list[str] = Field(default_factory=list)


class VoiceRoutingFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    cases: list[VoiceRoutingCase] = Field(min_length=100)
    expected_category_counts: dict[str, int]
    thresholds: dict[str, float]


class RoutingPrediction(BaseModel):
    route: Route
    tool_name: str | None
    direct_answer: bool
    used_context: list[str]


class RoutingProvider(Protocol):
    name: str

    def route(self, case: VoiceRoutingCase) -> RoutingPrediction: ...


class DeterministicFakeRoutingProvider:
    """Offline routing seam used for reproducible mini/full contract evaluation."""

    def __init__(self, model: str) -> None:
        self.name = model

    def route(self, case: VoiceRoutingCase) -> RoutingPrediction:
        command = parse_deterministic_command(
            case.utterance,
            VoiceCommandContext(
                has_current_lesson=True,
                has_previous_lesson=True,
                has_return_target=True,
                choice_ids=("choice_a", "choice_b", "choice_c", "choice_d"),
                choice_labels={"choice_a": "첫 번째 선택"},
            ),
        )
        if command.is_confident:
            return RoutingPrediction(
                route="learning_command",
                tool_name="apply_learning_action",
                direct_answer=False,
                used_context=case.required_context,
            )

        normalized = case.utterance.casefold()
        if any(marker in normalized for marker in ("공식", "문서", "자료", "튜토리얼")):
            route: Route = "deep_task"
            tool = "start_deep_learning_task"
        elif any(marker in normalized for marker in ("로드맵", "학습 경로", "커리큘럼")):
            route = "deep_task"
            tool = "start_deep_learning_task"
        elif any(
            marker in normalized
            for marker in ("영향", "다중 파일", "호출 체인", "어디까지 바뀌", "파급")
        ):
            route = "deep_task"
            tool = "start_deep_learning_task"
        elif any(
            marker in normalized
            for marker in ("안녕", "고마워", "맞아?", "무슨 뜻", "잘 들려", "잠깐")
        ):
            route = "short_conversation"
            tool = None
        else:
            route = "grounded_question"
            tool = "answer_with_repository_evidence"
        return RoutingPrediction(
            route=route,
            tool_name=tool,
            direct_answer=route == "short_conversation",
            used_context=case.required_context,
        )


def evaluate_provider(
    fixture: VoiceRoutingFixture,
    provider: RoutingProvider,
) -> dict:
    route_hits = 0
    tool_hits = 0
    forbidden_direct_answer_violations = 0
    required_context_total = 0
    required_context_hits = 0
    failures: list[dict[str, str]] = []
    for case in fixture.cases:
        prediction = provider.route(case)
        route_ok = prediction.route == case.expected_route
        tool_ok = prediction.tool_name == case.allowed_tool
        violation = case.forbidden_direct_answer and prediction.direct_answer
        expected_context = set(case.required_context)
        actual_context = set(prediction.used_context)
        context_hits = len(expected_context & actual_context)
        route_hits += int(route_ok)
        tool_hits += int(tool_ok)
        forbidden_direct_answer_violations += int(violation)
        required_context_total += len(expected_context)
        required_context_hits += context_hits
        if not route_ok or not tool_ok or violation or context_hits != len(expected_context):
            failures.append(
                {
                    "id": case.id,
                    "expected_route": case.expected_route,
                    "actual_route": prediction.route,
                }
            )

    count = len(fixture.cases)
    context_recall = (
        required_context_hits / required_context_total if required_context_total else 1.0
    )
    metrics = {
        "route_accuracy": round(route_hits / count, 4),
        "tool_accuracy": round(tool_hits / count, 4),
        "forbidden_direct_answer_rate": round(
            forbidden_direct_answer_violations / count,
            4,
        ),
        "required_context_recall": round(context_recall, 4),
    }
    passed = all(
        (
            metrics[name] <= threshold
            if name == "forbidden_direct_answer_rate"
            else metrics[name] >= threshold
        )
        for name, threshold in fixture.thresholds.items()
    )
    return {
        "model": provider.name,
        "provider": "deterministic_fake",
        "case_count": count,
        "metrics": metrics,
        "failures": failures,
        "passed": passed and not failures,
    }


def evaluate_fixture(fixture: VoiceRoutingFixture) -> dict:
    actual_counts = dict(Counter(case.category for case in fixture.cases))
    counts_match = actual_counts == fixture.expected_category_counts
    reports = [
        evaluate_provider(fixture, DeterministicFakeRoutingProvider(model))
        for model in ("gpt-realtime-2.1-mini", "gpt-realtime-2.1")
    ]
    return {
        "fixture": fixture.name,
        "evaluation_mode": "offline_fake_provider",
        "category_counts": actual_counts,
        "expected_category_counts": fixture.expected_category_counts,
        "category_counts_match": counts_match,
        "models": reports,
        "passed": counts_match and all(report["passed"] for report in reports),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Korean voice routing contracts")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("apps/api/evaluation/fixtures/voice_routing_ko_v1.json"),
    )
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args()
    fixture_path = args.fixture if args.fixture.is_absolute() else REPOSITORY_ROOT / args.fixture
    fixture = VoiceRoutingFixture.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    report = evaluate_fixture(fixture)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report_out:
        report_path = (
            args.report_out if args.report_out.is_absolute() else REPOSITORY_ROOT / args.report_out
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n", encoding="utf-8")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
