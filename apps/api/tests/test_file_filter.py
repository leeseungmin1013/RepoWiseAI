from pathlib import Path

from app.core.config import Settings
from app.services.file_filter import collect_source_files


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collects_supported_source_and_applies_ignore_rules(tmp_path: Path) -> None:
    write(tmp_path / ".gitignore", "ignored.ts\n")
    write(tmp_path / "src" / "main.ts", "export const answer = 42;\n")
    write(tmp_path / "README.md", "# Example\n")
    write(tmp_path / "ignored.ts", "export const ignored = true;\n")
    write(tmp_path / "node_modules" / "package" / "index.js", "module.exports = {};\n")
    write(tmp_path / ".env", "SECRET=do-not-index\n")

    settings = Settings(
        _env_file=None,
        max_repository_files=20,
        max_repository_bytes=100_000,
        max_file_bytes=10_000,
    )
    files = collect_source_files(tmp_path, settings)

    assert [file.path for file in files] == ["README.md", "src/main.ts"]
    assert files[1].language == "typescript"
    assert files[1].content_hash.startswith("sha256:")
