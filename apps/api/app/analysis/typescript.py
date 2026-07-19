from __future__ import annotations

import hashlib
from dataclasses import dataclass

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

SYMBOL_TYPES = {
    "function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
}

ROUTE_NAMES = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


@dataclass(frozen=True)
class ParsedSymbol:
    qualified_name: str
    display_name: str
    kind: str
    signature: str | None
    start_line: int
    end_line: int
    content_hash: str


@dataclass(frozen=True)
class ParsedEdge:
    relation: str
    source_qualified_name: str | None
    target: str
    confidence: float
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ParseResult:
    symbols: list[ParsedSymbol]
    edges: list[ParsedEdge]


class TypeScriptAnalyzer:
    def __init__(self) -> None:
        self._typescript_language = Language(tree_sitter_typescript.language_typescript())
        self._tsx_language = Language(tree_sitter_typescript.language_tsx())
        self._typescript = Parser(self._typescript_language)
        self._tsx = Parser(self._tsx_language)

    def parse(self, file_path: str, content: str, language: str) -> ParseResult:
        source = content.encode("utf-8")
        parser = self._tsx if language in {"tsx", "jsx"} else self._typescript
        tree = parser.parse(source)
        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []
        stack: list[tuple[Node, str | None]] = [(tree.root_node, None)]
        while stack:
            node, parent_qualified_name = stack.pop()
            current_qualified_name = parent_qualified_name
            symbol = self._symbol_from_node(node, source, file_path, parent_qualified_name)
            if symbol:
                symbols.append(symbol)
                current_qualified_name = symbol.qualified_name

            if node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                if source_node:
                    edges.append(
                        ParsedEdge(
                            relation="IMPORTS",
                            source_qualified_name=None,
                            target=self._text(source_node, source).strip("'\""),
                            confidence=1.0,
                            start_line=node.start_point.row + 1,
                            end_line=node.end_point.row + 1,
                        )
                    )

            if node.type == "call_expression":
                function_node = node.child_by_field_name("function")
                if function_node:
                    target = self._text(function_node, source).strip()
                    if target and len(target) <= 300:
                        edges.append(
                            ParsedEdge(
                                relation="CALLS",
                                source_qualified_name=current_qualified_name,
                                target=target,
                                confidence=0.65,
                                start_line=node.start_point.row + 1,
                                end_line=node.end_point.row + 1,
                            )
                        )

            stack.extend((child, current_qualified_name) for child in reversed(node.children))

        return ParseResult(symbols=symbols, edges=edges)

    def _symbol_from_node(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        parent_qualified_name: str | None,
    ) -> ParsedSymbol | None:
        kind = SYMBOL_TYPES.get(node.type)
        name_node = node.child_by_field_name("name")

        if node.type == "variable_declarator":
            value_node = node.child_by_field_name("value")
            if value_node is None or value_node.type not in {
                "arrow_function",
                "function_expression",
            }:
                return None
            is_component = name_node and self._text(name_node, source)[:1].isupper()
            kind = "component" if is_component else "function"

        if not kind or name_node is None:
            return None

        display_name = self._text(name_node, source).strip()
        if not display_name:
            return None
        if display_name in ROUTE_NAMES and kind == "function":
            kind = "route"

        parent_name = parent_qualified_name.split("::", 1)[-1] if parent_qualified_name else None
        local_name = f"{parent_name}.{display_name}" if parent_name else display_name
        qualified_name = f"{file_path}::{local_name}"
        symbol_text = self._text(node, source)
        first_line = symbol_text.splitlines()[0].strip() if symbol_text else display_name
        signature = first_line[:500]
        return ParsedSymbol(
            qualified_name=qualified_name,
            display_name=display_name,
            kind=kind,
            signature=signature,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            content_hash=f"sha256:{hashlib.sha256(symbol_text.encode('utf-8')).hexdigest()}",
        )

    @staticmethod
    def _text(node: Node, source: bytes) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
