from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import Any

from app.analysis.typescript import (
    ParsedEdge,
    ParsedSymbol,
    ParseResult,
)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
READ_METHODS = {"get", "scalar", "scalars", "fetchone", "fetchall"}
WRITE_METHODS = {"add", "add_all", "delete", "merge", "commit", "flush"}
EXTERNAL_MODULES = {
    "openai": "OpenAI",
    "redis": "Redis",
    "httpx": "HTTP",
    "requests": "HTTP",
    "boto3": "AWS",
    "stripe": "Stripe",
    "github": "GitHub",
}


@dataclass(frozen=True)
class _Context:
    qualified_name: str | None
    class_name: str | None = None


class PythonAnalyzer:
    """Extract a conservative Python symbol and semantic-relation subset with stdlib AST."""

    def parse(self, file_path: str, content: str, language: str = "python") -> ParseResult:
        if language != "python":
            raise ValueError(f"Unsupported Python analyzer language: {language}")
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return ParseResult(symbols=[], edges=[])

        self._file_path = file_path
        self._content = content
        self._lines = content.splitlines()
        self._symbols: list[ParsedSymbol] = []
        self._edges: list[ParsedEdge] = []
        self._imports: dict[str, str] = {}
        self._visit_statements(tree.body, _Context(None))
        return ParseResult(symbols=self._symbols, edges=self._edges)

    def _visit_statements(self, statements: list[ast.stmt], context: _Context) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function(statement, context)
            elif isinstance(statement, ast.ClassDef):
                self._visit_class(statement, context)
            else:
                self._visit_node(statement, context)

    def _visit_class(self, node: ast.ClassDef, context: _Context) -> None:
        qualified_name = self._qualify(node.name, context)
        self._symbols.append(
            self._symbol(node, node.name, "class", qualified_name, self._signature(node))
        )
        class_context = _Context(qualified_name, node.name)
        self._visit_statements(node.body, class_context)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        context: _Context,
    ) -> None:
        qualified_name = self._qualify(node.name, context)
        route_metadata = self._route_metadata(node)
        kind = "route" if route_metadata else ("method" if context.class_name else "function")
        exported_names = (
            tuple(sorted(route_metadata["http_methods"])) if route_metadata else ()
        )
        self._symbols.append(
            self._symbol(
                node,
                node.name,
                kind,
                qualified_name,
                self._signature(node),
                exported_names=exported_names,
                metadata=route_metadata or {},
            )
        )
        self._visit_statements(node.body, _Context(qualified_name, context.class_name))

    def _visit_node(self, node: ast.AST, context: _Context) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                self._imports[local] = alias.name
                self._edges.append(
                    self._edge(
                        node,
                        "IMPORTS",
                        context,
                        alias.name,
                        1.0,
                        module_specifier=alias.name,
                        bindings=[
                            {
                                "imported": alias.name,
                                "local": local,
                                "kind": "namespace",
                                "aliased": alias.asname is not None,
                                "type_only": False,
                            }
                        ],
                        import_kind="import",
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            bindings = []
            for alias in node.names:
                local = alias.asname or alias.name
                qualified = f"{node.module}.{alias.name}" if node.module else alias.name
                self._imports[local] = qualified
                bindings.append(
                    {
                        "imported": alias.name,
                        "local": local,
                        "kind": "named",
                        "aliased": alias.asname is not None,
                        "type_only": False,
                    }
                )
            self._edges.append(
                self._edge(
                    node,
                    "IMPORTS",
                    context,
                    module,
                    1.0,
                    module_specifier=module,
                    bindings=bindings,
                    import_kind="import",
                )
            )
        elif isinstance(node, ast.Call):
            self._visit_call(node, context)
        elif isinstance(node, ast.Raise):
            target = self._call_name(node.exc) if node.exc else "reraised exception"
            self._edges.append(
                self._edge(
                    node,
                    "RAISES",
                    context,
                    target or "exception",
                    1.0,
                    failure_kind="exception",
                    extractor="python_ast",
                    confidence_rationale="Explicit Python raise statement.",
                )
            )

        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                continue
            self._visit_node(child, context)

    def _visit_call(self, node: ast.Call, context: _Context) -> None:
        target = self._call_name(node.func)
        if not target:
            return
        self._edges.append(
            self._edge(
                node,
                "CALLS",
                context,
                target,
                0.75,
                extractor="python_ast",
                confidence_rationale="Python AST resolves the syntactic call target.",
            )
        )

        method = target.rsplit(".", 1)[-1]
        root = target.split(".", 1)[0].casefold()
        is_database_client = (
            root in {"db", "database", "repo", "repository", "session"}
            or root.endswith(("db", "repo", "repository", "session"))
        )
        relation: str | None = None
        if is_database_client and (
            method in READ_METHODS or method.startswith(("find", "list", "read"))
        ):
            relation = "READS"
        elif is_database_client and (
            method in WRITE_METHODS
            or method.startswith(("create", "update", "write", "save"))
        ):
            relation = "WRITES"
        elif target.startswith(("select", "db.select")):
            relation = "READS"
        elif target.startswith(("delete", "update", "insert")):
            relation = "WRITES"
        if relation:
            operation_target = self._operation_target(node)
            self._edges.append(
                self._edge(
                    node,
                    relation,
                    context,
                    f"database:{operation_target}",
                    0.9,
                    storage_kind="database",
                    storage_operation=method,
                    model=operation_target,
                    extractor="python_ast",
                    confidence_rationale="Recognized database session or query operation.",
                )
            )

        root_name = target.split(".", 1)[0]
        imported_module = self._imports.get(root_name, root_name).split(".", 1)[0]
        service = EXTERNAL_MODULES.get(imported_module)
        if service:
            self._edges.append(
                self._edge(
                    node,
                    "USES_EXTERNAL",
                    context,
                    f"external:{service}",
                    0.9,
                    service=service,
                    operation=target,
                    extractor="python_ast",
                    confidence_rationale="Call is rooted in a recognized external SDK import.",
                )
            )

    def _route_metadata(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> dict[str, Any] | None:
        methods: set[str] = set()
        paths: list[str] = []
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            target = self._call_name(decorator.func)
            method = target.rsplit(".", 1)[-1].lower() if target else ""
            if method not in HTTP_METHODS:
                continue
            if not decorator.args:
                continue
            path = self._literal_string(decorator.args[0])
            if not path or not path.startswith("/"):
                continue
            methods.add(method.upper())
            paths.append(path)
        if not methods or not paths:
            return None
        return {
            "http_methods": sorted(methods),
            "request_paths": sorted(set(paths)),
            "framework": "fastapi",
            "extractor": "python_ast",
        }

    def _symbol(
        self,
        node: ast.AST,
        display_name: str,
        kind: str,
        qualified_name: str,
        signature: str | None,
        *,
        exported_names: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> ParsedSymbol:
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start) or start)
        snippet = "\n".join(self._lines[start - 1 : end])
        return ParsedSymbol(
            qualified_name=qualified_name,
            display_name=display_name,
            kind=kind,
            signature=signature,
            start_line=start,
            end_line=end,
            content_hash=f"sha256:{hashlib.sha256(snippet.encode('utf-8')).hexdigest()}",
            exported_names=exported_names,
            metadata=metadata or {},
        )

    def _edge(
        self,
        node: ast.AST,
        relation: str,
        context: _Context,
        target: str,
        confidence: float,
        **metadata: Any,
    ) -> ParsedEdge:
        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start) or start)
        metadata.setdefault("extractor", "python_ast")
        return ParsedEdge(
            relation=relation,
            source_qualified_name=context.qualified_name,
            target=target[:1_200],
            confidence=confidence,
            start_line=start,
            end_line=end,
            metadata=metadata,
        )

    def _qualify(self, name: str, context: _Context) -> str:
        if context.qualified_name:
            return f"{context.qualified_name}.{name}"
        return f"{self._file_path}::{name}"

    def _signature(self, node: ast.AST) -> str | None:
        try:
            value = ast.unparse(node)
        except (AttributeError, ValueError):
            return None
        return value.splitlines()[0][:1_000]

    def _operation_target(self, node: ast.Call) -> str:
        if not node.args:
            return "unknown"
        model_names = [
            child.id
            for child in ast.walk(node.args[0])
            if isinstance(child, ast.Name)
            and child.id[:1].isupper()
            and child.id not in {"True", "False", "None"}
        ]
        if model_names:
            return model_names[0][:200]
        target = self._call_name(node.args[0])
        return (target or type(node.args[0]).__name__)[:200]

    @staticmethod
    def _literal_string(node: ast.AST) -> str | None:
        return (
            node.value
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            else None
        )

    @classmethod
    def _call_name(cls, node: ast.AST | None) -> str:
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = cls._call_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        if isinstance(node, ast.Call):
            return cls._call_name(node.func)
        if isinstance(node, ast.Subscript):
            return cls._call_name(node.value)
        return ""
