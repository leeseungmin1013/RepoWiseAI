from __future__ import annotations

from dataclasses import dataclass

ASSESSMENT_VERSION = "stack-diagnostic-v1"


@dataclass(frozen=True)
class AssessmentQuestion:
    id: str
    category: str
    prompt: str
    choices: tuple[tuple[str, str], ...]
    concept_id: str | None = None
    answer_key: str | None = None
    stack_requirement: str | None = None

    def stored_payload(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "prompt": self.prompt,
            "choices": [{"value": value, "label": label} for value, label in self.choices],
            "concept_id": self.concept_id,
            "answer_key": self.answer_key,
            "stack_requirement": self.stack_requirement,
        }

    def public_payload(self) -> dict:
        payload = self.stored_payload()
        payload.pop("answer_key")
        return payload


COMMON_QUESTIONS = (
    AssessmentQuestion(
        id="goal",
        category="goal",
        prompt="이 저장소를 이해하려는 가장 큰 목표는 무엇인가요?",
        choices=(
            ("understand_whole_project", "프로젝트 전체를 이해하고 싶어요"),
            ("modify_feature", "특정 기능을 수정할 준비를 하고 싶어요"),
            ("learn_programming", "코드를 보며 프로그래밍을 공부하고 싶어요"),
        ),
    ),
    AssessmentQuestion(
        id="preferred_explanation",
        category="preference",
        prompt="막힌 코드를 어떤 방식으로 먼저 설명받고 싶나요?",
        choices=(
            ("line_by_line", "코드를 한 줄씩 따라가고 싶어요"),
            ("analogy", "쉬운 비유와 작은 예시가 좋아요"),
            ("architecture", "전체 구조와 역할부터 보고 싶어요"),
        ),
    ),
    AssessmentQuestion(
        id="javascript_experience",
        category="self_report",
        prompt="JavaScript 또는 TypeScript 코드를 읽어본 경험은 어느 정도인가요?",
        choices=(
            ("none", "거의 없어요"),
            ("basic", "변수와 함수 정도는 알아요"),
            ("comfortable", "함수와 객체 코드를 편하게 읽어요"),
        ),
        concept_id="function",
    ),
    AssessmentQuestion(
        id="function_flow",
        category="objective",
        prompt="함수가 다른 함수를 호출하면 프로그램은 보통 어디로 진행할까요?",
        choices=(
            ("next_line", "호출을 건너뛰고 바로 다음 줄로 갑니다"),
            ("called_function", "호출된 함수로 이동한 뒤 결과를 가지고 돌아옵니다"),
            ("file_start", "현재 파일의 첫 줄로 돌아갑니다"),
        ),
        concept_id="function",
        answer_key="called_function",
    ),
    AssessmentQuestion(
        id="async_order",
        category="objective",
        prompt="await를 만나면 async 함수는 보통 어떻게 동작할까요?",
        choices=(
            ("stop_app", "애플리케이션 전체를 멈춥니다"),
            ("wait_then_continue", "해당 작업의 결과를 기다린 뒤 다음 줄을 계속합니다"),
            ("skip_result", "결과를 무시하고 함수를 끝냅니다"),
        ),
        concept_id="async_await",
        answer_key="wait_then_continue",
    ),
    AssessmentQuestion(
        id="pace",
        category="preference",
        prompt="학습 경로의 진행 속도는 어느 쪽이 편한가요?",
        choices=(
            ("careful", "꼼꼼하게 배경부터 확인"),
            ("balanced", "핵심 코드와 개념을 균형 있게"),
            ("fast", "중요한 구조와 흐름만 빠르게"),
        ),
    ),
)

STACK_QUESTIONS = {
    "React": AssessmentQuestion(
        id="react_experience",
        category="self_report",
        prompt="React의 component, props, state가 익숙한가요?",
        choices=(
            ("none", "아직 잘 몰라요"),
            ("basic", "이름과 역할은 들어봤어요"),
            ("comfortable", "간단한 component를 읽고 수정할 수 있어요"),
        ),
        concept_id="react_component",
        stack_requirement="React",
    ),
    "Next.js": AssessmentQuestion(
        id="next_route",
        category="self_report",
        prompt="Next.js의 page 또는 route 파일 구조가 익숙한가요?",
        choices=(
            ("none", "처음 봐요"),
            ("basic", "page와 route가 있다는 것은 알아요"),
            ("comfortable", "App Router 흐름을 읽을 수 있어요"),
        ),
        concept_id="framework_routing",
        stack_requirement="Next.js",
    ),
}


def questions_for_stack(stack: list[str]) -> list[AssessmentQuestion]:
    questions = list(COMMON_QUESTIONS)
    for name in ("React", "Next.js"):
        if name in stack:
            questions.append(STACK_QUESTIONS[name])
            break
    return questions


def merge_questions_for_stack(existing: list[dict], stack: list[str]) -> list[dict]:
    merged = [dict(item) for item in existing]
    existing_ids = {item.get("id") for item in merged}
    for question in questions_for_stack(stack):
        if question.id not in existing_ids:
            merged.append(question.stored_payload())
            existing_ids.add(question.id)
    return merged


def question_by_id(questions: list[dict], item_id: str) -> dict | None:
    return next((item for item in questions if item.get("id") == item_id), None)
