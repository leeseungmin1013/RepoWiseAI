from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$.-]*")


@dataclass(frozen=True)
class SymbolSpan:
    id: str
    display_name: str
    kind: str
    signature: str | None
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ChunkDraft:
    key: str
    parent_key: str | None
    symbol_id: str | None
    chunk_type: str
    ordinal: int
    title: str
    language: str
    start_line: int
    end_line: int
    content: str
    search_text: str
    content_hash: str
    metadata: dict = field(default_factory=dict)

    @property
    def embedding_text(self) -> str:
        return self.search_text[:24_000]


def expand_identifiers(text: str) -> str:
    terms = [text]
    for identifier in IDENTIFIER.findall(text):
        separated = CAMEL_BOUNDARY.sub(" ", identifier.replace("_", " ").replace(".", " "))
        if separated != identifier:
            terms.append(separated)
    return " ".join(terms)


def build_file_chunks(
    *,
    file_id: str,
    path: str,
    language: str,
    content: str,
    symbols: list[SymbolSpan],
    max_lines: int,
    overlap_lines: int,
) -> list[ChunkDraft]:
    if max_lines < 20:
        raise ValueError("max_lines must be at least 20")
    if overlap_lines < 0 or overlap_lines >= max_lines:
        raise ValueError("overlap_lines must be between 0 and max_lines - 1")

    lines = content.splitlines() or [""]
    drafts: list[ChunkDraft] = []
    ordinal = 0

    for start, end in _windows(1, len(lines), max_lines, overlap_lines):
        ordinal += 1
        title = path if len(lines) <= max_lines else f"{path} lines {start}-{end}"
        drafts.append(
            _draft(
                key=f"file:{file_id}:{start}",
                parent_key=None,
                symbol=None,
                chunk_type="file",
                ordinal=ordinal,
                title=title,
                path=path,
                language=language,
                lines=lines,
                start=start,
                end=end,
            )
        )

    ordered_symbols = sorted(
        symbols, key=lambda item: (item.start_line, -(item.end_line - item.start_line))
    )
    parent_keys: dict[str, str | None] = {}
    for symbol in ordered_symbols:
        parent = _nearest_parent(symbol, ordered_symbols)
        parent_keys[symbol.id] = f"symbol:{parent.id}" if parent else None
        ordinal += 1
        drafts.append(
            _draft(
                key=f"symbol:{symbol.id}",
                parent_key=parent_keys[symbol.id],
                symbol=symbol,
                chunk_type="symbol",
                ordinal=ordinal,
                title=f"{path}#{symbol.display_name}",
                path=path,
                language=language,
                lines=lines,
                start=symbol.start_line,
                end=symbol.end_line,
            )
        )

        if symbol.end_line - symbol.start_line + 1 <= max_lines:
            continue
        for block_start, block_end in _windows(
            symbol.start_line, symbol.end_line, max_lines, overlap_lines
        ):
            ordinal += 1
            drafts.append(
                _draft(
                    key=f"block:{symbol.id}:{block_start}",
                    parent_key=f"symbol:{symbol.id}",
                    symbol=symbol,
                    chunk_type="block",
                    ordinal=ordinal,
                    title=f"{path}#{symbol.display_name} lines {block_start}-{block_end}",
                    path=path,
                    language=language,
                    lines=lines,
                    start=block_start,
                    end=block_end,
                )
            )
    return drafts


def _nearest_parent(symbol: SymbolSpan, symbols: list[SymbolSpan]) -> SymbolSpan | None:
    parents = [
        candidate
        for candidate in symbols
        if candidate.id != symbol.id
        and candidate.start_line <= symbol.start_line
        and candidate.end_line >= symbol.end_line
    ]
    return min(parents, key=lambda item: item.end_line - item.start_line, default=None)


def _windows(start: int, end: int, size: int, overlap: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    cursor = start
    while cursor <= end:
        window_end = min(end, cursor + size - 1)
        windows.append((cursor, window_end))
        if window_end == end:
            break
        cursor = window_end - overlap + 1
    return windows


def _draft(
    *,
    key: str,
    parent_key: str | None,
    symbol: SymbolSpan | None,
    chunk_type: str,
    ordinal: int,
    title: str,
    path: str,
    language: str,
    lines: list[str],
    start: int,
    end: int,
) -> ChunkDraft:
    safe_start = max(1, min(start, len(lines)))
    safe_end = max(safe_start, min(end, len(lines)))
    source = "\n".join(lines[safe_start - 1 : safe_end])
    signature = symbol.signature if symbol else None
    prefix = [
        f"path: {path}",
        f"language: {language}",
        f"chunk: {chunk_type}",
        f"title: {title}",
    ]
    if symbol:
        prefix.extend(
            [
                f"symbol: {symbol.display_name}",
                f"kind: {symbol.kind}",
                f"signature: {signature or symbol.display_name}",
            ]
        )
    search_text = expand_identifiers("\n".join([*prefix, "source:", source]))
    return ChunkDraft(
        key=key,
        parent_key=parent_key,
        symbol_id=symbol.id if symbol else None,
        chunk_type=chunk_type,
        ordinal=ordinal,
        title=title,
        language=language,
        start_line=safe_start,
        end_line=safe_end,
        content=source,
        search_text=search_text,
        content_hash=f"sha256:{hashlib.sha256(source.encode('utf-8')).hexdigest()}",
        metadata={
            "concept_candidates": _concept_candidates(source, language),
            "symbol_kind": symbol.kind if symbol else None,
            "signature": signature,
        },
    )


def _concept_candidates(source: str, language: str) -> list[str]:
    rules = {
        "async_await": re.compile(r"\b(async|await)\b"),
        "promise": re.compile(r"\bPromise\b"),
        "class": re.compile(r"\bclass\s+\w+"),
        "generic_type": re.compile(r"\b\w+\s*<[^>]+>"),
        "exception_handling": re.compile(r"\b(try|catch|throw)\b"),
        "recursion": re.compile(r"\bfunction\s+(\w+)[\s\S]*\b\1\s*\("),
    }
    concepts = [name for name, pattern in rules.items() if pattern.search(source)]
    if language in {"tsx", "jsx"} and re.search(r"<[A-Z][A-Za-z0-9]*", source):
        concepts.append("react_component")
    return concepts
