from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from app.services.file_filter import SourceFile


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    content_hash: str
    language: str
    byte_size: int


@dataclass(frozen=True)
class ManifestDiff:
    unchanged: set[str]
    modified: set[str]
    added: set[str]
    deleted: set[str]
    renamed: dict[str, str]
    file_change_ratio: float
    byte_change_ratio: float
    language_changes: dict[str, int]

    @property
    def direct_dirty(self) -> set[str]:
        return (
            self.modified
            | self.added
            | self.deleted
            | set(self.renamed)
            | set(self.renamed.values())
        )

    def summary(self) -> dict:
        return {
            "added": len(self.added),
            "modified": len(self.modified),
            "deleted": len(self.deleted),
            "renamed": len(self.renamed),
            "unchanged": len(self.unchanged),
            "file_change_ratio": self.file_change_ratio,
            "byte_change_ratio": self.byte_change_ratio,
            "language_changes": self.language_changes,
            "direct_changed_files": len(self.direct_dirty),
        }


def build_manifest(source_files: list[SourceFile]) -> dict[str, ManifestEntry]:
    return {
        item.path: ManifestEntry(
            path=item.path,
            content_hash=item.content_hash,
            language=item.language,
            byte_size=item.byte_size,
        )
        for item in source_files
    }


def manifest_hash(manifest: dict[str, ManifestEntry]) -> str:
    payload = [asdict(manifest[path]) for path in sorted(manifest)]
    value = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def diff_manifests(
    previous: dict[str, ManifestEntry], current: dict[str, ManifestEntry]
) -> ManifestDiff:
    previous_paths = set(previous)
    current_paths = set(current)
    common = previous_paths & current_paths
    unchanged = {
        path for path in common if previous[path].content_hash == current[path].content_hash
    }
    modified = common - unchanged
    deleted = previous_paths - current_paths
    added = current_paths - previous_paths

    deleted_by_hash: dict[str, list[str]] = {}
    for path in deleted:
        deleted_by_hash.setdefault(previous[path].content_hash, []).append(path)
    renamed: dict[str, str] = {}
    for new_path in sorted(added):
        candidates = deleted_by_hash.get(current[new_path].content_hash, [])
        if not candidates:
            continue
        old_path = max(candidates, key=lambda item: SequenceMatcher(None, item, new_path).ratio())
        renamed[old_path] = new_path
        candidates.remove(old_path)
    added -= set(renamed.values())
    deleted -= set(renamed)

    changed_current_bytes = sum(
        current[path].byte_size for path in modified | added | set(renamed.values())
    )
    deleted_bytes = sum(previous[path].byte_size for path in deleted)
    total_bytes = max(1, sum(item.byte_size for item in current.values()))
    denominator = max(1, len(previous_paths | current_paths))
    changed_file_count = len(modified) + len(added) + len(deleted) + len(renamed)
    language_changes: dict[str, int] = {}
    for path in modified | added | set(renamed.values()):
        language = current[path].language
        language_changes[language] = language_changes.get(language, 0) + 1
    for path in deleted:
        language = previous[path].language
        language_changes[language] = language_changes.get(language, 0) + 1
    return ManifestDiff(
        unchanged=unchanged,
        modified=modified,
        added=added,
        deleted=deleted,
        renamed=renamed,
        file_change_ratio=changed_file_count / denominator,
        byte_change_ratio=(changed_current_bytes + deleted_bytes) / total_bytes,
        language_changes=language_changes,
    )
