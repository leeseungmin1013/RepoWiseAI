from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKClientError

from app.ai.gateway import extract_usage
from app.analysis.incremental import choose_incremental_mode
from app.analysis.manifest import ManifestDiff, ManifestEntry, diff_manifests, manifest_hash
from app.api import health
from app.api.router import api_router
from app.core import auth
from app.core.authorization import ensure_chat_access
from app.core.config import Settings
from app.services.semantic_cache import SemanticCacheService, canonical_fingerprint, normalize_query
from app.services.snapshot_resolver import analysis_fingerprint
from app.services.usage import UsageContext, UsageService, UsageSnapshot


def _entry(path: str, digest: str, size: int = 10) -> ManifestEntry:
    return ManifestEntry(path=path, content_hash=digest, language="python", byte_size=size)


def test_manifest_diff_detects_add_modify_delete_and_rename_deterministically() -> None:
    previous = {
        "same.py": _entry("same.py", "same"),
        "modify.py": _entry("modify.py", "old"),
        "delete.py": _entry("delete.py", "deleted"),
        "old/name.py": _entry("old/name.py", "renamed"),
    }
    current = {
        "same.py": _entry("same.py", "same"),
        "modify.py": _entry("modify.py", "new"),
        "add.py": _entry("add.py", "added"),
        "new/name.py": _entry("new/name.py", "renamed"),
    }

    diff = diff_manifests(previous, current)

    assert diff.unchanged == {"same.py"}
    assert diff.modified == {"modify.py"}
    assert diff.added == {"add.py"}
    assert diff.deleted == {"delete.py"}
    assert diff.renamed == {"old/name.py": "new/name.py"}
    assert manifest_hash(previous) == manifest_hash(dict(reversed(list(previous.items()))))


@pytest.mark.parametrize(
    ("dirty_count", "expected"),
    [(29, "incremental"), (31, "full")],
)
def test_incremental_threshold_boundary(dirty_count: int, expected: str) -> None:
    unchanged = {f"file-{index}.py" for index in range(100)}
    diff = ManifestDiff(
        unchanged=unchanged,
        modified=set(),
        added=set(),
        deleted=set(),
        renamed={},
        file_change_ratio=dirty_count / 100,
        byte_change_ratio=dirty_count / 100,
        language_changes={},
    )
    decision = choose_incremental_mode(
        diff=diff,
        dirty_paths=set(sorted(unchanged)[:dirty_count]),
        current_file_count=100,
        threshold=0.30,
    )
    assert decision.mode == expected


def test_analysis_fingerprint_is_stable_and_version_sensitive() -> None:
    baseline = Settings()
    same = Settings()
    changed = Settings(chunker_version="chunker-v2")

    assert analysis_fingerprint(baseline) == analysis_fingerprint(same)
    assert analysis_fingerprint(baseline) != analysis_fingerprint(changed)


def test_semantic_context_fingerprint_separates_style_and_normalizes_query() -> None:
    service = SemanticCacheService(Settings())
    snapshot = SimpleNamespace(id="snap", index_version="index-v1")
    db = SimpleNamespace(get=lambda *_args: None)
    beginner = service.context_fingerprint(
        db,
        snapshot=snapshot,
        selection={},
        learning_context={"lesson": "auth"},
        preferred_style="beginner",
        modality="text",
        task_kind=None,
        model="model-a",
        reasoning_effort=None,
    )
    advanced = service.context_fingerprint(
        db,
        snapshot=snapshot,
        selection={},
        learning_context={"lesson": "auth"},
        preferred_style="advanced",
        modality="text",
        task_kind=None,
        model="model-a",
        reasoning_effort=None,
    )

    assert beginner != advanced
    assert normalize_query("  로그인\n 함수를   설명해줘 ") == "로그인 함수를 설명해줘"
    assert canonical_fingerprint({"b": 2, "a": 1}) == canonical_fingerprint({"a": 1, "b": 2})


def _signed_token(private_key, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": "user-1",
        "iss": "https://project.supabase.co/auth/v1",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **overrides,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def test_valid_supabase_jwt_is_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda _settings: client)

    payload = auth.decode_access_token(
        _signed_token(private_key),
        Settings(
            supabase_jwt_issuer="https://project.supabase.co/auth/v1",
            supabase_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
        ),
    )

    assert payload["sub"] == "user-1"


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.invalid/auth/v1"},
        {"aud": "wrong-audience"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
    ],
)
def test_invalid_supabase_jwt_claims_are_rejected(
    monkeypatch: pytest.MonkeyPatch, claims: dict[str, object]
) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda _settings: client)

    with pytest.raises(HTTPException) as caught:
        auth.decode_access_token(
            _signed_token(private_key, **claims),
            Settings(
                supabase_jwt_issuer="https://project.supabase.co/auth/v1",
                supabase_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            ),
        )
    assert caught.value.status_code == 401


def test_unknown_jwks_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def missing(_token: str):
        raise PyJWKClientError("unknown key")

    monkeypatch.setattr(
        auth,
        "_jwks_client",
        lambda _settings: SimpleNamespace(get_signing_key_from_jwt=missing),
    )
    with pytest.raises(HTTPException) as caught:
        auth.decode_access_token(
            _signed_token(private_key),
            Settings(
                supabase_jwt_issuer="https://project.supabase.co/auth/v1",
                supabase_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            ),
        )
    assert caught.value.status_code == 401


def test_provider_usage_dto_captures_cached_reasoning_and_embedding_tokens() -> None:
    usage = SimpleNamespace(
        input_tokens=120,
        output_tokens=30,
        input_tokens_details=SimpleNamespace(cached_tokens=80),
        output_tokens_details=SimpleNamespace(reasoning_tokens=10),
    )
    response = SimpleNamespace(usage=usage)

    generation = extract_usage(response)
    embedding = extract_usage(response, embedding=True)

    assert generation.input_tokens == 120
    assert generation.cached_input_tokens == 80
    assert generation.output_tokens == 30
    assert generation.reasoning_tokens == 10
    assert embedding.embedding_tokens == 120
    assert embedding.input_tokens == 0


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class _PriceDb:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self, _query) -> _ScalarRows:
        return _ScalarRows(self.rows)


def test_cost_catalog_uses_effective_price_rows_without_hardcoded_rates() -> None:
    rows = [
        SimpleNamespace(
            usage_type="input_tokens",
            micro_usd_per_unit=2,
            version="prices-2026-08",
        ),
        SimpleNamespace(
            usage_type="output_tokens",
            micro_usd_per_unit=5,
            version="prices-2026-08",
        ),
    ]

    cost, version = UsageService().calculate_cost(
        _PriceDb(rows),
        provider="openai",
        model="test-model",
        usage={"input_tokens": 100, "output_tokens": 20},
    )

    assert cost == 300
    assert version == "prices-2026-08"


def test_bonus_consumption_uses_database_order_and_never_double_spends() -> None:
    expiring = SimpleNamespace(remaining_micro_usd=40)
    later = SimpleNamespace(remaining_micro_usd=100)
    db = _PriceDb([expiring, later])

    UsageService._consume_bonus(db, "org-1", 70)

    assert expiring.remaining_micro_usd == 0
    assert later.remaining_micro_usd == 70


def test_cost_catalog_uses_only_latest_effective_price_per_usage_type() -> None:
    rows = [
        SimpleNamespace(
            usage_type="input_tokens",
            micro_usd_per_unit=3,
            version="prices-new",
        ),
        SimpleNamespace(
            usage_type="input_tokens",
            micro_usd_per_unit=2,
            version="prices-old",
        ),
    ]

    cost, version = UsageService().calculate_cost(
        _PriceDb(rows),
        provider="openai",
        model="test-model",
        usage={"input_tokens": 100},
    )

    assert cost == 300
    assert version == "prices-new"


def test_every_non_health_api_router_has_an_auth_dependency() -> None:
    for included in api_router.routes:
        if included.original_router is health.router:
            assert not included.include_context.dependencies
            continue
        dependencies = {
            getattr(item.dependency, "__name__", "")
            for item in included.include_context.dependencies
        }
        assert dependencies & {"authorize_scope", "require_admin"}


def test_chat_access_rejects_a_different_organization_before_snapshot_lookup() -> None:
    context = auth.AuthContext(user_id="user-1", organization_id="org-1", role="owner")
    session = SimpleNamespace(organization_id="org-2", user_id="user-1", snapshot_id="snap-1")
    with pytest.raises(HTTPException) as caught:
        ensure_chat_access(SimpleNamespace(), context, session)
    assert caught.value.status_code == 404


class _MissingReservationDb:
    def __init__(self) -> None:
        self.calls = 0

    def scalar(self, _query):
        self.calls += 1
        return None


def test_settlement_rejects_a_reservation_outside_the_organization() -> None:
    db = _MissingReservationDb()
    context = UsageContext(
        organization_id="org-1",
        user_id="user-1",
        feature="chat_generation",
        request_id="request-1",
        idempotency_key="request-1",
    )
    with pytest.raises(ValueError, match="current organization"):
        UsageService().settle(
            db,
            reservation_id="reserve-other-org",
            context=context,
            provider=None,
            model=None,
            usage={},
        )
    assert db.calls == 2


class _ReserveDb:
    def __init__(self) -> None:
        self.reservation = None
        self.commits = 0

    def scalar(self, _query):
        return None

    def add(self, value) -> None:
        self.reservation = value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        raise AssertionError("reserve should not roll back")


def test_shadow_mode_records_feature_limit_excess_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = UsageService(Settings(quota_enforcement_mode="shadow"))
    db = _ReserveDb()
    period = SimpleNamespace(id="quota-1", reserved_micro_usd=0)
    now = datetime.now(UTC)
    snapshot = UsageSnapshot(now, now + timedelta(days=1), 1_000, 0, 0, 0)
    monkeypatch.setattr(service, "_period", lambda *_args, **_kwargs: period)
    monkeypatch.setattr(service, "current_snapshot", lambda *_args: snapshot)

    def exceed(*_args) -> None:
        raise HTTPException(status_code=429, detail={"code": "feature_limit_exceeded"})

    monkeypatch.setattr(service, "_check_feature_limit", exceed)
    reservation = service.reserve(
        db,
        context=UsageContext("org-1", "user-1", "chat_generation", "req-1", "req-1"),
        estimated_cost_micro_usd=100,
    )

    assert reservation is not None
    assert reservation.status == "shadow_exceeded"
    assert period.reserved_micro_usd == 0
    assert db.commits == 1


def test_repository_analysis_rq_job_id_uses_only_supported_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class QueueStub:
        def enqueue(self, *args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id=kwargs["job_id"])

    from app import queue

    monkeypatch.setattr(queue, "get_analysis_queue", QueueStub)

    job_id = queue.enqueue_repository_analysis("snap_abc123")

    assert job_id == "repository-analysis-snap_abc123"
    assert ":" not in job_id


def test_repository_attachment_uses_conflict_safe_insert() -> None:
    from sqlalchemy.dialects import postgresql

    from app.core.auth import AuthContext
    from app.services.snapshot_resolver import _attach_repository

    class DbStub:
        statement = None

        def execute(self, statement):
            self.statement = statement

    db = DbStub()
    _attach_repository(
        db,
        SimpleNamespace(id="repo_1"),
        AuthContext(
            user_id="user_1",
            organization_id="org_1",
            role="owner",
        ),
    )

    sql = str(db.statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (organization_id, repository_id) DO NOTHING" in sql
