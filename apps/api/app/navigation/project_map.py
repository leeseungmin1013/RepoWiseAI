from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath
from typing import Any, Literal

from app.models import FileRecord, RepositorySnapshot, SymbolEdge
from app.schemas import (
    ProjectMapCapability,
    ProjectMapEnvironmentVariable,
    ProjectMapEvidence,
    ProjectMapExternalService,
    ProjectMapReadFirst,
    ProjectMapResponse,
    ProjectMapSystemArea,
    ProjectMapTechnology,
)

Confidence = Literal["verified", "inferred", "unknown"]

LANGUAGE_GROUPS = (
    ("TypeScript", "language", frozenset({"typescript", "tsx"})),
    ("JavaScript", "language", frozenset({"javascript", "jsx"})),
)

TECHNOLOGIES: dict[str, tuple[str, str]] = {
    "next": ("Next.js", "framework"),
    "react": ("React", "user_interface"),
    "typescript": ("TypeScript", "language"),
    "tailwindcss": ("Tailwind CSS", "styling"),
    "vite": ("Vite", "build_tool"),
    "express": ("Express", "server_framework"),
    "@prisma/client": ("Prisma", "data_access"),
    "prisma": ("Prisma", "data_access"),
    "drizzle-orm": ("Drizzle ORM", "data_access"),
    "mongoose": ("Mongoose", "data_access"),
    "zod": ("Zod", "validation"),
    "openai": ("OpenAI SDK", "external_sdk"),
    "@anthropic-ai/sdk": ("Anthropic SDK", "external_sdk"),
    "@supabase/supabase-js": ("Supabase SDK", "external_sdk"),
    "firebase": ("Firebase SDK", "external_sdk"),
    "stripe": ("Stripe SDK", "external_sdk"),
    "vitest": ("Vitest", "testing"),
    "jest": ("Jest", "testing"),
    "@playwright/test": ("Playwright", "testing"),
}

SERVICE_PACKAGES: dict[str, tuple[str, str]] = {
    "openai": ("OpenAI", "OpenAI SDK를 통해 AI API를 호출하는 외부 경계입니다."),
    "@anthropic-ai/sdk": (
        "Anthropic",
        "Anthropic SDK를 통해 AI API를 호출하는 외부 경계입니다.",
    ),
    "@google/generative-ai": (
        "Google Generative AI",
        "Google Generative AI SDK를 사용하는 외부 경계입니다.",
    ),
    "@supabase/supabase-js": (
        "Supabase",
        "Supabase SDK를 통해 데이터 또는 인증 기능에 연결합니다.",
    ),
    "firebase": ("Firebase", "Firebase SDK를 통해 외부 백엔드 기능에 연결합니다."),
    "stripe": ("Stripe", "Stripe SDK를 통해 결제 기능에 연결합니다."),
    "resend": ("Resend", "Resend SDK를 통해 이메일 전송 기능에 연결합니다."),
    "twilio": ("Twilio", "Twilio SDK를 통해 메시징 기능에 연결합니다."),
    "@prisma/client": (
        "Database",
        "Prisma 클라이언트를 통해 외부 데이터 저장소에 연결합니다.",
    ),
    "pg": ("PostgreSQL", "PostgreSQL 클라이언트를 통해 외부 데이터 저장소에 연결합니다."),
}

FEATURE_HEADINGS = {
    "feature",
    "features",
    "capabilities",
    "what it does",
    "key features",
    "기능",
    "주요 기능",
    "핵심 기능",
}

ENV_PATTERNS = (
    re.compile(r"\bprocess\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"\bprocess\.env\[['\"]([A-Z][A-Z0-9_]*)['\"]\]"),
    re.compile(r"\bimport\.meta\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"\bDeno\.env\.get\(['\"]([A-Z][A-Z0-9_]*)['\"]\)"),
    re.compile(r"\bos\.(?:getenv|environ\.get)\(['\"]([A-Z][A-Z0-9_]*)['\"]"),
)
ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=")
REMOTE_URL = re.compile(r"https?://([A-Za-z0-9.-]+)")
REMOTE_CALL_HINT = re.compile(r"\b(?:fetch|axios\.(?:get|post|put|patch|delete)|new\s+URL)\b")
ENV_INLINE_VALUE = re.compile(
    r"\b([A-Z][A-Z0-9_]{2,})\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def build_project_map(
    snapshot: RepositorySnapshot,
    files: Sequence[FileRecord],
    import_edges: Sequence[SymbolEdge] = (),
) -> ProjectMapResponse:
    """Build a stable, evidence-only overview without model or network calls."""

    ordered_files = sorted(files, key=lambda item: (item.path.casefold(), item.id))
    ordered_edges = sorted(
        import_edges,
        key=lambda item: (
            item.source_file_id,
            item.source_start_line or 0,
            item.target_path or "",
            item.id,
        ),
    )
    readme = _find_readme(ordered_files)
    manifests = _load_manifests(ordered_files)
    summary, summary_confidence = _build_summary(snapshot, readme, manifests)
    capabilities = _build_capabilities(ordered_files, readme)
    system_areas = _build_system_areas(ordered_files)
    external_services = _build_external_services(ordered_files, manifests, ordered_edges)
    environment_variables = _build_environment_variables(ordered_files)

    repository = snapshot.repository
    return ProjectMapResponse(
        repository_name=f"{repository.owner}/{repository.name}",
        snapshot_id=snapshot.id,
        commit_sha=snapshot.commit_sha or "",
        summary=summary,
        summary_confidence=summary_confidence,
        tech_stack=_build_tech_stack(ordered_files, manifests),
        capabilities=capabilities,
        system_areas=system_areas,
        external_services=external_services,
        environment_variables=environment_variables,
        read_first=_build_read_first(ordered_files, readme),
        limitations=_build_limitations(
            readme=readme,
            manifests=manifests,
            import_edges=ordered_edges,
            capabilities=capabilities,
            system_areas=system_areas,
        ),
    )


def _find_readme(files: Sequence[FileRecord]) -> FileRecord | None:
    candidates = [
        file
        for file in files
        if PurePosixPath(file.path).name.casefold() in {"readme.md", "readme.mdx"}
    ]
    return min(
        candidates,
        key=lambda item: (item.path.count("/"), item.path.casefold()),
        default=None,
    )


def _load_manifests(files: Sequence[FileRecord]) -> list[tuple[FileRecord, dict[str, Any]]]:
    manifests: list[tuple[FileRecord, dict[str, Any]]] = []
    for file in files:
        if PurePosixPath(file.path).name != "package.json":
            continue
        try:
            payload = json.loads(file.content)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            manifests.append((file, payload))
    return sorted(
        manifests,
        key=lambda item: (item[0].path.count("/"), item[0].path.casefold()),
    )


def _build_summary(
    snapshot: RepositorySnapshot,
    readme: FileRecord | None,
    manifests: Sequence[tuple[FileRecord, dict[str, Any]]],
) -> tuple[str, Confidence]:
    if readme:
        paragraph = _readme_summary(readme.content)
        if paragraph:
            return paragraph, "inferred"
    for _, manifest in manifests:
        description = manifest.get("description")
        if isinstance(description, str) and description.strip():
            return _truncate(_redact_environment_values(description.strip()), 240), "inferred"
    repository = snapshot.repository
    return (
        f"{repository.owner}/{repository.name} 저장소의 정적 파일 구조를 바탕으로 "
        "만든 프로젝트 지도입니다.",
        "unknown",
    )


def _readme_summary(content: str) -> str | None:
    paragraph: list[str] = []
    in_fence = False
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or _is_readme_noise(stripped):
            if paragraph:
                break
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith(("#", "- ", "* ", "+ ", "|")):
            if paragraph:
                break
            continue
        cleaned = _clean_markdown(stripped)
        if cleaned:
            paragraph.append(cleaned)
    if not paragraph:
        return None
    return _truncate(" ".join(paragraph), 240)


def _is_readme_noise(line: str) -> bool:
    lower = line.casefold()
    return (
        not line
        or line.startswith(("<!--", "<img", "<picture", "[![", "!["))
        or "shields.io" in lower
    )


def _clean_markdown(value: str) -> str:
    value = re.sub(r"!\[[^]]*]\([^)]*\)", "", value)
    value = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"(?:`|\*\*|__|~~)", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return _redact_environment_values(value)


def _redact_environment_values(value: str) -> str:
    return ENV_INLINE_VALUE.sub(r"\1=<redacted>", value)


def _build_tech_stack(
    files: Sequence[FileRecord],
    manifests: Sequence[tuple[FileRecord, dict[str, Any]]],
) -> list[ProjectMapTechnology]:
    claims: dict[str, dict[str, Any]] = {}
    for name, category, languages in LANGUAGE_GROUPS:
        matching = next(
            (
                file
                for file in files
                if file.language in languages and not _is_config_file(file.path)
            ),
            None,
        )
        if matching:
            _add_claim(
                claims,
                name,
                category,
                "verified",
                _evidence(matching, 1, "분석된 파일 언어가 이 기술을 직접 보여 줍니다."),
            )

    for manifest_file, manifest in manifests:
        dependencies = _manifest_dependencies(manifest)
        for dependency, (name, category) in TECHNOLOGIES.items():
            if dependency not in dependencies:
                continue
            _add_claim(
                claims,
                name,
                category,
                "verified",
                _evidence(
                    manifest_file,
                    _find_line(manifest_file, f'"{dependency}"'),
                    f"package.json이 {dependency} 의존성을 선언합니다.",
                ),
            )
    return [
        ProjectMapTechnology(
            name=name,
            category=claim["description"],
            confidence=claim["confidence"],
            evidence=claim["evidence"],
        )
        for name, claim in claims.items()
    ]


def _build_capabilities(
    files: Sequence[FileRecord], readme: FileRecord | None
) -> list[ProjectMapCapability]:
    capabilities: list[ProjectMapCapability] = []
    if readme:
        for index, (line_number, feature) in enumerate(_readme_features(readme.content), start=1):
            capabilities.append(
                ProjectMapCapability(
                    id=f"readme-feature-{index}",
                    name=_truncate(feature, 80),
                    description=feature,
                    confidence="inferred",
                    evidence=[
                        _evidence(
                            readme,
                            line_number,
                            "README의 기능 목록이 이 사용자 행동을 설명합니다.",
                        )
                    ],
                )
            )
            if len(capabilities) == 5:
                return capabilities

    used_names = {item.name for item in capabilities}
    page_files = [file for file in files if _is_page_file(file.path)]
    route_files = [file for file in files if _is_api_file(file.path)]
    fallbacks = [
        *(
            (
                _page_capability_name(file.path),
                "화면 경로를 통해 사용자가 이 기능에 접근할 수 있습니다.",
                file,
                "page",
            )
            for file in page_files
        ),
        *(
            (
                _route_capability_name(file.path),
                "API 경로가 이 요청을 서버에서 처리합니다.",
                file,
                "api",
            )
            for file in route_files
        ),
    ]
    for name, description, file, kind in fallbacks:
        if name in used_names:
            continue
        capabilities.append(
            ProjectMapCapability(
                id=f"{kind}-{len(capabilities) + 1}",
                name=name,
                description=description,
                confidence="inferred",
                evidence=[
                    _evidence(file, 1, "프레임워크의 파일 경로 관례가 이 기능을 나타냅니다.")
                ],
            )
        )
        used_names.add(name)
        if len(capabilities) == 5:
            break
    return capabilities


def _readme_features(content: str) -> list[tuple[int, str]]:
    output: list[tuple[int, str]] = []
    in_features = False
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", raw_line)
        if heading:
            title = _clean_markdown(heading.group(1)).casefold().rstrip(":")
            in_features = title in FEATURE_HEADINGS
            continue
        if not in_features:
            continue
        bullet = re.match(r"^\s*[-*+]\s+(.+?)\s*$", raw_line)
        if not bullet:
            continue
        feature = _clean_markdown(bullet.group(1))
        if feature:
            output.append((line_number, _truncate(feature, 240)))
    return output[:5]


def _build_system_areas(files: Sequence[FileRecord]) -> list[ProjectMapSystemArea]:
    definitions: tuple[
        tuple[str, str, str, Callable[[str], bool]], ...
    ] = (
        (
            "interface",
            "사용자 인터페이스",
            "페이지와 컴포넌트가 사용자에게 보이는 화면과 상호작용을 구성합니다.",
            _is_interface_file,
        ),
        (
            "api",
            "API 및 서버 경계",
            "라우트와 서버 진입점이 외부 요청을 받아 애플리케이션 로직으로 전달합니다.",
            _is_api_file,
        ),
        (
            "data",
            "데이터 및 영속성",
            "스키마와 데이터 접근 코드가 저장 형식과 영속성 경계를 정의합니다.",
            _is_data_file,
        ),
        (
            "core",
            "핵심 애플리케이션 로직",
            "서비스와 기능 모듈이 화면과 서버에서 공유하는 동작을 구현합니다.",
            _is_core_file,
        ),
        (
            "tests",
            "검증 및 테스트",
            "테스트 파일이 기대 동작과 변경 후 확인 지점을 기록합니다.",
            _is_test_file,
        ),
        (
            "configuration",
            "프로젝트 설정",
            "manifest와 설정 파일이 실행, 빌드, 도구 구성을 정의합니다.",
            _is_config_file,
        ),
    )
    output: list[ProjectMapSystemArea] = []
    for area_id, name, description, predicate in definitions:
        matches = [file for file in files if predicate(file.path)][:3]
        if not matches:
            continue
        output.append(
            ProjectMapSystemArea(
                id=area_id,
                name=name,
                description=description,
                confidence="inferred",
                evidence=[
                    _evidence(file, 1, "파일 경로와 이름이 이 시스템 영역의 관례와 일치합니다.")
                    for file in matches
                ],
            )
        )
    return output


def _build_external_services(
    files: Sequence[FileRecord],
    manifests: Sequence[tuple[FileRecord, dict[str, Any]]],
    import_edges: Sequence[SymbolEdge],
) -> list[ProjectMapExternalService]:
    claims: dict[str, dict[str, Any]] = {}
    for manifest_file, manifest in manifests:
        dependencies = _manifest_dependencies(manifest)
        for package, (name, description) in SERVICE_PACKAGES.items():
            if package not in dependencies:
                continue
            _add_claim(
                claims,
                name,
                description,
                "inferred",
                _evidence(
                    manifest_file,
                    _find_line(manifest_file, f'"{package}"'),
                    f"package.json이 {package} SDK 또는 클라이언트를 선언합니다.",
                ),
            )

    files_by_id = {file.id: file for file in files}
    for edge in import_edges:
        package = _package_name(edge.target_path or "")
        service = _service_for_package(package)
        source_file = files_by_id.get(edge.source_file_id)
        if service is None or source_file is None:
            continue
        name, description = service
        _add_claim(
            claims,
            name,
            description,
            "verified",
            _evidence(
                source_file,
                edge.source_start_line or 1,
                f"코드의 import가 {package} 패키지를 직접 참조합니다.",
                edge.source_end_line,
            ),
        )

    for file in files:
        if file.language not in {"typescript", "tsx", "javascript", "jsx"}:
            continue
        for line_number, line in enumerate(file.content.splitlines(), start=1):
            if not REMOTE_CALL_HINT.search(line):
                continue
            for host in REMOTE_URL.findall(line):
                normalized = host.casefold().rstrip(".")
                if normalized in {"localhost", "127.0.0.1", "example.com"}:
                    continue
                name = normalized
                _add_claim(
                    claims,
                    name,
                    "코드에 고정된 원격 호스트로 요청하는 외부 API 경계입니다.",
                    "verified",
                    _evidence(file, line_number, "코드가 이 원격 호스트 URL을 직접 참조합니다."),
                )

    return [
        ProjectMapExternalService(
            name=name,
            description=claim["description"],
            confidence=claim["confidence"],
            evidence=claim["evidence"],
        )
        for name, claim in sorted(claims.items(), key=lambda item: item[0].casefold())
    ]


def _build_environment_variables(
    files: Sequence[FileRecord],
) -> list[ProjectMapEnvironmentVariable]:
    claims: dict[str, dict[str, Any]] = {}
    for file in files:
        for line_number, line in enumerate(file.content.splitlines(), start=1):
            names: set[str] = set()
            if file.language in {"typescript", "tsx", "javascript", "jsx"}:
                for pattern in ENV_PATTERNS:
                    names.update(pattern.findall(line))
                if "process.env" in line and "{" in line and "}" in line:
                    destructured = line.split("{", 1)[1].split("}", 1)[0]
                    names.update(re.findall(r"\b[A-Z][A-Z0-9_]*\b", destructured))
            elif file.is_documentation or file.path.casefold().endswith(".example"):
                assignment = ENV_ASSIGNMENT.match(line)
                if assignment:
                    names.add(assignment.group(1))

            for name in sorted(names):
                confidence = "verified" if not file.is_documentation else "inferred"
                reason = (
                    "코드가 이 환경 변수 이름을 직접 참조합니다."
                    if confidence == "verified"
                    else "문서가 이 환경 변수 이름을 설정 항목으로 안내합니다."
                )
                _add_claim(
                    claims,
                    name,
                    _environment_description(name),
                    confidence,
                    _evidence(file, line_number, reason),
                )

    return [
        ProjectMapEnvironmentVariable(
            name=name,
            description=claim["description"],
            confidence=claim["confidence"],
            evidence=claim["evidence"],
        )
        for name, claim in sorted(claims.items())
    ]


def _environment_description(name: str) -> str:
    if name.startswith("NEXT_PUBLIC_") or name.startswith("VITE_"):
        return "브라우저 코드에 노출될 수 있는 공개 설정 이름입니다."
    if name.endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")):
        return "서버 측 자격 증명에 사용하는 설정 이름입니다. 값은 지도에 포함하지 않습니다."
    if name.endswith("_URL"):
        return "외부 시스템 또는 데이터 저장소의 연결 주소를 지정하는 설정 이름입니다."
    if name.endswith("_MODEL"):
        return "사용할 모델 또는 실행 대상을 선택하는 설정 이름입니다."
    return "실행 환경에 따라 달라지는 설정 이름입니다."


def _build_read_first(
    files: Sequence[FileRecord], readme: FileRecord | None
) -> list[ProjectMapReadFirst]:
    recommendations: list[tuple[FileRecord, str]] = []
    if readme:
        recommendations.append((readme, "프로젝트의 목적과 실행 방법을 먼저 확인합니다."))

    root_manifest = next((file for file in files if file.path == "package.json"), None)
    if root_manifest:
        recommendations.append((root_manifest, "실행 명령과 주요 의존성을 확인합니다."))

    for candidates, reason in (
        (
            [file for file in files if _is_page_file(file.path)],
            "사용자가 처음 만나는 화면의 역할을 확인합니다.",
        ),
        (
            [file for file in files if _is_api_file(file.path)],
            "화면의 요청이 서버에서 처리되는 경계를 확인합니다.",
        ),
        (
            [file for file in files if _is_data_file(file.path)],
            "저장되는 데이터의 형태와 접근 경계를 확인합니다.",
        ),
    ):
        if candidates:
            candidate = min(
                candidates,
                key=lambda item: (item.path.count("/"), item.path.casefold()),
            )
            recommendations.append((candidate, reason))

    if not recommendations:
        code_file = next(
            (
                file
                for file in files
                if file.language in {"typescript", "tsx", "javascript", "jsx"}
            ),
            None,
        )
        if code_file:
            recommendations.append((code_file, "저장소의 첫 번째 분석 가능 코드 파일입니다."))

    output: list[ProjectMapReadFirst] = []
    seen: set[str] = set()
    for file, reason in recommendations:
        if file.id in seen:
            continue
        seen.add(file.id)
        output.append(
            ProjectMapReadFirst(
                file_id=file.id,
                path=file.path,
                start_line=1,
                end_line=min(max(file.line_count, 1), 40),
                reason=reason,
                confidence="inferred",
            )
        )
        if len(output) == 5:
            break
    return output


def _build_limitations(
    *,
    readme: FileRecord | None,
    manifests: Sequence[tuple[FileRecord, dict[str, Any]]],
    import_edges: Sequence[SymbolEdge],
    capabilities: Sequence[ProjectMapCapability],
    system_areas: Sequence[ProjectMapSystemArea],
) -> list[str]:
    limitations = [
        "정적 파일, README, package.json, 경로와 import만 사용했으며 "
        "런타임 동작은 확인하지 않았습니다."
    ]
    if readme is None:
        limitations.append(
            "README 근거가 없어 프로젝트 목적과 사용자 기능을 충분히 확인하지 못했습니다."
        )
    if not manifests:
        limitations.append(
            "유효한 package.json 근거가 없어 기술 스택과 실행 구성을 일부 놓칠 수 있습니다."
        )
    if not import_edges:
        limitations.append(
            "분석된 import 근거가 없어 외부 서비스 사용 여부는 manifest 중심으로 추정했습니다."
        )
    if not capabilities or not system_areas:
        limitations.append("확인 가능한 기능 또는 시스템 영역이 부족해 지도 일부가 비어 있습니다.")
    limitations.append(
        "환경 설정은 보안을 위해 변수 이름만 표시하며 값은 수집하거나 반환하지 않습니다."
    )
    return limitations


def _manifest_dependencies(manifest: dict[str, Any]) -> set[str]:
    dependencies: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = manifest.get(key)
        if isinstance(section, dict):
            dependencies.update(name for name in section if isinstance(name, str))
    return dependencies


def _add_claim(
    claims: dict[str, dict[str, Any]],
    name: str,
    description: str,
    confidence: Confidence,
    evidence: ProjectMapEvidence,
) -> None:
    claim = claims.setdefault(
        name,
        {"description": description, "confidence": confidence, "evidence": []},
    )
    if _confidence_rank(confidence) > _confidence_rank(claim["confidence"]):
        claim["confidence"] = confidence
    evidence_key = (evidence.file_id, evidence.start_line, evidence.end_line, evidence.reason)
    existing_keys = {
        (item.file_id, item.start_line, item.end_line, item.reason) for item in claim["evidence"]
    }
    if evidence_key not in existing_keys and len(claim["evidence"]) < 5:
        claim["evidence"].append(evidence)


def _confidence_rank(value: Confidence) -> int:
    return {"unknown": 0, "inferred": 1, "verified": 2}.get(value, 0)


def _evidence(
    file: FileRecord,
    start_line: int,
    reason: str,
    end_line: int | None = None,
) -> ProjectMapEvidence:
    maximum = max(file.line_count, 1)
    start = min(max(start_line, 1), maximum)
    end = min(max(end_line or start, start), maximum)
    return ProjectMapEvidence(
        file_id=file.id,
        path=file.path,
        start_line=start,
        end_line=end,
        reason=reason,
    )


def _find_line(file: FileRecord, needle: str) -> int:
    return next(
        (
            line_number
            for line_number, line in enumerate(file.content.splitlines(), start=1)
            if needle in line
        ),
        1,
    )


def _package_name(target: str) -> str:
    if not target or target.startswith((".", "/")):
        return ""
    parts = target.split("/")
    return "/".join(parts[:2]) if target.startswith("@") else parts[0]


def _service_for_package(package: str) -> tuple[str, str] | None:
    if package in SERVICE_PACKAGES:
        return SERVICE_PACKAGES[package]
    if package.startswith("@aws-sdk/"):
        return "AWS", "AWS SDK를 통해 외부 클라우드 서비스에 연결합니다."
    if package.startswith("@azure/"):
        return "Microsoft Azure", "Azure SDK를 통해 외부 클라우드 서비스에 연결합니다."
    return None


def _is_page_file(path: str) -> bool:
    lower = path.casefold()
    name = PurePosixPath(lower).name
    return (
        name in {"page.ts", "page.tsx", "page.js", "page.jsx"}
        or ("/pages/" in f"/{lower}" and not _is_api_file(path))
    )


def _is_interface_file(path: str) -> bool:
    lower = f"/{path.casefold()}"
    name = PurePosixPath(lower).name
    return not _is_api_file(path) and (
        _is_page_file(path)
        or name.startswith("layout.")
        or any(segment in lower for segment in ("/components/", "/views/", "/ui/"))
    )


def _is_api_file(path: str) -> bool:
    lower = f"/{path.casefold()}"
    name = PurePosixPath(lower).name
    return (
        "/api/" in lower
        or "/routes/" in lower
        or "/controllers/" in lower
        or name in {"server.ts", "server.js", "server.mjs"}
        or (name.startswith("route.") and "/app/" in lower)
    )


def _is_data_file(path: str) -> bool:
    lower = f"/{path.casefold()}"
    name = PurePosixPath(lower).name
    return (
        "/prisma/" in lower
        or "/data/" in lower
        or "/migrations/" in lower
        or "/models/" in lower
        or "/database/" in lower
        or name
        in {
            "schema.prisma",
            "db.ts",
            "db.js",
            "database.ts",
            "database.js",
            "prisma.ts",
            "prisma.js",
        }
    )


def _is_core_file(path: str) -> bool:
    lower = f"/{path.casefold()}"
    return not _is_api_file(path) and any(
        segment in lower
        for segment in ("/lib/", "/services/", "/features/", "/core/", "/hooks/", "/state/")
    )


def _is_test_file(path: str) -> bool:
    lower = f"/{path.casefold()}"
    name = PurePosixPath(lower).name
    return (
        any(segment in lower for segment in ("/tests/", "/test/", "/__tests__/", "/e2e/"))
        or ".test." in name
        or ".spec." in name
    )


def _is_config_file(path: str) -> bool:
    lower = path.casefold()
    name = PurePosixPath(lower).name
    return name == "package.json" or "config." in name or name.startswith(("tsconfig", "eslint"))


def _page_capability_name(path: str) -> str:
    parts = list(PurePosixPath(path).parts)
    meaningful = [part for part in parts[:-1] if part not in {"src", "app", "pages"}]
    label = meaningful[-1] if meaningful else "홈"
    return f"{label} 화면 사용"


def _route_capability_name(path: str) -> str:
    parts = list(PurePosixPath(path).parts)
    meaningful = [part for part in parts[:-1] if part not in {"src", "app", "api", "routes"}]
    label = meaningful[-1] if meaningful else "서버"
    return f"{label} 요청 처리"


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"
