from app.analysis.typescript import TypeScriptAnalyzer

SOURCE = """import { saveToken } from './token';

export async function login(email: string) {
  const token = await requestToken(email);
  saveToken(token);
  return token;
}

export const ProfileCard = () => <section>Profile</section>;

export class SessionStore {
  clear() {
    saveToken('');
  }
}
"""


def test_extracts_symbols_imports_and_calls_with_real_line_numbers() -> None:
    result = TypeScriptAnalyzer().parse("src/auth.tsx", SOURCE, "tsx")

    symbols = {(symbol.display_name, symbol.kind): symbol for symbol in result.symbols}
    assert symbols[("login", "function")].start_line == 3
    assert symbols[("ProfileCard", "component")].start_line == 9
    assert symbols[("SessionStore", "class")].start_line == 11
    assert symbols[("clear", "method")].start_line == 12

    imports = [edge for edge in result.edges if edge.relation == "IMPORTS"]
    calls = [edge.target for edge in result.edges if edge.relation == "CALLS"]
    assert imports[0].target == "./token"
    assert "requestToken" in calls
    assert "saveToken" in calls


def test_reuses_analyzer_across_multiple_source_files() -> None:
    analyzer = TypeScriptAnalyzer()
    sources = [
        "export function first() { return Promise.resolve(1); }",
        "export const second = async () => await first();",
        "export class Third { run() { return second(); } }",
    ]

    results = [
        analyzer.parse(f"src/file-{index}.ts", source, "typescript")
        for index, source in enumerate(sources)
    ]

    assert [len(result.symbols) for result in results] == [1, 1, 2]
    assert sum(len(result.edges) for result in results) >= 3


def test_extracts_import_binding_and_re_export_metadata() -> None:
    source = """import client, { save as persist, load } from './client';
export { createOrder as submitOrder } from './orders';
"""

    result = TypeScriptAnalyzer().parse("src/index.ts", source, "typescript")

    imports = [edge for edge in result.edges if edge.relation == "IMPORTS"]
    assert len(imports) == 2
    assert imports[0].metadata["import_kind"] == "import"
    assert imports[0].metadata["bindings"] == [
        {
            "imported": "default",
            "local": "client",
            "kind": "default",
            "aliased": True,
            "type_only": False,
        },
        {
            "imported": "save",
            "local": "persist",
            "kind": "named",
            "aliased": True,
            "type_only": False,
        },
        {
            "imported": "load",
            "local": "load",
            "kind": "named",
            "aliased": False,
            "type_only": False,
        },
    ]
    assert imports[1].metadata["import_kind"] == "re_export"
    assert imports[1].metadata["bindings"] == [
        {
            "imported": "createOrder",
            "local": "submitOrder",
            "kind": "re_export",
            "aliased": True,
            "type_only": False,
        }
    ]


def test_extracts_identifier_triggers_and_literal_http_requests_only() -> None:
    source = """import axios from 'axios';
export function CheckoutForm() {
  const submit = async () => {
    await fetch('/api/orders', { method: 'POST' });
    await axios.get('/api/session');
    await fetch(dynamicTarget);
  };
  return (
    <form onSubmit={submit}>
      <button onClick={() => console.log('inline')}>Buy</button>
    </form>
  );
}
"""

    result = TypeScriptAnalyzer().parse("src/checkout.tsx", source, "tsx")

    triggers = [edge for edge in result.edges if edge.relation == "TRIGGERS"]
    assert len(triggers) == 1
    assert triggers[0].target == "submit"
    assert triggers[0].source_qualified_name == "src/checkout.tsx::CheckoutForm"
    assert triggers[0].start_line == 9
    assert triggers[0].end_line == 9
    assert triggers[0].metadata["event_name"] == "onSubmit"

    requests = [edge for edge in result.edges if edge.relation == "REQUESTS"]
    assert [(edge.target, edge.metadata["http_method"]) for edge in requests] == [
        ("/api/orders", "POST"),
        ("/api/session", "GET"),
    ]
    assert [(edge.start_line, edge.end_line) for edge in requests] == [(4, 4), (5, 5)]
    assert all(edge.metadata["literal"] is True for edge in requests)
    assert all(edge.metadata["awaited"] is True for edge in requests)


def test_extracts_local_fetch_wrapper_requests_and_template_paths() -> None:
    source = """async function request(path: string, init?: RequestInit) {
  return fetch(`/api${path}`, init);
}

export const api = {
  getSnapshot: (snapshotId: string) =>
    request(`/snapshots/${snapshotId}`),
  updateSnapshot: (snapshotId: string) =>
    request(`/snapshots/${snapshotId}`, { method: "PATCH" }),
};
"""

    result = TypeScriptAnalyzer().parse("src/lib/api.ts", source, "typescript")

    symbols = {symbol.display_name: symbol for symbol in result.symbols}
    assert {"request", "getSnapshot", "updateSnapshot"} <= symbols.keys()
    requests = [edge for edge in result.edges if edge.relation == "REQUESTS"]
    assert [
        (edge.source_qualified_name, edge.target, edge.metadata["http_method"])
        for edge in requests
    ] == [
        ("src/lib/api.ts::getSnapshot", "/snapshots/{snapshotId}", "GET"),
        ("src/lib/api.ts::updateSnapshot", "/snapshots/{snapshotId}", "PATCH"),
    ]


def test_marks_arrow_function_route_methods_as_routes() -> None:
    result = TypeScriptAnalyzer().parse(
        "src/app/api/orders/route.ts",
        "export const POST = async () => Response.json({ ok: true });",
        "typescript",
    )

    assert [
        (symbol.display_name, symbol.kind, symbol.exported_names)
        for symbol in result.symbols
    ] == [
        ("POST", "route", ("POST",))
    ]

    non_exported = TypeScriptAnalyzer().parse(
        "src/app/api/orders/route.ts",
        "async function GET() { return new Response(null); }",
        "typescript",
    )
    assert [
        (symbol.display_name, symbol.kind, symbol.exported_names)
        for symbol in non_exported.symbols
    ] == [("GET", "function", ())]


def test_suppresses_shadowed_or_untrusted_http_clients() -> None:
    source = """import trustedClient from 'axios';
import axios from './local-client';
import fetch from './local-fetch';

export function run(fetch) {
  fetch('/api/parameter-shadow');
  axios.get('/api/untrusted-import');
  trustedClient.post('/api/trusted');
}
"""

    result = TypeScriptAnalyzer().parse("src/client.ts", source, "typescript")

    requests = [edge for edge in result.edges if edge.relation == "REQUESTS"]
    assert [(edge.target, edge.metadata["client_identifier"]) for edge in requests] == [
        ("/api/trusted", "trustedClient")
    ]
    assert requests[0].metadata["client_provenance"] == "import:axios"

    file_shadow = TypeScriptAnalyzer().parse(
        "src/shadow.ts",
        "const fetch = (path) => path; fetch('/api/file-shadow');",
        "typescript",
    )
    assert not [edge for edge in file_shadow.edges if edge.relation == "REQUESTS"]


def test_only_intrinsic_user_input_events_become_triggers() -> None:
    source = """export function Screen() {
  const click = () => undefined;
  const change = () => undefined;
  const ready = () => undefined;
  return <>
    <button onClick={click}>Save</button>
    <input onChange={change} />
    <Widget onClick={click} onSuccess={ready} />
    <div onReady={ready} />
    <img onLoad={ready} onError={ready} />
  </>;
}
"""

    result = TypeScriptAnalyzer().parse("src/screen.tsx", source, "tsx")

    triggers = [edge for edge in result.edges if edge.relation == "TRIGGERS"]
    assert [
        (edge.metadata["element_name"], edge.metadata["event_name"], edge.target)
        for edge in triggers
    ] == [
        ("button", "onClick", "click"),
        ("input", "onChange", "change"),
    ]


def test_redacts_request_secrets_and_rejects_oversized_targets() -> None:
    oversized_target = f"/{'a' * 1_200}"
    source = f"""export function load() {{
  fetch('/api/orders?api_key=super-secret#access-token');
  fetch('https://user:password@example.com/v1?token=external-secret');
  fetch('{oversized_target}');
}}
"""

    result = TypeScriptAnalyzer().parse("src/requests.ts", source, "typescript")

    requests = [edge for edge in result.edges if edge.relation == "REQUESTS"]
    assert [edge.target for edge in requests] == [
        "/api/orders",
        "https://example.com/v1",
    ]
    assert [edge.metadata["request_path"] for edge in requests] == [
        "/api/orders",
        "/v1",
    ]
    assert requests[0].metadata["query_redacted"] is True
    assert requests[0].metadata["fragment_redacted"] is True
    assert requests[1].metadata["credentials_redacted"] is True
    serialized_edges = repr(requests)
    for secret in ("super-secret", "access-token", "password", "external-secret"):
        assert secret not in serialized_edges
    assert all(len(edge.target) <= 1_200 for edge in requests)


def test_extracts_state_storage_navigation_and_external_service_effects() -> None:
    source = """import { useState } from 'react';
import { useRouter, redirect } from 'next/navigation';
import OpenAI from 'openai';

export function Composer() {
  const [answer, setAnswer] = useState('');
  const router = useRouter();
  const client = new OpenAI();
  const submit = async () => {
    const draft = localStorage.getItem('draft');
    localStorage.setItem('draft', answer);
    await client.responses.create({ input: draft });
    setAnswer('done');
    router.push('/done?token=secret#private');
    redirect('/fallback?credential=secret');
  };
  return <button onClick={submit}>Send</button>;
}
"""

    result = TypeScriptAnalyzer().parse("src/composer.tsx", source, "tsx")
    effects = [
        edge
        for edge in result.edges
        if edge.relation in {"READS", "WRITES", "NAVIGATES_TO", "USES_EXTERNAL"}
    ]

    assert [(edge.relation, edge.target) for edge in effects] == [
        ("READS", "storage:localStorage:draft"),
        ("WRITES", "storage:localStorage:draft"),
        ("USES_EXTERNAL", "external:OpenAI"),
        ("WRITES", "state:answer"),
        ("NAVIGATES_TO", "/done"),
        ("NAVIGATES_TO", "/fallback"),
    ]
    external = next(edge for edge in effects if edge.relation == "USES_EXTERNAL")
    assert external.metadata["package"] == "openai"
    assert external.metadata["operation"] == "responses.create"
    assert external.metadata["awaited"] is True
    state_write = next(
        edge
        for edge in effects
        if edge.relation == "WRITES" and edge.target == "state:answer"
    )
    assert state_write.metadata["setter"] == "setAnswer"
    assert "done" not in repr(state_write)
    assert "secret" not in repr(effects)


def test_suppresses_shadowed_storage_and_untrusted_effect_clients() -> None:
    source = """import { useState as localState } from './state';
import { useRouter as localRouter } from './router';
import Client from './client';

export function run(localStorage) {
  const [value, setValue] = localState('');
  const router = localRouter();
  const client = new Client();
  localStorage.getItem('draft');
  setValue('done');
  router.push('/done');
  client.responses.create({ input: value });
}
"""

    result = TypeScriptAnalyzer().parse("src/untrusted.ts", source, "typescript")

    assert not [
        edge
        for edge in result.edges
        if edge.relation in {"READS", "WRITES", "NAVIGATES_TO", "USES_EXTERNAL"}
    ]
