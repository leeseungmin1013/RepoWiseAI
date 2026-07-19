from app.analysis.chunking import SymbolSpan, build_file_chunks, expand_identifiers


def test_builds_file_symbol_and_child_block_chunks_with_real_lines() -> None:
    lines = [f"line {index}" for index in range(1, 241)]
    content = "\n".join(lines)
    symbols = [
        SymbolSpan(
            id="sym_class",
            display_name="UserService",
            kind="class",
            signature="export class UserService",
            start_line=10,
            end_line=220,
        ),
        SymbolSpan(
            id="sym_login",
            display_name="loginUser",
            kind="method",
            signature="async loginUser(email: string)",
            start_line=30,
            end_line=60,
        ),
    ]

    chunks = build_file_chunks(
        file_id="file_1",
        path="src/userService.ts",
        language="typescript",
        content=content,
        symbols=symbols,
        max_lines=80,
        overlap_lines=10,
    )

    class_chunk = next(chunk for chunk in chunks if chunk.key == "symbol:sym_class")
    method_chunk = next(chunk for chunk in chunks if chunk.key == "symbol:sym_login")
    child_blocks = [chunk for chunk in chunks if chunk.parent_key == "symbol:sym_class"]

    assert class_chunk.start_line == 10
    assert class_chunk.end_line == 220
    assert method_chunk.parent_key == "symbol:sym_class"
    assert method_chunk.content.splitlines()[0] == "line 30"
    assert any(chunk.chunk_type == "block" for chunk in child_blocks)
    assert all(chunk.content_hash.startswith("sha256:") for chunk in chunks)


def test_expands_camel_case_and_paths_for_lexical_search() -> None:
    expanded = expand_identifiers("src/userService.ts loginUser")

    assert "user Service ts" in expanded
    assert "login User" in expanded
