import hashlib

from app.learning.explanations import segment_source
from app.models import CodeChunk


def test_typescript_explanation_uses_ast_statement_boundaries():
    content = """export async function loadUser(id: string) {
  const response = await fetch(`/users/${id}`);
  if (!response.ok) {
    throw new Error('failed');
  }
  return response.json();
}"""
    chunk = CodeChunk(
        id="chk_test",
        snapshot_id="snap_test",
        file_id="file_test",
        chunk_type="symbol",
        ordinal=0,
        title="src/user.ts#loadUser",
        language="typescript",
        start_line=20,
        end_line=26,
        content=content,
        search_text=content,
        embedding_model="local-hash-v1",
        content_hash=f"sha256:{hashlib.sha256(content.encode()).hexdigest()}",
        metadata_json={"concept_candidates": ["async_await", "exception_handling"]},
    )

    segments = segment_source(chunk)

    assert segments[0].node_type == "function_declaration"
    assert segments[0].start_line == 20
    assert any(item.node_type == "lexical_declaration" for item in segments)
    assert any(item.node_type == "if_statement" for item in segments)
    assert any(item.node_type == "throw_statement" for item in segments)
    assert any(item.node_type == "return_statement" for item in segments)
    assert all(20 <= item.start_line <= item.end_line <= 26 for item in segments)


def test_non_code_explanation_falls_back_to_nonempty_lines():
    chunk = CodeChunk(
        language="markdown",
        content="# Title\n\nSome text",
        start_line=4,
    )

    segments = segment_source(chunk)

    assert [item.start_line for item in segments] == [4, 6]
    assert [item.source for item in segments] == ["# Title", "Some text"]
