from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import REPOSITORY_ROOT, get_settings
from app.core.db import SessionLocal
from app.models import ChatMessage, ChatSession, Repository, RepositorySnapshot
from app.retrieval.hybrid import FusedHit, HybridRetriever


@dataclass(frozen=True)
class ExpectedEvidence:
    path: str
    symbol: str | None = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RepoWise hybrid retrieval")
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--snapshot-id")
    parser.add_argument("--fail-below", type=float, default=0.0)
    args = parser.parse_args()

    fixture_path = args.fixture
    if not fixture_path.is_absolute():
        fixture_path = REPOSITORY_ROOT / fixture_path
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    report = evaluate_fixture(fixture, snapshot_id=args.snapshot_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["recall_at_k"] < args.fail_below:
        raise SystemExit(1)


def evaluate_fixture(fixture: dict, *, snapshot_id: str | None = None) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        snapshot = _load_snapshot(db, fixture["repository"], snapshot_id)
        cases = []
        reciprocal_ranks: list[float] = []
        matched_expectations = 0
        total_expectations = 0

        for case in fixture["cases"]:
            session = ChatSession(
                snapshot_id=snapshot.id,
                goal=f"evaluation:{fixture.get('name', 'retrieval')}",
            )
            db.add(session)
            db.flush()
            message = ChatMessage(session_id=session.id, role="user", content=case["query"])
            db.add(message)
            db.flush()
            result = HybridRetriever(settings).retrieve(
                db,
                snapshot=snapshot,
                session_id=session.id,
                message_id=message.id,
                query=case["query"],
            )
            expected = [ExpectedEvidence(**item) for item in case["expected_any"]]
            matches = [_first_matching_rank(result.hits, item) for item in expected]
            matched = sum(rank is not None for rank in matches)
            matched_expectations += matched
            total_expectations += len(expected)
            first_rank = min((rank for rank in matches if rank is not None), default=None)
            reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
            cases.append(
                {
                    "id": case["id"],
                    "intent": result.analysis.intent,
                    "matched": matched,
                    "expected": len(expected),
                    "first_relevant_rank": first_rank,
                    "top_hits": [hit.chunk.title for hit in result.hits[:5]],
                    "retrieval_run_id": result.run.id,
                }
            )
        db.commit()

    recall = matched_expectations / total_expectations if total_expectations else 0.0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0
    return {
        "fixture": fixture.get("name"),
        "repository": fixture["repository"],
        "snapshot_id": snapshot.id,
        "index_version": snapshot.index_version,
        "embedding_model": snapshot.embedding_model,
        "case_count": len(cases),
        "recall_at_k": round(recall, 4),
        "mrr": round(mrr, 4),
        "cases": cases,
    }


def _load_snapshot(db, repository_name: str, snapshot_id: str | None) -> RepositorySnapshot:
    statement = (
        select(RepositorySnapshot)
        .join(Repository, Repository.id == RepositorySnapshot.repository_id)
        .where(
            RepositorySnapshot.status == "ready",
            RepositorySnapshot.chunk_count > 0,
        )
        .options(selectinload(RepositorySnapshot.repository))
    )
    if snapshot_id:
        statement = statement.where(RepositorySnapshot.id == snapshot_id)
    else:
        owner, name = repository_name.split("/", 1)
        statement = statement.where(Repository.owner == owner, Repository.name == name)
    snapshot = db.scalar(statement.order_by(RepositorySnapshot.created_at.desc()).limit(1))
    if snapshot is None:
        raise RuntimeError("No ready retrieval snapshot matched the evaluation fixture")
    return snapshot


def _first_matching_rank(
    hits: list[FusedHit], expected: ExpectedEvidence
) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        path = hit.chunk.title.split("#", 1)[0].split(" lines ", 1)[0]
        symbol = hit.chunk.title.rsplit("#", 1)[-1].split(" lines ", 1)[0]
        if path != expected.path:
            continue
        if expected.symbol and symbol.lower() != expected.symbol.lower():
            continue
        return rank
    return None


if __name__ == "__main__":
    main()
