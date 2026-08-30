from __future__ import annotations

REALTIME_FUNCTION_TOOLS: list[dict] = [
    {
        "type": "function",
        "name": "answer_with_repository_evidence",
        "description": "현재 저장소와 레슨의 검증된 코드 근거로 질문에 답한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                "answer_depth": {
                    "type": "string",
                    "enum": ["beginner", "standard", "advanced"],
                },
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "start_deep_learning_task",
        "description": "자료 탐색, 영향 분석, 로드맵 생성처럼 시간이 걸리는 작업을 시작한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": [
                        "research_materials",
                        "impact_analysis",
                        "roadmap_proposal",
                        "deep_explanation",
                    ],
                },
                "request": {"type": "string", "minLength": 1, "maxLength": 4000},
                "source_policy": {
                    "type": "string",
                    "enum": ["repository_only", "official_docs_only"],
                },
            },
            "required": ["task_type", "request"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "apply_learning_action",
        "description": "현재 레슨에서 허용된 결정적 학습 동작을 실행한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "understood",
                        "needs_help",
                        "skip",
                        "next",
                        "return",
                        "submit_choice",
                    ],
                },
                "choice_id": {"type": ["string", "null"]},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
]


def realtime_tool_names() -> set[str]:
    return {str(tool["name"]) for tool in REALTIME_FUNCTION_TOOLS}
