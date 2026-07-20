from app.analysis.typescript import ParseResult, TypeScriptAnalyzer
from app.models import NavigationArtifact, SymbolEdge
from app.workers.repository_analysis import (
    _build_route_handler_index,
    _find_next_package_roots,
    _next_route_request_path,
    _resolve_parsed_edge,
)


def _symbol_indexes(
    parse_results: dict[str, ParseResult],
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    symbols = [
        symbol for result in parse_results.values() for symbol in result.symbols
    ]
    symbol_ids = {
        symbol.qualified_name: f"symbol-{index}"
        for index, symbol in enumerate(symbols)
    }
    display_symbol_ids = {
        (path, symbol.display_name): symbol_ids[symbol.qualified_name]
        for path, result in parse_results.items()
        for symbol in result.symbols
    }
    return symbol_ids, display_symbol_ids


def test_resolves_local_trigger_and_exact_next_route_handler() -> None:
    analyzer = TypeScriptAnalyzer()
    client_path = "src/app/checkout/page.tsx"
    route_path = "src/app/api/orders/route.ts"
    client = analyzer.parse(
        client_path,
        """export function CheckoutForm() {
  const submit = async () => {
    await fetch('/api/orders?source=checkout', { method: 'POST' });
  };
  return <form onSubmit={submit}>Checkout</form>;
}
""",
        "tsx",
    )
    route = analyzer.parse(
        route_path,
        "export async function POST() { return Response.json({ ok: true }); }",
        "typescript",
    )
    parse_results = {client_path: client, route_path: route}
    symbol_ids, display_symbol_ids = _symbol_indexes(parse_results)
    route_handlers = _build_route_handler_index(parse_results, symbol_ids, {""})

    trigger = next(edge for edge in client.edges if edge.relation == "TRIGGERS")
    resolved_trigger = _resolve_parsed_edge(
        file_path=client_path,
        parsed_edge=trigger,
        known_paths=set(parse_results),
        symbol_ids=symbol_ids,
        display_symbol_ids=display_symbol_ids,
        route_handlers=route_handlers,
        next_package_roots={""},
    )
    submit_symbol_id = symbol_ids[f"{client_path}::CheckoutForm.submit"]
    assert len(resolved_trigger) == 1
    assert resolved_trigger[0].target_symbol_id == submit_symbol_id
    assert resolved_trigger[0].metadata["resolution"] == "local_symbol"
    assert resolved_trigger[0].start_line == 5
    assert resolved_trigger[0].end_line == 5

    request = next(edge for edge in client.edges if edge.relation == "REQUESTS")
    resolved_request = _resolve_parsed_edge(
        file_path=client_path,
        parsed_edge=request,
        known_paths=set(parse_results),
        symbol_ids=symbol_ids,
        display_symbol_ids=display_symbol_ids,
        route_handlers=route_handlers,
        next_package_roots={""},
    )
    assert [edge.relation for edge in resolved_request] == ["REQUESTS", "HANDLED_BY"]
    assert resolved_request[0].target_symbol_id is None
    assert resolved_request[0].metadata["resolution"] == "exact_next_app_route"
    handled_by = resolved_request[1]
    assert handled_by.source_qualified_name == f"{client_path}::CheckoutForm.submit"
    assert handled_by.target_symbol_id == symbol_ids[f"{route_path}::POST"]
    assert handled_by.target_path == route_path
    assert handled_by.start_line == 3
    assert handled_by.end_line == 3
    assert handled_by.confidence == 1.0
    assert handled_by.metadata["http_method"] == "POST"
    assert handled_by.metadata["request_path"] == "/api/orders"
    assert handled_by.metadata["resolution"] == "exact_next_app_route"


def test_does_not_resolve_dynamic_or_ambiguous_targets() -> None:
    analyzer = TypeScriptAnalyzer()
    client_path = "src/app/page.tsx"
    route_path = "src/app/api/orders/route.ts"
    client = analyzer.parse(
        client_path,
        """export function Page({ target }) {
  fetch(target);
  fetch('/api/orders');
  fetch('/api/orders', { method: target.method });
  return <button onClick={() => fetch('/api/orders')}>Go</button>;
}
""",
        "tsx",
    )
    route = analyzer.parse(
        route_path,
        "export async function POST() { return new Response(null); }",
        "typescript",
    )
    parse_results = {client_path: client, route_path: route}
    symbol_ids, display_symbol_ids = _symbol_indexes(parse_results)
    route_handlers = _build_route_handler_index(parse_results, symbol_ids, {""})

    assert not [edge for edge in client.edges if edge.relation == "TRIGGERS"]
    requests = [edge for edge in client.edges if edge.relation == "REQUESTS"]
    assert [edge.target for edge in requests] == [
        "/api/orders",
        "/api/orders",
        "/api/orders",
    ]
    assert [edge.metadata["http_method"] for edge in requests] == [
        "GET",
        "UNKNOWN",
        "GET",
    ]
    for request in requests:
        resolved = _resolve_parsed_edge(
            file_path=client_path,
            parsed_edge=request,
            known_paths=set(parse_results),
            symbol_ids=symbol_ids,
            display_symbol_ids=display_symbol_ids,
            route_handlers=route_handlers,
            next_package_roots={""},
        )
        assert [edge.relation for edge in resolved] == ["REQUESTS"]
        assert resolved[0].metadata["resolution"] == "literal_only"

    assert _next_route_request_path("src/app/api/users/[id]/route.ts") is None
    assert _next_route_request_path("src/pages/api/orders.ts") is None


def test_preserves_import_bindings_when_resolving_local_module_path() -> None:
    analyzer = TypeScriptAnalyzer()
    source_path = "src/app/page.tsx"
    dependency_path = "src/lib/actions.ts"
    result = analyzer.parse(
        source_path,
        "import { save as persist } from '../lib/actions';",
        "tsx",
    )
    imported = next(edge for edge in result.edges if edge.relation == "IMPORTS")

    resolved = _resolve_parsed_edge(
        file_path=source_path,
        parsed_edge=imported,
        known_paths={source_path, dependency_path},
        symbol_ids={},
        display_symbol_ids={},
        route_handlers={},
        next_package_roots=set(),
    )

    assert resolved[0].target_path == dependency_path
    assert resolved[0].metadata["resolution"] == "local_file"
    assert resolved[0].metadata["bindings"] == [
        {
            "imported": "save",
            "local": "persist",
            "kind": "named",
            "aliased": True,
            "type_only": False,
        }
    ]


def test_route_index_requires_exported_handler_and_proven_next_package() -> None:
    analyzer = TypeScriptAnalyzer()
    route_path = "apps/web/src/app/api/status/route.ts"
    non_exported = analyzer.parse(
        route_path,
        "async function GET() { return new Response('ok'); }",
        "typescript",
    )
    parse_results = {route_path: non_exported}
    symbol_ids, _ = _symbol_indexes(parse_results)

    assert _build_route_handler_index(parse_results, symbol_ids, {"apps/web"}) == {}

    exported = analyzer.parse(
        route_path,
        "export async function GET() { return new Response('ok'); }",
        "typescript",
    )
    parse_results = {route_path: exported}
    symbol_ids, _ = _symbol_indexes(parse_results)
    assert _build_route_handler_index(parse_results, symbol_ids, set()) == {}
    indexed = _build_route_handler_index(parse_results, symbol_ids, {"apps/web"})
    assert list(indexed) == [("apps/web", "/api/status", "GET")]

    roots = _find_next_package_roots(
        {
            "apps/web/package.json": '{"dependencies":{"next":"16.0.0"}}',
            "apps/admin/package.json": '{"dependencies":{"react":"19.0.0"}}',
            "package.json": "not-json",
        }
    )
    assert roots == {"apps/web"}


def test_does_not_cross_next_package_roots_when_resolving_routes() -> None:
    analyzer = TypeScriptAnalyzer()
    client_path = "apps/store/src/app/page.tsx"
    other_route_path = "apps/admin/src/app/api/orders/route.ts"
    client = analyzer.parse(
        client_path,
        "export function load() { return fetch('/api/orders'); }",
        "tsx",
    )
    other_route = analyzer.parse(
        other_route_path,
        "export async function GET() { return new Response(null); }",
        "typescript",
    )
    parse_results = {client_path: client, other_route_path: other_route}
    symbol_ids, display_symbol_ids = _symbol_indexes(parse_results)
    roots = {"apps/store", "apps/admin"}
    route_handlers = _build_route_handler_index(parse_results, symbol_ids, roots)
    request = next(edge for edge in client.edges if edge.relation == "REQUESTS")

    resolved = _resolve_parsed_edge(
        file_path=client_path,
        parsed_edge=request,
        known_paths=set(parse_results),
        symbol_ids=symbol_ids,
        display_symbol_ids=display_symbol_ids,
        route_handlers=route_handlers,
        next_package_roots=roots,
    )

    assert [edge.relation for edge in resolved] == ["REQUESTS"]
    assert resolved[0].metadata["resolution"] == "literal_only"


def test_navigation_graph_models_keep_versioned_artifacts_and_edge_metadata() -> None:
    metadata_column = SymbolEdge.__table__.columns["metadata_json"]
    assert metadata_column.nullable is False
    assert metadata_column.server_default is not None

    artifact_columns = set(NavigationArtifact.__table__.columns.keys())
    assert {
        "snapshot_id",
        "artifact_type",
        "artifact_key",
        "artifact_version",
        "status",
        "payload_json",
        "evidence_ids",
        "confidence_summary",
        "generation_metadata",
        "created_at",
        "updated_at",
    } <= artifact_columns
    unique_index = next(
        index
        for index in NavigationArtifact.__table__.indexes
        if index.name == "uq_navigation_artifact_snapshot_type_key_version"
    )
    assert unique_index.unique is True
    assert [column.name for column in unique_index.columns] == [
        "snapshot_id",
        "artifact_type",
        "artifact_key",
        "artifact_version",
    ]
    snapshot_foreign_key = next(
        iter(NavigationArtifact.__table__.columns["snapshot_id"].foreign_keys)
    )
    assert snapshot_foreign_key.ondelete == "CASCADE"
