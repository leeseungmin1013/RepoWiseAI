from __future__ import annotations

import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from app.ai.gateway import MeteredOpenAIClient
from app.core.config import Settings
from app.schemas import ArchitectureGraphResponse


class ArchitectureLabelSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str = Field(min_length=1, max_length=80)
    responsibility: str = Field(min_length=1, max_length=240)


class ArchitectureLabelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[ArchitectureLabelSuggestion] = Field(max_length=34)


def apply_architecture_label_suggestions(
    graph: ArchitectureGraphResponse,
    suggestions: list[ArchitectureLabelSuggestion],
) -> ArchitectureGraphResponse:
    allowed_ids = {node.id for node in graph.nodes}
    by_id: dict[str, ArchitectureLabelSuggestion] = {}
    for suggestion in suggestions:
        if suggestion.node_id in allowed_ids and suggestion.node_id not in by_id:
            by_id[suggestion.node_id] = suggestion
    if not by_id:
        return graph
    nodes = [
        node.model_copy(
            update={
                "label": by_id[node.id].label.strip(),
                "responsibility": by_id[node.id].responsibility.strip(),
            }
        )
        if node.id in by_id
        else node
        for node in graph.nodes
    ]
    return graph.model_copy(
        update={
            "nodes": nodes,
            "limitations": [
                *graph.limitations,
                "AI는 기존 node ID와 코드 근거 안에서 이름·책임 설명만 다듬었으며 "
                "노드와 관계를 추가하지 않았습니다.",
            ],
        }
    )


def enhance_architecture_graph_labels(
    graph: ArchitectureGraphResponse,
    settings: Settings,
    recorder: Callable[..., None] | None = None,
) -> ArchitectureGraphResponse:
    if not settings.openai_api_key or settings.generation_provider not in {
        "auto",
        "openai",
    }:
        raise RuntimeError("OpenAI generation is unavailable")

    candidates = [
        {
            "node_id": node.id,
            "current_label": node.label,
            "current_responsibility": node.responsibility,
            "node_type": node.node_type,
            "paths": [evidence.path for evidence in node.evidence],
            "inputs": node.inputs,
            "outputs": node.outputs,
        }
        for node in graph.nodes
    ]
    client = MeteredOpenAIClient(settings.openai_api_key, recorder=recorder)
    response = client.responses_parse(
        model=settings.generation_model,
        input=[
            {
                "role": "system",
                "content": (
                    "Improve repository architecture node labels and one-sentence "
                    "responsibilities in Korean. Select only supplied node_id values. "
                    "Do not add nodes, edges, files, technologies, or runtime claims. "
                    "Keep labels concise and responsibilities grounded in the supplied "
                    "paths, inputs, and outputs."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(candidates, ensure_ascii=False),
            },
        ],
        text_format=ArchitectureLabelPayload,
    )
    payload = response.output_parsed
    if payload is None:
        raise RuntimeError("OpenAI returned no architecture label payload")
    return apply_architecture_label_suggestions(graph, payload.suggestions)
