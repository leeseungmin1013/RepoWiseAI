from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learning.concepts import concept_definition
from app.models import KnowledgeSource, LearnerProfile


@dataclass(frozen=True)
class SourceSeed:
    concept_id: str
    title: str
    publisher: str
    canonical_url: str
    difficulty: str = "beginner"
    language: str = "en"
    estimated_minutes: int = 10


SOURCE_REGISTRY = (
    SourceSeed(
        "function",
        "Functions",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Functions",
        estimated_minutes=12,
    ),
    SourceSeed(
        "variable",
        "Grammar and types: declarations",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Grammar_and_types#declarations",
        estimated_minutes=8,
    ),
    SourceSeed(
        "conditional",
        "Control flow and error handling",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Control_flow_and_error_handling",
    ),
    SourceSeed(
        "loop",
        "Loops and iteration",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Loops_and_iteration",
    ),
    SourceSeed(
        "return",
        "return statement",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/return",
        estimated_minutes=5,
    ),
    SourceSeed(
        "async_await",
        "async function",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function",
    ),
    SourceSeed(
        "async_await",
        "await operator",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/await",
        estimated_minutes=8,
    ),
    SourceSeed(
        "promise",
        "Using promises",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Using_promises",
        estimated_minutes=15,
    ),
    SourceSeed(
        "exception_handling",
        "try...catch",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/try...catch",
        estimated_minutes=8,
    ),
    SourceSeed(
        "class",
        "Classes",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Classes",
        estimated_minutes=12,
    ),
    SourceSeed(
        "generic_type",
        "Generics",
        "TypeScript Handbook",
        "https://www.typescriptlang.org/docs/handbook/2/generics.html",
        difficulty="intermediate",
        estimated_minutes=15,
    ),
    SourceSeed(
        "react_component",
        "Your First Component",
        "React",
        "https://react.dev/learn/your-first-component",
    ),
    SourceSeed(
        "react_component",
        "Passing Props to a Component",
        "React",
        "https://react.dev/learn/passing-props-to-a-component",
    ),
    SourceSeed(
        "react_props",
        "Passing Props to a Component",
        "React",
        "https://react.dev/learn/passing-props-to-a-component",
    ),
    SourceSeed(
        "react_state",
        "Managing State",
        "React",
        "https://react.dev/learn/managing-state",
        estimated_minutes=15,
    ),
    SourceSeed(
        "module",
        "JavaScript modules",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules",
        estimated_minutes=12,
    ),
    SourceSeed(
        "http_request",
        "Using the Fetch API",
        "MDN Web Docs",
        "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch",
        estimated_minutes=12,
    ),
    SourceSeed(
        "framework_routing",
        "Next.js App Router",
        "Next.js",
        "https://nextjs.org/docs/app",
        difficulty="intermediate",
        estimated_minutes=15,
    ),
)


CONCEPT_COPY = {
    "function": ("함수", "입력을 받아 정해진 작업을 수행하고 결과를 돌려주는 코드 단위입니다."),
    "variable": ("변수와 선언", "값에 이름을 붙여 이후 코드가 그 값을 읽거나 바꿀 수 있게 합니다."),
    "conditional": ("조건 분기", "조건의 참·거짓에 따라 서로 다른 실행 경로를 선택합니다."),
    "loop": ("반복", "같은 규칙을 여러 값이나 조건에 적용합니다."),
    "return": ("반환", "현재 함수를 끝내고 호출한 쪽에 결과를 전달합니다."),
    "async_await": (
        "비동기와 await",
        "오래 걸리는 작업을 기다리는 동안 실행 흐름을 명시적으로 관리합니다.",
    ),
    "promise": ("Promise", "미래에 성공 값이나 실패 이유가 정해질 비동기 작업을 표현합니다."),
    "exception_handling": (
        "예외 처리",
        "실패가 발생했을 때 정상 흐름과 오류 대응 흐름을 분리합니다.",
    ),
    "class": ("클래스", "관련 데이터와 동작을 하나의 설계 단위로 묶습니다."),
    "generic_type": ("제네릭 타입", "구체적인 타입을 나중에 정하면서도 타입 안전성을 유지합니다."),
    "react_component": (
        "React 컴포넌트",
        "화면 일부를 입력(props)과 상태에 따라 렌더링하는 단위입니다.",
    ),
    "framework_routing": ("라우팅", "URL과 요청을 처리할 화면 또는 서버 로직에 연결합니다."),
    "call": ("함수 호출", "정의된 함수에 제어권과 인수를 넘겨 실제 작업을 실행합니다."),
}


def ensure_knowledge_sources(db: Session) -> None:
    existing = set(
        db.execute(select(KnowledgeSource.concept_id, KnowledgeSource.canonical_url)).all()
    )
    for seed in SOURCE_REGISTRY:
        if (seed.concept_id, seed.canonical_url) in existing:
            continue
        db.add(
            KnowledgeSource(
                concept_id=seed.concept_id,
                title=seed.title,
                publisher=seed.publisher,
                canonical_url=seed.canonical_url,
                difficulty=seed.difficulty,
                language=seed.language,
                estimated_minutes=seed.estimated_minutes,
            )
        )


def recommended_sources(
    db: Session,
    concept_ids: list[str],
    profile: LearnerProfile | None = None,
    *,
    limit: int = 6,
) -> list[KnowledgeSource]:
    ensure_knowledge_sources(db)
    db.flush()
    normalized = list(dict.fromkeys(item for item in concept_ids if item)) or [
        "function",
        "variable",
    ]
    sources = db.scalars(
        select(KnowledgeSource).where(KnowledgeSource.concept_id.in_(normalized))
    ).all()
    mastery = profile.concept_mastery if profile else {}

    def rank(source: KnowledgeSource) -> tuple[float, int, str]:
        score = float((mastery.get(source.concept_id) or {}).get("score", 0.5))
        penalty = 1 if source.difficulty == "intermediate" and score < 0.45 else 0
        return (score + penalty, source.estimated_minutes, source.title)

    return sorted(sources, key=rank)[:limit]


def concept_bridge(concept_ids: list[str]) -> list[dict]:
    result: list[dict] = []
    for concept_id in list(dict.fromkeys(concept_ids)):
        title, definition = CONCEPT_COPY.get(concept_id, concept_definition(concept_id))
        result.append(
            {
                "concept_id": concept_id,
                "title": title,
                "definition": definition,
                "check_question": f"현재 코드에서 {title}이 사용되는 위치와 이유를 찾을 수 있나요?",
            }
        )
    return result


def small_examples(concept_ids: list[str]) -> list[dict]:
    examples = {
        "function": "function add(a, b) {\n  return a + b;\n}",
        "variable": "const userName = 'Ada';\nlet retryCount = 0;",
        "conditional": "if (isReady) {\n  start();\n} else {\n  wait();\n}",
        "loop": "for (const item of items) {\n  process(item);\n}",
        "return": "function label(name) {\n  return `Hello ${name}`;\n}",
        "async_await": (
            "async function loadUser() {\n"
            "  const response = await fetch('/user');\n"
            "  return response.json();\n}"
        ),
        "promise": "loadData().then(useData).catch(handleError);",
        "exception_handling": ("try {\n  await save();\n} catch (error) {\n  report(error);\n}"),
        "class": "class Counter {\n  value = 0;\n  increment() { this.value += 1; }\n}",
        "generic_type": ("function first<T>(items: T[]): T | undefined {\n  return items[0];\n}"),
        "react_component": ("function Greeting({ name }) {\n  return <h1>Hello {name}</h1>;\n}"),
        "call": "const result = calculate(input);",
    }
    return [
        {
            "concept_id": concept_id,
            "code": examples.get(
                concept_id, "// 현재 코드의 작은 입력으로 실행 흐름을 따라보세요."
            ),
        }
        for concept_id in list(dict.fromkeys(concept_ids))
    ]
