from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

import tree_sitter_typescript
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from tree_sitter import Language, Node, Parser

from app.ai.gateway import MeteredOpenAIClient
from app.core.config import Settings
from app.models import CodeChunk, ExplanationArtifact, FileRecord, LearningStep
from app.retrieval.hybrid import evidence_id_for_chunk

SEGMENTER_VERSION = "tree-sitter-statements-v1"
SIMPLE_NODES = {
    "import_statement",
    "lexical_declaration",
    "variable_declaration",
    "expression_statement",
    "return_statement",
    "throw_statement",
    "break_statement",
    "continue_statement",
}
STRUCTURAL_NODES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "class_declaration",
    "if_statement",
    "for_statement",
    "for_in_statement",
    "while_statement",
    "switch_statement",
    "try_statement",
    "catch_clause",
}


@dataclass(frozen=True)
class SegmentDraft:
    segment_id: str
    node_type: str
    start_line: int
    end_line: int
    source: str


class OpenAISegment(BaseModel):
    segment_id: str
    what: str
    why: str
    syntax_concepts: list[str]


class OpenAIExplanationPayload(BaseModel):
    segments: list[OpenAISegment]


def get_or_create_line_explanation(
    db: Session,
    *,
    step_id: str,
    depth_band: str,
    settings: Settings,
    recorder: Callable[..., None] | None = None,
) -> tuple[ExplanationArtifact, LearningStep, FileRecord, str]:
    step = db.scalar(
        select(LearningStep)
        .where(LearningStep.id == step_id)
        .options(selectinload(LearningStep.chunk))
    )
    if step is None or step.chunk is None:
        raise ValueError("Learning step has no source-code chunk")
    chunk = step.chunk
    file = db.get(FileRecord, chunk.file_id)
    if file is None or not _verified_source(chunk, file):
        raise ValueError("Learning step source could not be verified")
    existing = db.scalar(
        select(ExplanationArtifact).where(
            ExplanationArtifact.chunk_id == chunk.id,
            ExplanationArtifact.artifact_type == "line_by_line",
            ExplanationArtifact.depth_band == depth_band,
            ExplanationArtifact.segmenter_version == SEGMENTER_VERSION,
        )
    )
    if existing is not None:
        mode = str((existing.model_metadata or {}).get("mode", "cached"))
        return existing, step, file, mode

    drafts = segment_source(chunk)
    segments, mode, model_metadata = _teach_segments(
        drafts, chunk, depth_band, settings, recorder=recorder
    )
    artifact = ExplanationArtifact(
        snapshot_id=chunk.snapshot_id,
        chunk_id=chunk.id,
        artifact_type="line_by_line",
        depth_band=depth_band,
        segments=segments,
        source_hash=chunk.content_hash,
        segmenter_version=SEGMENTER_VERSION,
        model_metadata=model_metadata,
        verification_status="verified",
    )
    db.add(artifact)
    db.flush()
    return artifact, step, file, mode


def segment_source(chunk: CodeChunk) -> list[SegmentDraft]:
    if chunk.language not in {"typescript", "tsx", "javascript", "jsx"}:
        return _line_fallback(chunk)
    language = Language(
        tree_sitter_typescript.language_tsx()
        if chunk.language in {"tsx", "jsx"}
        else tree_sitter_typescript.language_typescript()
    )
    source = chunk.content.encode("utf-8")
    tree = Parser(language).parse(source)
    candidates: list[tuple[int, int, str]] = []

    def visit(node: Node) -> None:
        if node.type in SIMPLE_NODES:
            candidates.append((node.start_byte, node.end_byte, node.type))
        elif node.type in STRUCTURAL_NODES:
            body = (
                node.child_by_field_name("body")
                or node.child_by_field_name("consequence")
                or node.child_by_field_name("value")
            )
            end_byte = body.start_byte + 1 if body is not None else node.end_byte
            candidates.append((node.start_byte, max(node.start_byte + 1, end_byte), node.type))
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    unique: dict[tuple[int, int], tuple[int, int, str]] = {}
    for item in candidates:
        unique.setdefault((item[0], item[1]), item)
    ordered = sorted(unique.values(), key=lambda item: (item[0], item[1] - item[0]))[:80]
    result: list[SegmentDraft] = []
    for index, (start_byte, end_byte, node_type) in enumerate(ordered, start=1):
        text = source[start_byte:end_byte].decode("utf-8", errors="replace").strip()
        if not text:
            continue
        before = source[:start_byte].decode("utf-8", errors="replace")
        through = source[:end_byte].decode("utf-8", errors="replace")
        start_line = chunk.start_line + before.count("\n")
        end_line = chunk.start_line + through.count("\n")
        if through.endswith("\n"):
            end_line = max(start_line, end_line - 1)
        result.append(
            SegmentDraft(
                segment_id=f"seg_{index:03d}",
                node_type=node_type,
                start_line=start_line,
                end_line=max(start_line, end_line),
                source=text,
            )
        )
    return result or _line_fallback(chunk)


def _teach_segments(
    drafts: list[SegmentDraft],
    chunk: CodeChunk,
    depth_band: str,
    settings: Settings,
    recorder: Callable[..., None] | None = None,
) -> tuple[list[dict], str, dict]:
    deterministic = [_fallback_teaching(item, chunk) for item in drafts]
    uses_openai = bool(settings.openai_api_key) and settings.generation_provider in {
        "auto",
        "openai",
    }
    if not uses_openai:
        return deterministic, "deterministic", {"mode": "deterministic"}
    try:
        payload = [
            {
                "segment_id": item.segment_id,
                "node_type": item.node_type,
                "source": item.source,
            }
            for item in drafts
        ]
        client = MeteredOpenAIClient(settings.openai_api_key, recorder=recorder)
        response = client.responses_parse(
            model=settings.generation_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are RepoWise AI teaching a Korean beginner from verified code. "
                        "Explain every supplied AST segment in concise Korean. Do not invent code, "
                        "Do not invent paths, line numbers, or segment IDs. "
                        "Use 'what' for execution or syntax and 'why' for this code's role. "
                        "Return all supplied IDs exactly once. "
                        f"Depth: {depth_band}."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            text_format=OpenAIExplanationPayload,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("OpenAI returned no structured explanation")
        by_id = {item.segment_id: item for item in parsed.segments}
        allowed = {item.segment_id for item in drafts}
        if set(by_id) != allowed:
            raise ValueError("OpenAI explanation IDs did not match verified segments")
        enriched: list[dict] = []
        fallback_by_id = {item["segment_id"]: item for item in deterministic}
        for draft in drafts:
            teaching = by_id[draft.segment_id]
            base = fallback_by_id[draft.segment_id]
            enriched.append(
                {
                    **base,
                    "what": teaching.what.strip()[:1200] or base["what"],
                    "why": teaching.why.strip()[:1200] or base["why"],
                    "syntax_concepts": list(dict.fromkeys(teaching.syntax_concepts))[:8],
                }
            )
        return (
            enriched,
            "openai",
            {
                "mode": "openai",
                "model": settings.generation_model,
            },
        )
    except Exception as exc:
        return (
            deterministic,
            "deterministic_fallback",
            {
                "mode": "deterministic_fallback",
                "error_type": type(exc).__name__,
            },
        )


def _fallback_teaching(segment: SegmentDraft, chunk: CodeChunk) -> dict:
    copy = {
        "import_statement": (
            "다른 모듈에서 이름이나 기능을 가져옵니다.",
            "이 파일이 외부 기능을 재사용하게 합니다.",
            ["module"],
        ),
        "lexical_declaration": (
            "const 또는 let으로 값에 이름을 붙입니다.",
            "뒤의 로직이 이 값을 다시 참조할 수 있게 합니다.",
            ["variable"],
        ),
        "variable_declaration": (
            "변수를 선언하고 초기값을 연결합니다.",
            "중간 결과나 상태를 다음 단계에 전달합니다.",
            ["variable"],
        ),
        "expression_statement": (
            "함수를 호출하거나 값을 갱신하는 실행 문장입니다.",
            "현재 단계의 실제 작업을 수행합니다.",
            ["call"],
        ),
        "return_statement": (
            "함수를 끝내고 결과를 호출한 쪽으로 돌려줍니다.",
            "이 함수의 출력 계약을 완성합니다.",
            ["return"],
        ),
        "throw_statement": (
            "정상 실행을 중단하고 오류를 전달합니다.",
            "잘못된 상태가 다음 단계로 퍼지는 것을 막습니다.",
            ["exception_handling"],
        ),
        "if_statement": (
            "조건에 따라 실행할 경로를 선택합니다.",
            "서로 다른 입력이나 상태를 구분해 처리합니다.",
            ["conditional"],
        ),
        "for_statement": (
            "조건이 유지되는 동안 코드를 반복합니다.",
            "여러 값에 같은 처리를 적용합니다.",
            ["loop"],
        ),
        "for_in_statement": (
            "컬렉션의 항목을 하나씩 꺼내 반복합니다.",
            "각 항목을 동일한 규칙으로 처리합니다.",
            ["loop"],
        ),
        "while_statement": (
            "조건이 참인 동안 실행을 반복합니다.",
            "완료 조건에 도달할 때까지 작업을 이어갑니다.",
            ["loop"],
        ),
        "function_declaration": (
            "재사용할 실행 절차를 함수로 정의합니다.",
            "입력, 처리, 출력을 하나의 책임으로 묶습니다.",
            ["function"],
        ),
        "function_expression": (
            "함수를 값처럼 만들어 변수나 인수에 연결합니다.",
            "필요한 위치에 동작을 전달할 수 있게 합니다.",
            ["function"],
        ),
        "arrow_function": (
            "화살표 문법으로 함수를 정의합니다.",
            "짧은 콜백이나 컴포넌트 동작을 표현합니다.",
            ["function"],
        ),
        "method_definition": (
            "객체나 클래스가 수행할 메서드를 정의합니다.",
            "데이터와 관련 동작을 같은 책임 안에 둡니다.",
            ["function", "class"],
        ),
        "class_declaration": (
            "데이터와 메서드를 묶는 클래스 설계를 선언합니다.",
            "같은 구조의 객체를 일관되게 만들 수 있게 합니다.",
            ["class"],
        ),
        "try_statement": (
            "실패할 수 있는 작업과 오류 처리를 분리합니다.",
            "실패해도 대응 흐름으로 안전하게 이동하게 합니다.",
            ["exception_handling"],
        ),
        "catch_clause": (
            "앞선 작업에서 발생한 오류를 받습니다.",
            "오류를 기록하거나 복구하는 처리를 수행합니다.",
            ["exception_handling"],
        ),
    }
    what, why, concepts = copy.get(
        segment.node_type,
        ("이 줄의 표현식이나 문장을 실행합니다.", "현재 코드 흐름의 한 단계를 구성합니다.", []),
    )
    metadata_concepts = list((chunk.metadata_json or {}).get("concept_candidates") or [])
    return {
        "segment_id": segment.segment_id,
        "start_line": segment.start_line,
        "end_line": segment.end_line,
        "source": segment.source,
        "what": what,
        "why": why,
        "syntax_concepts": list(dict.fromkeys([*concepts, *metadata_concepts]))[:8],
        "evidence_id": evidence_id_for_chunk(chunk.id),
    }


def _line_fallback(chunk: CodeChunk) -> list[SegmentDraft]:
    non_empty = (
        (offset, line) for offset, line in enumerate(chunk.content.splitlines()) if line.strip()
    )
    return [
        SegmentDraft(
            segment_id=f"seg_{index:03d}",
            node_type="line",
            start_line=chunk.start_line + offset,
            end_line=chunk.start_line + offset,
            source=line.strip(),
        )
        for index, (offset, line) in enumerate(non_empty, start=1)
    ][:80]


def _verified_source(chunk: CodeChunk, file: FileRecord) -> bool:
    source = "\n".join(file.content.splitlines()[chunk.start_line - 1 : chunk.end_line])
    digest = hashlib.sha256(chunk.content.encode("utf-8")).hexdigest()
    return source == chunk.content and chunk.content_hash == f"sha256:{digest}"
