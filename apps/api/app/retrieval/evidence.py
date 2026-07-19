from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FileRecord
from app.retrieval.hybrid import FusedHit


@dataclass(frozen=True)
class ResolvedEvidence:
    evidence_id: str
    snapshot_id: str
    file_id: str
    path: str
    language: str
    title: str
    chunk_type: str
    start_line: int
    end_line: int
    preview: str
    score: float
    retrievers: list[str]
    content: str
    symbol_name: str | None


class EvidenceRegistry:
    def resolve(self, db: Session, hits: list[FusedHit]) -> list[ResolvedEvidence]:
        if not hits:
            return []
        files = db.scalars(
            select(FileRecord).where(FileRecord.id.in_({hit.chunk.file_id for hit in hits}))
        ).all()
        file_by_id = {file.id: file for file in files}
        evidence: list[ResolvedEvidence] = []
        for hit in hits:
            chunk = hit.chunk
            file = file_by_id.get(chunk.file_id)
            if file is None or not self._valid(chunk.content, chunk.content_hash):
                continue
            if chunk.start_line < 1 or chunk.end_line > file.line_count:
                continue
            source = "\n".join(file.content.splitlines()[chunk.start_line - 1 : chunk.end_line])
            if source != chunk.content:
                continue
            symbol_name = chunk.title.rsplit("#", 1)[-1].split(" lines ", 1)[0]
            if "#" not in chunk.title:
                symbol_name = None
            evidence.append(
                ResolvedEvidence(
                    evidence_id=hit.evidence_id,
                    snapshot_id=chunk.snapshot_id,
                    file_id=file.id,
                    path=file.path,
                    language=file.language,
                    title=chunk.title,
                    chunk_type=chunk.chunk_type,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    preview=_preview(chunk.content),
                    score=hit.score,
                    retrievers=hit.retrievers,
                    content=chunk.content,
                    symbol_name=symbol_name,
                )
            )
        return evidence

    @staticmethod
    def _valid(content: str, expected_hash: str) -> bool:
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return expected_hash == f"sha256:{actual}"


def _preview(content: str, limit: int = 320) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    return compact if len(compact) <= limit else f"{compact[: limit - 3].rstrip()}..."
