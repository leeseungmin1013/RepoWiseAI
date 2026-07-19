from app.analysis.tree import build_file_tree
from app.models import FileRecord


def file(file_id: str, path: str) -> FileRecord:
    return FileRecord(
        id=file_id,
        snapshot_id="snap_test",
        path=path,
        language="typescript",
        content="",
        content_hash="sha256:test",
        byte_size=0,
        line_count=1,
    )


def test_builds_directories_before_files() -> None:
    tree = build_file_tree(
        [
            file("file_page", "src/app/page.tsx"),
            file("file_root", "next.config.ts"),
            file("file_api", "src/app/api/route.ts"),
        ]
    )

    assert [node["name"] for node in tree] == ["src", "next.config.ts"]
    app = tree[0]["children"][0]
    assert app["path"] == "src/app"
    assert {child["name"] for child in app["children"]} == {"api", "page.tsx"}
