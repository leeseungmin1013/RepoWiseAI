from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pathspec import GitIgnoreSpec

from app.core.config import Settings

DEFAULT_EXCLUDES = [
    ".git/",
    "**/.git/",
    "node_modules/",
    "**/node_modules/",
    ".next/",
    "**/.next/",
    "dist/",
    "**/dist/",
    "build/",
    "**/build/",
    "coverage/",
    "**/coverage/",
    "vendor/",
    "**/vendor/",
    "*.min.js",
    "*.min.css",
    "*.map",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
]

SECRET_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
}

SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}

LANGUAGE_BY_SUFFIX = {
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".md": "markdown",
    ".mdx": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}


class AnalysisLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceFile:
    path: str
    language: str
    content: str
    content_hash: str
    byte_size: int
    line_count: int
    is_documentation: bool


def build_ignore_spec(repository_root: Path) -> GitIgnoreSpec:
    patterns = list(DEFAULT_EXCLUDES)
    for name in (".gitignore", ".repowiseignore"):
        ignore_file = repository_root / name
        if ignore_file.is_file() and not ignore_file.is_symlink():
            patterns.extend(ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines())
    return GitIgnoreSpec.from_lines(patterns)


def collect_source_files(repository_root: Path, settings: Settings) -> list[SourceFile]:
    spec = build_ignore_spec(repository_root)
    output: list[SourceFile] = []
    total_bytes = 0

    for path in sorted(repository_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(repository_root).as_posix()
        if spec.match_file(relative) or _is_secret(path):
            continue

        language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        if language is None:
            continue
        byte_size = path.stat().st_size
        if byte_size > settings.max_file_bytes:
            continue
        if len(output) >= settings.max_repository_files:
            raise AnalysisLimitError("The repository contains too many supported files")
        if total_bytes + byte_size > settings.max_repository_bytes:
            raise AnalysisLimitError("The supported repository text is too large")

        raw = path.read_bytes()
        if b"\x00" in raw:
            continue
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue

        total_bytes += byte_size
        output.append(
            SourceFile(
                path=relative,
                language=language,
                content=content,
                content_hash=f"sha256:{hashlib.sha256(raw).hexdigest()}",
                byte_size=byte_size,
                line_count=max(1, len(content.splitlines())),
                is_documentation=language == "markdown",
            )
        )

    return output


def _is_secret(path: Path) -> bool:
    lower_name = path.name.lower()
    return (
        lower_name in SECRET_NAMES
        or any(lower_name.startswith(f"{name}.") for name in (".env",))
        or path.suffix.lower() in SECRET_SUFFIXES
    )
