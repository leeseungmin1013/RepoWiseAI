from collections.abc import Iterable
from typing import Any

from app.models import FileRecord


def build_file_tree(files: Iterable[FileRecord]) -> list[dict[str, Any]]:
    root: dict[str, Any] = {}

    for file in sorted(files, key=lambda item: item.path.lower()):
        parts = file.path.split("/")
        cursor = root
        for index, part in enumerate(parts):
            is_file = index == len(parts) - 1
            if part not in cursor:
                cursor[part] = {
                    "_type": "file" if is_file else "directory",
                    "_path": "/".join(parts[: index + 1]),
                    "_file": file if is_file else None,
                    "_children": {},
                }
            cursor = cursor[part]["_children"]

    def serialize(nodes: dict[str, Any]) -> list[dict[str, Any]]:
        output = []
        for name, node in sorted(
            nodes.items(), key=lambda item: (item[1]["_type"] == "file", item[0].lower())
        ):
            file = node["_file"]
            output.append(
                {
                    "id": file.id if file else f"dir:{node['_path']}",
                    "name": name,
                    "path": node["_path"],
                    "type": node["_type"],
                    "file_id": file.id if file else None,
                    "language": file.language if file else None,
                    "children": serialize(node["_children"]),
                }
            )
        return output

    return serialize(root)
