from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

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
USER_INPUT_EVENTS = {
    "onBlur",
    "onChange",
    "onClick",
    "onFocus",
    "onInput",
    "onKeyDown",
    "onKeyUp",
    "onSelect",
    "onSubmit",
}
MAX_TARGET_PATH_LENGTH = 1_200
MAX_STORAGE_KEY_LENGTH = 200
EXTERNAL_SERVICE_PACKAGES = {
    "openai": "OpenAI",
    "@anthropic-ai/sdk": "Anthropic",
    "stripe": "Stripe",
    "@supabase/supabase-js": "Supabase",
    "firebase": "Firebase",
    "resend": "Resend",
    "twilio": "Twilio",
}


@dataclass(frozen=True)
class ParsedSymbol:
    qualified_name: str
    display_name: str
    kind: str
    signature: str | None
    start_line: int
    end_line: int
    content_hash: str
    exported_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedEdge:
    relation: str
    source_qualified_name: str | None
    target: str
    confidence: float
    start_line: int
    end_line: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseResult:
    symbols: list[ParsedSymbol]
    edges: list[ParsedEdge]


@dataclass(frozen=True)
class _RequestTarget:
    display_target: str
    request_path: str
    target_scope: str
    query_redacted: bool
    fragment_redacted: bool
    credentials_redacted: bool


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
        exported_names = self._top_level_export_names(tree.root_node, source)
        runtime_imports = self._runtime_import_bindings(tree.root_node, source)
        http_clients = self._trusted_http_clients(
            tree.root_node, source, runtime_imports
        )
        state_setters = self._react_state_setters(
            tree.root_node, source, runtime_imports
        )
        router_bindings, redirect_bindings = self._next_navigation_bindings(
            tree.root_node, source, runtime_imports
        )
        shadowed_storage_globals = self._non_import_runtime_bindings(
            tree.root_node,
            source,
            {"localStorage", "sessionStorage"},
        )
        storage_globals = {
            name
            for name in ("localStorage", "sessionStorage")
            if name not in shadowed_storage_globals
        }
        external_clients = self._external_service_clients(
            tree.root_node, source, runtime_imports
        )
        symbols: list[ParsedSymbol] = []
        edges: list[ParsedEdge] = []
        stack: list[tuple[Node, str | None]] = [(tree.root_node, None)]
        while stack:
            node, parent_qualified_name = stack.pop()
            current_qualified_name = parent_qualified_name
            symbol = self._symbol_from_node(
                node,
                source,
                file_path,
                parent_qualified_name,
                exported_names,
            )
            if symbol:
                symbols.append(symbol)
                current_qualified_name = symbol.qualified_name

            if node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                if source_node:
                    target = self._text(source_node, source).strip("'\"")
                    edges.append(
                        ParsedEdge(
                            relation="IMPORTS",
                            source_qualified_name=None,
                            target=target,
                            confidence=1.0,
                            start_line=node.start_point.row + 1,
                            end_line=node.end_point.row + 1,
                            metadata={
                                "module_specifier": target,
                                "bindings": self._module_bindings(node, source),
                                "import_kind": "import",
                                "confidence_rationale": (
                                    "Static ES module import with a literal module specifier."
                                ),
                                "extractor": "tree_sitter_typescript",
                            },
                        )
                    )

            if node.type == "export_statement":
                source_node = node.child_by_field_name("source")
                if source_node:
                    target = self._text(source_node, source).strip("'\"")
                    edges.append(
                        ParsedEdge(
                            relation="IMPORTS",
                            source_qualified_name=None,
                            target=target,
                            confidence=1.0,
                            start_line=node.start_point.row + 1,
                            end_line=node.end_point.row + 1,
                            metadata={
                                "module_specifier": target,
                                "bindings": self._module_bindings(node, source),
                                "import_kind": "re_export",
                                "confidence_rationale": (
                                    "Static ES module re-export with a literal module specifier."
                                ),
                                "extractor": "tree_sitter_typescript",
                            },
                        )
                    )

            if node.type == "jsx_attribute":
                trigger = self._trigger_edge_from_jsx_attribute(
                    node, source, current_qualified_name
                )
                if trigger:
                    edges.append(trigger)

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
                                metadata={
                                    "confidence_rationale": (
                                        "Syntactic call target; runtime dispatch is not resolved."
                                    ),
                                    "extractor": "tree_sitter_typescript",
                                },
                            )
                        )
                request = self._request_edge_from_call(
                    node, source, current_qualified_name, http_clients
                )
                if request:
                    edges.append(request)
                edges.extend(
                    self._effect_edges_from_call(
                        node=node,
                        source=source,
                        source_qualified_name=current_qualified_name,
                        state_setters=state_setters,
                        router_bindings=router_bindings,
                        redirect_bindings=redirect_bindings,
                        storage_globals=storage_globals,
                        external_clients=external_clients,
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
        exported_names: dict[str, set[str]],
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
        symbol_exports = (
            tuple(sorted(exported_names.get(display_name, set())))
            if parent_qualified_name is None
            else ()
        )
        if ROUTE_NAMES.intersection(symbol_exports) and kind in {"component", "function"}:
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
            exported_names=symbol_exports,
        )

    @staticmethod
    def _text(node: Node, source: bytes) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _top_level_export_names(
        self, root: Node, source: bytes
    ) -> dict[str, set[str]]:
        exports: dict[str, set[str]] = defaultdict(set)
        for statement in root.named_children:
            if statement.type != "export_statement":
                continue
            if statement.child_by_field_name("source") is not None:
                continue
            statement_text = self._text(statement, source).lstrip()
            if statement_text.startswith("export type "):
                continue
            is_default = statement_text.startswith("export default ")
            for child in statement.named_children:
                if child.type in {"function_declaration", "class_declaration"}:
                    name_node = child.child_by_field_name("name")
                    if name_node is not None:
                        local_name = self._text(name_node, source).strip()
                        exports[local_name].add("default" if is_default else local_name)
                elif child.type in {"lexical_declaration", "variable_declaration"}:
                    for declaration in child.named_children:
                        if declaration.type != "variable_declarator":
                            continue
                        name_node = declaration.child_by_field_name("name")
                        if name_node is not None and name_node.type == "identifier":
                            local_name = self._text(name_node, source).strip()
                            exports[local_name].add(local_name)
                elif child.type == "export_clause":
                    for specifier in child.named_children:
                        if specifier.type != "export_specifier":
                            continue
                        specifier_text = self._text(specifier, source).lstrip()
                        if specifier_text.startswith("type "):
                            continue
                        identifiers = [
                            item
                            for item in specifier.named_children
                            if item.type in {"identifier", "type_identifier"}
                        ]
                        if identifiers:
                            local_name = self._text(identifiers[0], source).strip()
                            exported_name = self._text(identifiers[-1], source).strip()
                            exports[local_name].add(exported_name)
        return dict(exports)

    def _runtime_import_bindings(
        self, root: Node, source: bytes
    ) -> dict[str, list[dict[str, str]]]:
        imports_by_local: dict[str, list[dict[str, str]]] = defaultdict(list)
        for statement in root.named_children:
            if statement.type != "import_statement":
                continue
            source_node = statement.child_by_field_name("source")
            if source_node is None:
                continue
            module_specifier = self._text(source_node, source).strip("'\"")
            for binding in self._module_bindings(statement, source):
                if binding.get("type_only"):
                    continue
                local = str(binding.get("local") or "")
                kind = str(binding.get("kind") or "")
                if local:
                    imports_by_local[local].append(
                        {
                            "module": module_specifier,
                            "imported": str(binding.get("imported") or ""),
                            "kind": kind,
                        }
                    )
        return dict(imports_by_local)

    def _non_import_runtime_bindings(
        self,
        root: Node,
        source: bytes,
        candidate_names: set[str],
    ) -> set[str]:
        non_import_bindings: set[str] = set()
        stack = list(reversed(root.named_children))
        while stack:
            node = stack.pop()
            if node.type == "import_statement":
                continue
            binding_node: Node | None = None
            if node.type == "variable_declarator":
                binding_node = node.child_by_field_name("name")
            elif node.type in {
                "class_declaration",
                "enum_declaration",
                "function_declaration",
                "function_expression",
            }:
                binding_node = node.child_by_field_name("name")
            elif node.type == "formal_parameters":
                binding_node = node
            elif node.type == "catch_clause":
                binding_node = node.child_by_field_name("parameter")
            if binding_node is not None:
                non_import_bindings.update(
                    self._bound_identifiers(binding_node, source) & candidate_names
                )
            stack.extend(reversed(node.named_children))
        return non_import_bindings

    def _trusted_http_clients(
        self,
        root: Node,
        source: bytes,
        imports_by_local: dict[str, list[dict[str, str]]],
    ) -> dict[str, tuple[str, str]]:
        candidate_names = {"fetch", "axios", *imports_by_local.keys()}
        non_import_bindings = self._non_import_runtime_bindings(
            root, source, candidate_names
        )

        clients: dict[str, tuple[str, str]] = {}
        if "fetch" not in non_import_bindings and "fetch" not in imports_by_local:
            clients["fetch"] = ("fetch", "global")
        for local, import_records in imports_by_local.items():
            if local in non_import_bindings:
                continue
            if import_records and all(
                record["module"] == "axios"
                and record["kind"] in {"default", "namespace"}
                for record in import_records
            ):
                clients[local] = ("axios", "import:axios")
        return clients

    def _bound_identifiers(self, node: Node, source: bytes) -> set[str]:
        names: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in {
                "identifier",
                "shorthand_property_identifier_pattern",
                "type_identifier",
            }:
                names.add(self._text(current, source).strip())
                continue
            if current.type == "type_annotation":
                continue
            stack.extend(reversed(current.named_children))
        return names

    def _react_state_setters(
        self,
        root: Node,
        source: bytes,
        imports_by_local: dict[str, list[dict[str, str]]],
    ) -> dict[str, str]:
        hook_identifiers = {
            local
            for local, records in imports_by_local.items()
            if records
            and all(
                record["module"] == "react"
                and record["imported"] == "useState"
                for record in records
            )
        }
        react_namespaces = {
            local
            for local, records in imports_by_local.items()
            if records
            and all(
                record["module"] == "react" and record["kind"] == "namespace"
                for record in records
            )
        }
        shadowed_hooks = self._non_import_runtime_bindings(
            root, source, hook_identifiers | react_namespaces
        )
        hook_identifiers -= shadowed_hooks
        react_namespaces -= shadowed_hooks
        candidates: dict[str, list[str]] = defaultdict(list)
        stack = list(reversed(root.named_children))
        while stack:
            node = stack.pop()
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                if (
                    name_node is not None
                    and name_node.type == "array_pattern"
                    and value_node is not None
                    and value_node.type == "call_expression"
                    and self._is_trusted_hook_call(
                        value_node,
                        "useState",
                        hook_identifiers,
                        react_namespaces,
                        source,
                    )
                ):
                    names = [
                        self._text(child, source).strip()
                        for child in name_node.named_children
                        if child.type == "identifier"
                    ]
                    if len(names) >= 2 and names[0] and names[1]:
                        candidates[names[1]].append(names[0])
            stack.extend(reversed(node.named_children))
        parameter_names = self._parameter_bound_names(root, source)
        return {
            setter: states[0]
            for setter, states in candidates.items()
            if len(states) == 1 and setter not in parameter_names
        }

    def _next_navigation_bindings(
        self,
        root: Node,
        source: bytes,
        imports_by_local: dict[str, list[dict[str, str]]],
    ) -> tuple[set[str], dict[str, str]]:
        use_router_identifiers = {
            local
            for local, records in imports_by_local.items()
            if records
            and all(
                record["module"] == "next/navigation"
                and record["imported"] == "useRouter"
                for record in records
            )
        }
        redirects = {
            local: records[0]["imported"]
            for local, records in imports_by_local.items()
            if len(records) == 1
            and records[0]["module"] == "next/navigation"
            and records[0]["imported"] in {"redirect", "permanentRedirect"}
        }
        shadowed_navigation_imports = self._non_import_runtime_bindings(
            root,
            source,
            use_router_identifiers | set(redirects),
        )
        use_router_identifiers -= shadowed_navigation_imports
        redirects = {
            local: imported
            for local, imported in redirects.items()
            if local not in shadowed_navigation_imports
        }
        router_candidates: dict[str, int] = defaultdict(int)
        stack = list(reversed(root.named_children))
        while stack:
            node = stack.pop()
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                if (
                    name_node is not None
                    and name_node.type == "identifier"
                    and value_node is not None
                    and value_node.type == "call_expression"
                ):
                    function_node = value_node.child_by_field_name("function")
                    if (
                        function_node is not None
                        and function_node.type == "identifier"
                        and self._text(function_node, source).strip()
                        in use_router_identifiers
                    ):
                        router_candidates[self._text(name_node, source).strip()] += 1
            stack.extend(reversed(node.named_children))
        parameter_names = self._parameter_bound_names(root, source)
        return (
            {
                name
                for name, count in router_candidates.items()
                if count == 1 and name not in parameter_names
            },
            redirects,
        )

    def _external_service_clients(
        self,
        root: Node,
        source: bytes,
        imports_by_local: dict[str, list[dict[str, str]]],
    ) -> dict[str, tuple[str, str, str]]:
        imported_services: dict[str, tuple[str, str, str]] = {}
        for local, records in imports_by_local.items():
            packages = {record["module"] for record in records}
            if len(packages) != 1:
                continue
            package = next(iter(packages))
            service = EXTERNAL_SERVICE_PACKAGES.get(package)
            if service and self._is_trusted_external_import(package, records):
                imported_services[local] = (service, package, f"import:{package}")

        shadowed_imports = self._non_import_runtime_bindings(
            root, source, set(imported_services)
        )
        imported_services = {
            local: service
            for local, service in imported_services.items()
            if local not in shadowed_imports
        }

        candidates: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        stack = list(reversed(root.named_children))
        while stack:
            node = stack.pop()
            if node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                if name_node is not None and name_node.type == "identifier" and value_node:
                    callable_node = None
                    if value_node.type == "new_expression":
                        callable_node = value_node.child_by_field_name("constructor")
                    elif value_node.type == "call_expression":
                        callable_node = value_node.child_by_field_name("function")
                    root_identifier = self._root_identifier(callable_node, source)
                    service = imported_services.get(root_identifier or "")
                    if service:
                        candidates[self._text(name_node, source).strip()].append(service)
            stack.extend(reversed(node.named_children))

        parameter_names = self._parameter_bound_names(root, source)
        clients = dict(imported_services)
        clients.update(
            {
                local: services[0]
                for local, services in candidates.items()
                if len(services) == 1 and local not in parameter_names
            }
        )
        return clients

    def _is_trusted_external_import(
        self, package: str, records: list[dict[str, str]]
    ) -> bool:
        trusted_named_imports = {
            "openai": {"OpenAI"},
            "@anthropic-ai/sdk": {"Anthropic"},
            "stripe": {"Stripe"},
            "@supabase/supabase-js": {"createClient"},
            "firebase": {"initializeApp"},
            "resend": {"Resend"},
            "twilio": {"Twilio"},
        }
        return bool(records) and all(
            record["kind"] in {"default", "namespace"}
            or record["imported"] in trusted_named_imports.get(package, set())
            for record in records
        )

    def _parameter_bound_names(self, root: Node, source: bytes) -> set[str]:
        names: set[str] = set()
        stack = list(reversed(root.named_children))
        while stack:
            node = stack.pop()
            if node.type == "formal_parameters":
                names.update(self._bound_identifiers(node, source))
                continue
            stack.extend(reversed(node.named_children))
        return names

    def _is_trusted_hook_call(
        self,
        call_node: Node,
        hook_name: str,
        hook_identifiers: set[str],
        namespace_identifiers: set[str],
        source: bytes,
    ) -> bool:
        function_node = call_node.child_by_field_name("function")
        if function_node is None:
            return False
        if function_node.type == "identifier":
            return self._text(function_node, source).strip() in hook_identifiers
        if function_node.type != "member_expression":
            return False
        object_node = function_node.child_by_field_name("object")
        property_node = function_node.child_by_field_name("property")
        return bool(
            object_node is not None
            and property_node is not None
            and object_node.type == "identifier"
            and self._text(object_node, source).strip() in namespace_identifiers
            and self._text(property_node, source).strip() == hook_name
        )

    def _root_identifier(self, node: Node | None, source: bytes) -> str | None:
        current = node
        while current is not None and current.type == "member_expression":
            current = current.child_by_field_name("object")
        if current is None or current.type != "identifier":
            return None
        value = self._text(current, source).strip()
        return value or None

    def _module_bindings(self, node: Node, source: bytes) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []

        def visit(current: Node) -> None:
            if current.type in {"import_specifier", "export_specifier"}:
                identifiers = [
                    child
                    for child in current.named_children
                    if child.type in {"identifier", "type_identifier"}
                ]
                if identifiers:
                    imported = self._text(identifiers[0], source)
                    local = self._text(identifiers[-1], source)
                    bindings.append(
                        {
                            "imported": imported,
                            "local": local,
                            "kind": (
                                "re_export"
                                if current.type == "export_specifier"
                                else "named"
                            ),
                            "aliased": imported != local,
                            "type_only": self._text(current, source).lstrip().startswith(
                                "type "
                            ),
                        }
                    )
                return

            if current.type == "namespace_import":
                identifiers = [
                    child for child in current.named_children if child.type == "identifier"
                ]
                if identifiers:
                    local = self._text(identifiers[-1], source)
                    bindings.append(
                        {
                            "imported": "*",
                            "local": local,
                            "kind": "namespace",
                            "aliased": True,
                            "type_only": False,
                        }
                    )
                return

            for child in current.named_children:
                visit(child)

        visit(node)

        import_clause = next(
            (child for child in node.named_children if child.type == "import_clause"),
            None,
        )
        if import_clause:
            default_binding = next(
                (child for child in import_clause.named_children if child.type == "identifier"),
                None,
            )
            if default_binding:
                local = self._text(default_binding, source)
                bindings.insert(
                    0,
                    {
                        "imported": "default",
                        "local": local,
                        "kind": "default",
                        "aliased": local != "default",
                        "type_only": self._text(import_clause, source).lstrip().startswith(
                            "type "
                        ),
                    },
                )
        statement_text = self._text(node, source).lstrip()
        if statement_text.startswith(("import type ", "export type ")):
            for binding in bindings:
                binding["type_only"] = True
        return bindings

    def _trigger_edge_from_jsx_attribute(
        self,
        node: Node,
        source: bytes,
        source_qualified_name: str | None,
    ) -> ParsedEdge | None:
        named_children = node.named_children
        if len(named_children) < 2:
            return None
        name_node = named_children[0]
        event_name = self._text(name_node, source).strip()
        if event_name not in USER_INPUT_EVENTS:
            return None
        element = node.parent
        if element is None or element.type not in {
            "jsx_opening_element",
            "jsx_self_closing_element",
        }:
            return None
        element_name_node = element.child_by_field_name("name")
        if element_name_node is None or element_name_node.type != "identifier":
            return None
        element_name = self._text(element_name_node, source).strip()
        if not element_name or not element_name[0].islower():
            return None

        expression_node = named_children[1]
        if expression_node.type != "jsx_expression":
            return None
        expressions = expression_node.named_children
        if len(expressions) != 1 or expressions[0].type != "identifier":
            return None
        handler_identifier = self._text(expressions[0], source).strip()
        if not handler_identifier:
            return None
        return ParsedEdge(
            relation="TRIGGERS",
            source_qualified_name=source_qualified_name,
            target=handler_identifier,
            confidence=0.98,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            metadata={
                "event_name": event_name,
                "element_name": element_name,
                "handler_identifier": handler_identifier,
                "resolution": "pending_local_symbol_resolution",
                "confidence_rationale": (
                    "JSX event prop directly references an identifier handler."
                ),
                "extractor": "tree_sitter_typescript",
            },
        )

    def _effect_edges_from_call(
        self,
        *,
        node: Node,
        source: bytes,
        source_qualified_name: str | None,
        state_setters: dict[str, str],
        router_bindings: set[str],
        redirect_bindings: dict[str, str],
        storage_globals: set[str],
        external_clients: dict[str, tuple[str, str, str]],
    ) -> list[ParsedEdge]:
        if source_qualified_name is None:
            return []
        function_node = node.child_by_field_name("function")
        arguments_node = node.child_by_field_name("arguments")
        if function_node is None or arguments_node is None:
            return []

        function_text = self._text(function_node, source).strip()
        arguments = arguments_node.named_children
        edges: list[ParsedEdge] = []
        if function_node.type == "identifier":
            state_name = state_setters.get(function_text)
            if state_name:
                edges.append(
                    self._effect_edge(
                        node=node,
                        relation="WRITES",
                        source_qualified_name=source_qualified_name,
                        target=f"state:{state_name}",
                        confidence=0.98,
                        metadata={
                            "write_kind": "react_state",
                            "state_name": state_name,
                            "setter": function_text,
                            "confidence_rationale": (
                                "Call targets the setter from an imported React useState tuple."
                            ),
                        },
                    )
                )

            redirect_kind = redirect_bindings.get(function_text)
            destination = self._literal_argument(arguments, 0, source)
            if redirect_kind and destination is not None:
                navigation_target = self._sanitize_request_target(destination)
                if navigation_target:
                    edges.append(
                        self._navigation_edge(
                            node=node,
                            source_qualified_name=source_qualified_name,
                            destination=navigation_target,
                            navigation_kind=redirect_kind,
                            client_identifier=function_text,
                        )
                    )

        if function_node.type == "member_expression":
            object_node = function_node.child_by_field_name("object")
            property_node = function_node.child_by_field_name("property")
            if object_node is not None and property_node is not None:
                object_name = self._text(object_node, source).strip()
                method_name = self._text(property_node, source).strip()
                storage_key = self._literal_argument(arguments, 0, source)
                if (
                    object_node.type == "identifier"
                    and object_name in storage_globals
                    and method_name in {"getItem", "setItem", "removeItem"}
                    and storage_key is not None
                    and 0 < len(storage_key) <= MAX_STORAGE_KEY_LENGTH
                ):
                    relation = "READS" if method_name == "getItem" else "WRITES"
                    edges.append(
                        self._effect_edge(
                            node=node,
                            relation=relation,
                            source_qualified_name=source_qualified_name,
                            target=f"storage:{object_name}:{storage_key}",
                            confidence=1.0,
                            metadata={
                                "storage_kind": object_name,
                                "storage_operation": method_name,
                                "storage_key": storage_key,
                                "confidence_rationale": (
                                    "Recognized unshadowed Web Storage call with a literal key."
                                ),
                            },
                        )
                    )

                destination = self._literal_argument(arguments, 0, source)
                if (
                    object_node.type == "identifier"
                    and object_name in router_bindings
                    and method_name in {"push", "replace"}
                    and destination is not None
                ):
                    navigation_target = self._sanitize_request_target(destination)
                    if navigation_target:
                        edges.append(
                            self._navigation_edge(
                                node=node,
                                source_qualified_name=source_qualified_name,
                                destination=navigation_target,
                                navigation_kind=f"router.{method_name}",
                                client_identifier=object_name,
                            )
                        )

        root_identifier = self._root_identifier(function_node, source)
        external_service = external_clients.get(root_identifier or "")
        if external_service and root_identifier:
            service, package, provenance = external_service
            operation = function_text
            prefix = f"{root_identifier}."
            if operation.startswith(prefix):
                operation = operation[len(prefix) :]
            if operation and len(operation) <= 200:
                edges.append(
                    self._effect_edge(
                        node=node,
                        relation="USES_EXTERNAL",
                        source_qualified_name=source_qualified_name,
                        target=f"external:{service}",
                        confidence=0.95,
                        metadata={
                            "service": service,
                            "package": package,
                            "client_identifier": root_identifier,
                            "client_provenance": provenance,
                            "operation": operation,
                            "awaited": self._is_awaited_call(node),
                            "confidence_rationale": (
                                "Call is rooted at a client constructed from a "
                                "recognized SDK import."
                            ),
                        },
                    )
                )
        return edges

    def _effect_edge(
        self,
        *,
        node: Node,
        relation: str,
        source_qualified_name: str,
        target: str,
        confidence: float,
        metadata: dict[str, Any],
    ) -> ParsedEdge:
        return ParsedEdge(
            relation=relation,
            source_qualified_name=source_qualified_name,
            target=target,
            confidence=confidence,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            metadata={**metadata, "extractor": "tree_sitter_typescript"},
        )

    def _navigation_edge(
        self,
        *,
        node: Node,
        source_qualified_name: str,
        destination: _RequestTarget,
        navigation_kind: str,
        client_identifier: str,
    ) -> ParsedEdge:
        return self._effect_edge(
            node=node,
            relation="NAVIGATES_TO",
            source_qualified_name=source_qualified_name,
            target=destination.display_target,
            confidence=1.0,
            metadata={
                "navigation_kind": navigation_kind,
                "client_identifier": client_identifier,
                "destination": destination.display_target,
                "destination_scope": destination.target_scope,
                "query_redacted": destination.query_redacted,
                "fragment_redacted": destination.fragment_redacted,
                "credentials_redacted": destination.credentials_redacted,
                "confidence_rationale": (
                    "Recognized Next.js navigation call with a literal destination."
                ),
            },
        )

    def _literal_argument(
        self, arguments: list[Node], index: int, source: bytes
    ) -> str | None:
        if index >= len(arguments):
            return None
        return self._literal_string(arguments[index], source)

    def _is_awaited_call(self, node: Node) -> bool:
        parent = node.parent
        while parent is not None and parent.type == "parenthesized_expression":
            parent = parent.parent
        return parent is not None and parent.type == "await_expression"

    def _request_edge_from_call(
        self,
        node: Node,
        source: bytes,
        source_qualified_name: str | None,
        http_clients: dict[str, tuple[str, str]],
    ) -> ParsedEdge | None:
        function_node = node.child_by_field_name("function")
        arguments_node = node.child_by_field_name("arguments")
        if function_node is None or arguments_node is None:
            return None

        client: str | None = None
        client_identifier: str | None = None
        client_provenance: str | None = None
        http_method: str | None = None
        function_text = self._text(function_node, source).strip()
        if function_node.type == "identifier" and function_text in http_clients:
            client, client_provenance = http_clients[function_text]
            client_identifier = function_text
            http_method = "GET"
        elif function_node.type == "member_expression":
            object_node = function_node.child_by_field_name("object")
            property_node = function_node.child_by_field_name("property")
            if object_node is not None and property_node is not None:
                object_name = self._text(object_node, source).strip()
                method_name = self._text(property_node, source).strip().upper()
                binding = http_clients.get(object_name)
                if (
                    binding
                    and binding[0] == "axios"
                    and method_name in ROUTE_NAMES | {"CONNECT"}
                ):
                    client, client_provenance = binding
                    client_identifier = object_name
                    http_method = method_name
        if client is None or http_method is None:
            return None

        arguments = arguments_node.named_children
        if not arguments:
            return None
        literal_target = self._literal_string(arguments[0], source)
        if literal_target is None:
            return None
        request_target = self._sanitize_request_target(literal_target)
        if request_target is None:
            return None

        method_source = "client_default" if http_method == "GET" else "client_method"
        if function_node.type == "identifier" and len(arguments) >= 2:
            method_is_static, configured_method = self._object_string_property(
                arguments[1], "method", source
            )
            if not method_is_static:
                http_method = "UNKNOWN"
                method_source = "dynamic_options"
            elif configured_method:
                http_method = configured_method.upper()
                method_source = "literal_options"

        return ParsedEdge(
            relation="REQUESTS",
            source_qualified_name=source_qualified_name,
            target=request_target.display_target,
            confidence=1.0,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            metadata={
                "client": client,
                "client_identifier": client_identifier,
                "client_provenance": client_provenance,
                "http_method": http_method,
                "http_method_source": method_source,
                "request_path": request_target.request_path,
                "display_target": request_target.display_target,
                "target_scope": request_target.target_scope,
                "query_redacted": request_target.query_redacted,
                "fragment_redacted": request_target.fragment_redacted,
                "credentials_redacted": request_target.credentials_redacted,
                "awaited": self._is_awaited_call(node),
                "literal": True,
                "resolution": "literal_only",
                "confidence_rationale": (
                    "Recognized HTTP client call with a literal request target."
                ),
                "extractor": "tree_sitter_typescript",
            },
        )

    def _sanitize_request_target(self, literal_target: str) -> _RequestTarget | None:
        if not literal_target or len(literal_target) > MAX_TARGET_PATH_LENGTH:
            return None
        try:
            parsed = urlsplit(literal_target)
            hostname = parsed.hostname
            port = parsed.port
            username = parsed.username
            password = parsed.password
        except ValueError:
            return None

        scheme = parsed.scheme.lower()
        if scheme and scheme not in {"http", "https"}:
            return None
        path = parsed.path
        if parsed.netloc:
            if hostname is None:
                return None
            authority = f"[{hostname}]" if ":" in hostname else hostname
            if port is not None:
                authority = f"{authority}:{port}"
            prefix = f"{scheme}://" if scheme else "//"
            path = path or "/"
            target_scope = "external"
            display_target = f"{prefix}{authority}{path}"
        else:
            if scheme or not path:
                return None
            target_scope = "local" if path.startswith("/") else "relative"
            display_target = path

        if len(path) > 1:
            path = path.rstrip("/")
        if len(display_target) > 1 and display_target.endswith("/"):
            display_target = display_target.rstrip("/")
        if not path or len(path) > MAX_TARGET_PATH_LENGTH:
            return None
        if not display_target or len(display_target) > MAX_TARGET_PATH_LENGTH:
            return None
        return _RequestTarget(
            display_target=display_target,
            request_path=path,
            target_scope=target_scope,
            query_redacted=bool(parsed.query),
            fragment_redacted=bool(parsed.fragment),
            credentials_redacted=bool(username or password),
        )

    def _literal_string(self, node: Node, source: bytes) -> str | None:
        if node.type != "string":
            return None
        value = self._text(node, source)
        if len(value) < 2 or value[0] not in {"'", '"'} or value[-1] != value[0]:
            return None
        return value[1:-1]

    def _object_string_property(
        self, node: Node, property_name: str, source: bytes
    ) -> tuple[bool, str | None]:
        if node.type != "object":
            return False, None
        for child in node.named_children:
            if child.type == "spread_element":
                return False, None
            if child.type.startswith("shorthand_property_identifier"):
                if self._text(child, source).strip() == property_name:
                    return False, None
                continue
            if child.type != "pair":
                continue
            key_node = child.child_by_field_name("key")
            value_node = child.child_by_field_name("value")
            if key_node is None or value_node is None:
                continue
            if key_node.type == "computed_property_name":
                return False, None
            key = self._text(key_node, source).strip("'\"")
            if key == property_name:
                value = self._literal_string(value_node, source)
                return value is not None, value
        return True, None
