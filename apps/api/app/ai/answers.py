from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel

from app.core.config import Settings
from app.retrieval.evidence import ResolvedEvidence

STYLE_GUIDANCE = {
    "beginner": (
        "Start with unfamiliar syntax and terms, then explain the execution flow. "
        "Use a precise everyday analogy only when it clarifies the code."
    ),
    "standard": "Explain responsibilities, data flow, and important implementation decisions.",
    "advanced": (
        "Focus on architectural boundaries, trade-offs, failure modes, complexity, "
        "and change impact."
    ),
}

DEEP_TASK_GUIDANCE = {
    "deep_explanation": (
        "Synthesize the end-to-end flow across all relevant supplied evidence. "
        "Call out component responsibilities, boundaries, and failure paths."
    ),
    "impact_analysis": (
        "Analyze change impact across callers, consumers, data contracts, tests, and "
        "failure modes that are present in the supplied evidence."
    ),
    "roadmap_proposal": (
        "Write a proposed learning sequence based on the supplied repository evidence "
        "and current learning context. Mark it as a proposal; do not claim it was applied."
    ),
}


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    evidence_ids: list[str]
    follow_up: str | None
    status: str
    mode: str
    model_name: str | None
    voice_summary: str | None = None


class OpenAIAnswerPayload(BaseModel):
    answer: str
    evidence_ids: list[str]
    follow_up: str | None
    voice_summary: str | None = None


class GroundedAnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        question: str,
        evidence: list[ResolvedEvidence],
        preferred_style: str = "beginner",
        learning_context: dict | None = None,
        model_name: str | None = None,
        reasoning_effort: str | None = None,
        allow_retrieval_fallback: bool = True,
        task_kind: str | None = None,
    ) -> GeneratedAnswer:
        if not evidence:
            if not allow_retrieval_fallback:
                raise ValueError("Deep generation requires verified repository evidence")
            return GeneratedAnswer(
                answer=(
                    "현재 스냅샷에서 이 질문을 뒷받침할 코드 근거를 찾지 못했습니다. "
                    "함수명이나 파일명을 포함해 질문을 조금 더 구체화해 주세요."
                ),
                evidence_ids=[],
                follow_up="찾으려는 기능의 이름이나 화면 이름이 있나요?",
                status="insufficient_evidence",
                mode="retrieval_only",
                model_name=None,
            )
        if self._uses_openai():
            try:
                return self._openai(
                    question,
                    evidence,
                    preferred_style,
                    learning_context=learning_context,
                    model_name=model_name,
                    reasoning_effort=reasoning_effort,
                    task_kind=task_kind,
                )
            except Exception:
                if not allow_retrieval_fallback:
                    raise
                return self._retrieval_only(evidence)
        if not allow_retrieval_fallback:
            raise RuntimeError("OpenAI generation is unavailable for deep tasks")
        return self._retrieval_only(evidence)

    def _uses_openai(self) -> bool:
        provider = self.settings.generation_provider
        return bool(self.settings.openai_api_key) and provider in {"auto", "openai"}

    def _openai(
        self,
        question: str,
        evidence: list[ResolvedEvidence],
        preferred_style: str,
        learning_context: dict | None = None,
        model_name: str | None = None,
        reasoning_effort: str | None = None,
        task_kind: str | None = None,
    ) -> GeneratedAnswer:
        from openai import OpenAI

        allowed_ids = {item.evidence_id for item in evidence}
        evidence_payload = [
            {
                "evidence_id": item.evidence_id,
                "language": item.language,
                "chunk_type": item.chunk_type,
                "symbol": item.symbol_name,
                "source": item.content[:12_000],
            }
            for item in evidence
        ]
        style = STYLE_GUIDANCE.get(preferred_style, STYLE_GUIDANCE["beginner"])
        task_guidance = DEEP_TASK_GUIDANCE.get(task_kind or "", "")
        instructions = f"""You are RepoWise AI, a patient senior software architect
teaching a learner.
Answer in Korean using only the supplied source-code evidence.
Do not include file paths, line numbers, URLs, or evidence IDs in the answer text.
Select only existing IDs in the evidence_ids field.
Write voice_summary as one or two short Korean sentences that preserve the grounded answer.
Do not put code, paths, URLs, line numbers, or evidence IDs in voice_summary.
{style}
{task_guidance}
If the evidence is insufficient, say so plainly.
"""
        prompt = f"""Current learning context:
{json.dumps(learning_context or {}, ensure_ascii=False)}

Question:
{question}

Evidence:
{json.dumps(evidence_payload, ensure_ascii=False)}
"""
        client = OpenAI(api_key=self.settings.openai_api_key)
        selected_model = model_name or self.settings.generation_model
        request = {
            "model": selected_model,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            "text_format": OpenAIAnswerPayload,
        }
        if reasoning_effort:
            request["reasoning"] = {"effort": reasoning_effort}
            request["background"] = False
            request["store"] = False
        response = client.responses.parse(**request)
        payload = response.output_parsed
        if payload is None:
            raise ValueError("OpenAI did not return a structured grounded answer")
        verified_ids = [
            evidence_id for evidence_id in payload.evidence_ids if evidence_id in allowed_ids
        ]
        if not payload.answer.strip() or not verified_ids:
            raise ValueError("OpenAI selected no valid evidence IDs")
        return GeneratedAnswer(
            answer=payload.answer.strip()[:8_000],
            evidence_ids=list(dict.fromkeys(verified_ids)),
            follow_up=payload.follow_up.strip()[:500] if payload.follow_up else None,
            status="grounded",
            mode="openai",
            model_name=selected_model,
            voice_summary=(
                payload.voice_summary.strip()[:600]
                if payload.voice_summary and payload.voice_summary.strip()
                else None
            ),
        )

    @staticmethod
    def _retrieval_only(evidence: list[ResolvedEvidence]) -> GeneratedAnswer:
        primary = evidence[0]
        subject = primary.symbol_name or primary.title
        selected: list[ResolvedEvidence] = []
        seen_sources: set[tuple[str, str]] = set()
        for item in evidence:
            source_key = (item.file_id, item.symbol_name or item.chunk_type)
            if source_key in seen_sources:
                continue
            selected.append(item)
            seen_sources.add(source_key)
            if len(selected) == 3:
                break
        if len(selected) < min(3, len(evidence)):
            selected_ids = {item.evidence_id for item in selected}
            selected.extend(item for item in evidence if item.evidence_id not in selected_ids)
            selected = selected[:3]
        return GeneratedAnswer(
            answer=(
                f"질문과 가장 가까운 코드 근거는 `{subject}`입니다. "
                "아래 인용을 열면 실제 구현 범위로 이동합니다. 먼저 가장 위의 근거를 읽고 "
                "이어지는 인용과 비교하면 이 기능의 코드 문맥을 빠르게 좁힐 수 있습니다."
            ),
            evidence_ids=[item.evidence_id for item in selected],
            follow_up="이 코드의 문법부터 볼까요, 아니면 실행 흐름부터 볼까요?",
            status="grounded",
            mode="retrieval_only",
            model_name=None,
        )
