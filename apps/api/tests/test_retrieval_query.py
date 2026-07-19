from app.retrieval.query import analyze_query


def test_extracts_identifiers_and_location_intent() -> None:
    result = analyze_query("loginUser 함수는 어느 파일에 있어?")

    assert result.intent == "location"
    assert "loginuser" in result.exact_terms
    assert "login" in result.lexical_query


def test_detects_flow_questions() -> None:
    result = analyze_query("로그인 요청의 실행 흐름을 설명해줘")

    assert result.intent == "flow"
    assert "call" in result.lexical_query


def test_expands_korean_entrypoint_question_for_english_code() -> None:
    result = analyze_query("이 프로젝트의 진입점은 어디야?")

    assert "entry_point" in result.hints
    assert "index" in result.lexical_query
    assert "default" in result.lexical_query
