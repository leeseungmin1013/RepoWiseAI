from __future__ import annotations

import re
from dataclasses import dataclass

from app.analysis.chunking import expand_identifiers

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$.\-/]*")
WORD_PATTERN = re.compile(r"[A-Za-z0-9가-힣_$.-]+")
QUERY_EXPANSIONS = {
    "진입점": ["entry", "entrypoint", "main", "index", "page", "server", "default export"],
    "시작": ["entry", "main", "index", "bootstrap", "initialize"],
    "로그인": ["login", "auth", "authenticate", "session", "token"],
    "사용자": ["user", "account", "profile"],
    "요청": ["request", "fetch", "api", "http", "route", "handler"],
    "실행": ["execute", "run", "call", "await", "return"],
    "흐름": ["flow", "call", "caller", "callee", "next", "handler"],
    "오류": ["error", "exception", "throw", "catch", "reject"],
    "함수": ["function", "method", "handler"],
    "클래스": ["class", "constructor", "instance"],
    "타입": ["type", "interface", "declaration", "definition", "d.ts"],
    "상태": ["state", "store", "reducer", "context"],
    "저장": ["save", "store", "repository", "database"],
    "테스트": ["test", "spec", "fixture", "assert"],
}


@dataclass(frozen=True)
class QueryAnalysis:
    intent: str
    exact_terms: list[str]
    lexical_query: str
    hints: list[str]


def analyze_query(query: str) -> QueryAnalysis:
    lowered = query.lower()
    intent = "explain"
    if any(term in lowered for term in ("어디", "위치", "파일", "where", "locate")):
        intent = "location"
    elif any(term in lowered for term in ("흐름", "호출", "실행", "동작", "flow", "call")):
        intent = "flow"
    elif any(term in lowered for term in ("영향", "바꾸", "수정", "impact", "change")):
        intent = "impact"
    elif any(term in lowered for term in ("문법", "개념", "수학", "원리", "syntax", "concept")):
        intent = "concept"

    exact_terms: list[str] = []
    seen: set[str] = set()
    for term in IDENTIFIER_PATTERN.findall(query):
        normalized = term.strip("./-").lower()
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        exact_terms.append(normalized)

    expanded_terms: list[str] = []
    for trigger, replacements in QUERY_EXPANSIONS.items():
        if trigger in lowered:
            expanded_terms.extend(replacements)
    lexical_terms = [*WORD_PATTERN.findall(expand_identifiers(query)), *expanded_terms]
    lexical_query = " ".join(dict.fromkeys(term.lower() for term in lexical_terms))
    hints = []
    if any(term in lowered for term in ("진입점", "시작", "먼저 읽", "entrypoint")):
        hints.append("entry_point")
    if any(term in lowered for term in ("테스트", "test", "spec")):
        hints.append("test")
    return QueryAnalysis(
        intent=intent,
        exact_terms=exact_terms[:10],
        lexical_query=lexical_query[:1_000],
        hints=hints,
    )
