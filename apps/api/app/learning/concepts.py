from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Concept, ConceptEdge, LearnerProfile, MasteryEvent

GRAPH_VERSION = "ts-web-concepts-v1"
MASTERY_THRESHOLD = 0.55


@dataclass(frozen=True)
class ConceptSeed:
    id: str
    display_name: str
    description: str
    domain: str
    difficulty: str = "beginner"


@dataclass(frozen=True)
class EdgeSeed:
    source: str
    target: str
    rationale: str
    confidence: float = 1.0


@dataclass(frozen=True)
class ConceptGap:
    concept_id: str
    display_name: str
    required_for: str
    depth: int
    score: float
    confidence: float
    rationale: str
    relation_confidence: float

    def payload(self) -> dict:
        return {
            "concept_id": self.concept_id,
            "display_name": self.display_name,
            "required_for": self.required_for,
            "depth": self.depth,
            "score": self.score,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "relation_confidence": self.relation_confidence,
        }


CONCEPT_REGISTRY = (
    ConceptSeed("variable", "변수와 선언", "값에 이름을 붙여 흐름 안에서 참조합니다.", "syntax"),
    ConceptSeed("function", "함수", "입력, 실행, 출력을 하나의 호출 단위로 묶습니다.", "syntax"),
    ConceptSeed("return", "반환", "함수 결과를 호출자에게 전달합니다.", "control_flow"),
    ConceptSeed("call", "함수 호출", "다른 함수로 실행 제어와 인수를 전달합니다.", "control_flow"),
    ConceptSeed("conditional", "조건 분기", "조건에 따라 실행 경로를 선택합니다.", "control_flow"),
    ConceptSeed("loop", "반복", "같은 처리를 여러 값이나 조건에 적용합니다.", "control_flow"),
    ConceptSeed(
        "module", "모듈", "파일 사이에서 이름과 책임을 가져오고 내보냅니다.", "architecture"
    ),
    ConceptSeed("class", "클래스", "데이터와 관련 동작을 하나의 설계로 묶습니다.", "syntax"),
    ConceptSeed("promise", "Promise", "미래에 완료될 비동기 작업을 값처럼 표현합니다.", "async"),
    ConceptSeed(
        "async_await", "비동기와 await", "비동기 결과를 기다리는 실행 순서를 표현합니다.", "async"
    ),
    ConceptSeed(
        "exception_handling", "예외 처리", "실패 흐름을 정상 흐름과 분리합니다.", "control_flow"
    ),
    ConceptSeed(
        "generic_type",
        "제네릭 타입",
        "구체 타입을 나중에 정하면서 타입 관계를 유지합니다.",
        "typescript",
        "intermediate",
    ),
    ConceptSeed("react_props", "React props", "부모가 컴포넌트에 전달하는 입력입니다.", "react"),
    ConceptSeed(
        "react_state", "React state", "화면 변화에 따라 유지되는 컴포넌트 상태입니다.", "react"
    ),
    ConceptSeed(
        "react_component",
        "React 컴포넌트",
        "입력과 상태로 화면 일부를 렌더링하는 단위입니다.",
        "react",
    ),
    ConceptSeed("http_request", "HTTP 요청", "클라이언트와 서버 사이의 요청과 응답입니다.", "web"),
    ConceptSeed(
        "framework_routing",
        "프레임워크 라우팅",
        "URL과 요청을 화면 또는 서버 로직에 연결합니다.",
        "web",
        "intermediate",
    ),
)


EDGE_REGISTRY = (
    EdgeSeed("variable", "function", "함수의 매개변수와 지역 값을 읽기 위해 필요합니다."),
    EdgeSeed("function", "return", "반환은 함수의 출력 계약 안에서 동작합니다."),
    EdgeSeed("function", "call", "호출 전 함수의 입력과 제어 이동을 알아야 합니다."),
    EdgeSeed("function", "promise", "Promise를 생성하고 소비하는 주체가 함수입니다."),
    EdgeSeed("promise", "async_await", "await가 기다리는 대상은 Promise 기반 작업입니다."),
    EdgeSeed("conditional", "exception_handling", "오류 조건과 정상 조건의 분기를 구분합니다."),
    EdgeSeed("function", "exception_handling", "예외는 함수 호출 경계를 따라 전달됩니다."),
    EdgeSeed("variable", "generic_type", "제네릭이 적용되는 값과 타입의 관계를 먼저 봅니다."),
    EdgeSeed("function", "generic_type", "제네릭 함수의 입력과 반환 타입을 해석합니다."),
    EdgeSeed("variable", "react_props", "props 값을 읽고 이름으로 참조합니다."),
    EdgeSeed("variable", "react_state", "state 값과 갱신 함수를 구분합니다."),
    EdgeSeed("react_props", "react_component", "컴포넌트 입력 경계를 이해하는 데 필요합니다."),
    EdgeSeed("react_state", "react_component", "상태 변화와 재렌더링 관계를 이해합니다."),
    EdgeSeed("function", "react_component", "함수 컴포넌트의 호출과 반환을 해석합니다."),
    EdgeSeed("module", "react_component", "컴포넌트 import와 export 경계를 해석합니다."),
    EdgeSeed("promise", "http_request", "비동기 응답과 실패를 Promise로 처리합니다."),
    EdgeSeed("async_await", "http_request", "요청 완료를 기다리는 실행 순서를 읽습니다."),
    EdgeSeed("module", "framework_routing", "파일과 route의 공개 경계를 파악합니다."),
    EdgeSeed("function", "framework_routing", "route handler의 입력과 반환을 해석합니다."),
    EdgeSeed("http_request", "framework_routing", "URL, method, 응답의 의미를 알아야 합니다."),
)


def ensure_concept_graph(db: Session) -> None:
    existing = {item.id: item for item in db.scalars(select(Concept)).all()}
    for seed in CONCEPT_REGISTRY:
        concept = existing.get(seed.id)
        if concept is None:
            db.add(
                Concept(
                    id=seed.id,
                    display_name=seed.display_name,
                    description=seed.description,
                    domain=seed.domain,
                    difficulty=seed.difficulty,
                    graph_version=GRAPH_VERSION,
                    metadata_json={},
                )
            )
        else:
            concept.display_name = seed.display_name
            concept.description = seed.description
            concept.domain = seed.domain
            concept.difficulty = seed.difficulty
            concept.graph_version = GRAPH_VERSION
    db.flush()

    existing_edges = set(
        db.execute(
            select(
                ConceptEdge.source_concept_id,
                ConceptEdge.target_concept_id,
                ConceptEdge.relation,
                ConceptEdge.graph_version,
            )
        ).all()
    )
    for edge in EDGE_REGISTRY:
        key = (edge.source, edge.target, "PREREQUISITE_OF", GRAPH_VERSION)
        if key in existing_edges:
            continue
        db.add(
            ConceptEdge(
                source_concept_id=edge.source,
                target_concept_id=edge.target,
                relation="PREREQUISITE_OF",
                confidence=edge.confidence,
                rationale=edge.rationale,
                source="curated-mvp",
                graph_version=GRAPH_VERSION,
            )
        )
    db.flush()


def resolve_concept_gaps(
    db: Session,
    *,
    profile: LearnerProfile,
    required_concept_ids: list[str],
    limit: int = 3,
) -> list[ConceptGap]:
    ensure_concept_graph(db)
    required = list(dict.fromkeys(item for item in required_concept_ids if item))
    if not required:
        return []
    concepts = {item.id: item for item in db.scalars(select(Concept)).all()}
    edges = db.scalars(
        select(ConceptEdge).where(
            ConceptEdge.target_concept_id.in_(required),
            ConceptEdge.relation == "PREREQUISITE_OF",
            ConceptEdge.graph_version == GRAPH_VERSION,
        )
    ).all()
    return select_concept_gaps(
        required_concept_ids=required,
        mastery=profile.concept_mastery or {},
        concept_names={item.id: item.display_name for item in concepts.values()},
        prerequisite_edges=[
            (
                edge.source_concept_id,
                edge.target_concept_id,
                edge.rationale,
                edge.confidence,
            )
            for edge in edges
        ],
        limit=limit,
    )


def select_concept_gaps(
    *,
    required_concept_ids: list[str],
    mastery: dict,
    concept_names: dict[str, str],
    prerequisite_edges: list[tuple[str, str, str, float]],
    limit: int = 3,
) -> list[ConceptGap]:
    required = list(dict.fromkeys(item for item in required_concept_ids if item))
    by_target: defaultdict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for source, target, rationale, confidence in prerequisite_edges:
        by_target[target].append((source, rationale, confidence))
    candidates: list[ConceptGap] = []
    for target_id in required:
        direct_missing: list[ConceptGap] = []
        for source_id, rationale, relation_confidence in by_target.get(target_id, []):
            state = mastery.get(source_id) or {}
            score = float(state.get("score", 0.5))
            confidence = float(state.get("confidence", 0.0))
            if state and score >= MASTERY_THRESHOLD and confidence >= 0.25:
                continue
            direct_missing.append(
                ConceptGap(
                    concept_id=source_id,
                    display_name=concept_names.get(source_id, source_id.replace("_", " ").title()),
                    required_for=target_id,
                    depth=1,
                    score=score,
                    confidence=confidence,
                    rationale=rationale,
                    relation_confidence=relation_confidence,
                )
            )
        if direct_missing:
            candidates.extend(
                sorted(direct_missing, key=lambda item: (item.score, item.confidence))
            )
            continue
        target_state = mastery.get(target_id) or {}
        target_score = float(target_state.get("score", 0.5))
        target_confidence = float(target_state.get("confidence", 0.0))
        if not target_state or target_score < MASTERY_THRESHOLD:
            display_name = concept_names.get(target_id)
            if display_name:
                candidates.append(
                    ConceptGap(
                        concept_id=target_id,
                        display_name=display_name,
                        required_for=target_id,
                        depth=0,
                        score=target_score,
                        confidence=target_confidence,
                        rationale="직접 선수 개념은 충분하므로 현재 개념 자체를 짧게 보충합니다.",
                        relation_confidence=1.0,
                    )
                )

    unique: dict[str, ConceptGap] = {}
    for item in sorted(
        candidates,
        key=lambda gap: (gap.depth == 0, gap.score, gap.confidence, gap.concept_id),
    ):
        unique.setdefault(item.concept_id, item)
    return list(unique.values())[:limit]


def build_mastery_overview(db: Session, profile: LearnerProfile) -> dict:
    ensure_concept_graph(db)
    concepts = db.scalars(
        select(Concept)
        .where(Concept.graph_version == GRAPH_VERSION)
        .order_by(Concept.domain, Concept.display_name)
    ).all()
    edges = db.scalars(
        select(ConceptEdge).where(
            ConceptEdge.relation == "PREREQUISITE_OF",
            ConceptEdge.graph_version == GRAPH_VERSION,
        )
    ).all()
    prerequisites: defaultdict[str, list[str]] = defaultdict(list)
    for edge in edges:
        prerequisites[edge.target_concept_id].append(edge.source_concept_id)
    events = db.scalars(
        select(MasteryEvent)
        .where(MasteryEvent.learner_profile_id == profile.id)
        .order_by(MasteryEvent.created_at.desc())
        .limit(200)
    ).all()
    event_counts = Counter(item.concept_id for item in events)
    latest_event = {}
    for event in events:
        latest_event.setdefault(event.concept_id, event)

    mastery = profile.concept_mastery or {}
    states: list[dict] = []
    summary = Counter()
    for concept in concepts:
        value = mastery.get(concept.id) or {}
        score = float(value.get("score", 0.5))
        confidence = float(value.get("confidence", 0.0))
        state = _mastery_state(bool(value), score, confidence)
        summary[state] += 1
        latest = latest_event.get(concept.id)
        states.append(
            {
                "concept_id": concept.id,
                "display_name": concept.display_name,
                "description": concept.description,
                "domain": concept.domain,
                "difficulty": concept.difficulty,
                "score": score,
                "confidence": confidence,
                "state": state,
                "source": value.get("source"),
                "prerequisite_ids": sorted(prerequisites.get(concept.id, [])),
                "event_count": event_counts[concept.id],
                "last_event_at": latest.created_at if latest else None,
            }
        )
    state_rank = {"needs_review": 0, "developing": 1, "ready": 2, "unknown": 3}
    states.sort(
        key=lambda item: (
            state_rank[item["state"]],
            -item["event_count"],
            item["display_name"],
        )
    )
    return {
        "profile_id": profile.id,
        "graph_version": GRAPH_VERSION,
        "summary": {
            "ready": summary["ready"],
            "developing": summary["developing"],
            "needs_review": summary["needs_review"],
            "unknown": summary["unknown"],
            "total": len(states),
        },
        "concepts": states,
        "recent_events": events[:30],
    }


def concept_definition(concept_id: str) -> tuple[str, str]:
    seed = next((item for item in CONCEPT_REGISTRY if item.id == concept_id), None)
    if seed is None:
        return (
            concept_id.replace("_", " ").title(),
            "현재 코드를 읽기 위해 필요한 핵심 개념입니다.",
        )
    return seed.display_name, seed.description


def _mastery_state(has_value: bool, score: float, confidence: float) -> str:
    if not has_value or confidence < 0.2:
        return "unknown"
    if score < MASTERY_THRESHOLD:
        return "needs_review"
    if score < 0.75 or confidence < 0.6:
        return "developing"
    return "ready"
