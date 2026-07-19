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
