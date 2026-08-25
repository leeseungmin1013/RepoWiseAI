from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.manifest import ManifestDiff
from app.models import FileRecord, SymbolEdge

PACKAGE_BOUNDARY_FILES = {
    "package.json",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "setup.py",
    "tsconfig.json",
    "next.config.js",
    "next.config.ts",
    "__init__.py",
}


@dataclass(frozen=True)
class IncrementalDecision:
    mode: str
    dirty_paths: set[str]
    reason: str
    impact_ratio: float


def dependency_closure(
    db: Session,
    *,
    base_snapshot_id: str,
    direct_dirty: set[str],
    all_current_paths: set[str],
) -> set[str]:
    files = db.scalars(select(FileRecord).where(FileRecord.snapshot_id == base_snapshot_id)).all()
    path_by_id = {item.id: item.path for item in files}
    reverse: dict[str, set[str]] = {}
    edges = db.scalars(
        select(SymbolEdge).where(
            SymbolEdge.snapshot_id == base_snapshot_id,
            SymbolEdge.relation.in_(["IMPORTS", "CALLS", "REQUESTS", "HANDLED_BY"]),
        )
    ).all()
    for edge in edges:
        source_path = path_by_id.get(edge.source_file_id)
        target_path = edge.target_path
        if source_path and target_path in all_current_paths:
            reverse.setdefault(target_path, set()).add(source_path)

    closure = set(direct_dirty)
    queue = list(direct_dirty)
    while queue:
        target = queue.pop()
        for dependent in reverse.get(target, set()):
            if dependent not in closure:
                closure.add(dependent)
                queue.append(dependent)

    for path in direct_dirty:
        if path.rsplit("/", 1)[-1] not in PACKAGE_BOUNDARY_FILES:
            continue
        boundary = path.rsplit("/", 1)[0] if "/" in path else ""
        prefix = f"{boundary}/" if boundary else ""
        closure.update(candidate for candidate in all_current_paths if candidate.startswith(prefix))
    return closure


def choose_incremental_mode(
    *,
    diff: ManifestDiff,
    dirty_paths: set[str],
    current_file_count: int,
    threshold: float,
    base_is_valid: bool = True,
) -> IncrementalDecision:
    impact_ratio = len(
        dirty_paths & (diff.unchanged | diff.modified | diff.added | set(diff.renamed.values()))
    ) / max(1, current_file_count)
    if not base_is_valid:
        return IncrementalDecision("full", set(), "base_snapshot_invalid", impact_ratio)
    if max(impact_ratio, diff.byte_change_ratio) > threshold:
        return IncrementalDecision("full", set(), "change_threshold_exceeded", impact_ratio)
    return IncrementalDecision("incremental", dirty_paths, "within_change_threshold", impact_ratio)
