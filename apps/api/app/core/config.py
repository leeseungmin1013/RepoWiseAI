from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = API_ROOT.parent.parent if API_ROOT.parent.name == "apps" else API_ROOT


class Settings(BaseSettings):
    app_name: str = "RepoWise AI API"
    app_env: str = "development"
    service_name: str = "repowise-api"
    release_sha: str = "local"
    render_git_commit: str | None = None
    log_level: str = "INFO"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://repowise:repowise@localhost:5432/repowise"
    migration_database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    healthcheck_timeout_seconds: float = 2.0
    queue_name: str = "repowise-analysis"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    analysis_workspace: Path = REPOSITORY_ROOT / ".data" / "repositories"
    github_token: str | None = None
    openai_api_key: str | None = None
    embedding_provider: str = "auto"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 768
    generation_provider: str = "auto"
    generation_model: str = "gpt-5.4-mini"
    realtime_model: str = "gpt-realtime-2.1-mini"
    realtime_transcription_model: str = "gpt-realtime-whisper"
    realtime_transcription_delay: str = "low"
    realtime_voice: str = "marin"
    realtime_language: str = "ko"
    realtime_reasoning_effort: str = "minimal"
    realtime_api_url: str = "https://api.openai.com/v1/realtime/calls"
    realtime_connect_timeout_seconds: float = 10.0
    realtime_request_timeout_seconds: float = 30.0
    realtime_max_sdp_bytes: int = 64 * 1024
    realtime_max_duration_seconds: int = 300
    deep_model: str = "gpt-5.6-terra"
    deep_reasoning_effort: str = "medium"
    deep_escalation_model: str = "gpt-5.6-sol"
    deep_escalation_reasoning_effort: str = "high"
    deep_task_timeout_seconds: int = 180
    deep_queue_name: str = "repowise-deep-learning"
    research_model: str = "gpt-5.6-terra"
    research_reasoning_effort: str = "medium"
    research_allowed_domains: str = (
        "developers.openai.com,docs.python.org,developer.mozilla.org,react.dev,nextjs.org,"
        "typescriptlang.org,nodejs.org,fastapi.tiangolo.com,docs.sqlalchemy.org,"
        "postgresql.org,redis.io,python-rq.org,docs.docker.com,git-scm.com"
    )
    research_max_sources: int = 5
    chunk_max_lines: int = 160
    chunk_overlap_lines: int = 20
    retrieval_top_k: int = 8
    retrieval_candidate_k: int = 24
    max_repository_files: int = 5_000
    max_repository_bytes: int = 30 * 1024 * 1024
    max_file_bytes: int = 1024 * 1024
    max_archive_bytes: int = 50 * 1024 * 1024
    analysis_job_timeout_seconds: int = 600
    navigation_architecture_graph_enabled: bool = True
    navigation_llm_labels_enabled: bool = False
    auth_required: bool = False
    supabase_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwks_url: str | None = None
    supabase_jwks_ttl_seconds: int = 600
    default_organization_id: str | None = None
    exact_snapshot_reuse_enabled: bool = True
    incremental_analysis_enabled: bool = True
    incremental_analysis_threshold: float = 0.30
    semantic_cache_read_enabled: bool = True
    semantic_cache_write_enabled: bool = True
    semantic_cache_shadow_mode: bool = False
    retrieval_cache_similarity_threshold: float = 0.92
    generation_cache_similarity_threshold: float = 0.96
    retrieval_cache_ttl_days: int = 90
    generation_cache_ttl_days: int = 30
    quota_enforcement_mode: str = "off"
    default_monthly_allowance_micro_usd: int = 250_000
    usage_reservation_ttl_seconds: int = 900
    chat_generation_reservation_micro_usd: int = 100_000
    repository_analysis_reservation_micro_usd: int = 1_000_000
    deep_task_reservation_micro_usd: int = 500_000
    realtime_reservation_micro_usd: int = 250_000
    analysis_fingerprint_version: str = "analysis-v1"
    file_filter_version: str = "source-filter-v1"
    chunker_version: str = "chunker-v1"
    embedding_prompt_version: str = "embedding-prompt-v1"
    retrieval_index_schema_version: str = "retrieval-v1"
    navigation_artifact_bundle_version: str = "navigation-v1"

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env", REPOSITORY_ROOT / "apps" / "api" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_release_sha(self) -> str:
        return self.render_git_commit or self.release_sha

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def research_allowed_domain_list(self) -> list[str]:
        return [
            domain.strip().lower().rstrip(".")
            for domain in self.research_allowed_domains.split(",")
            if domain.strip()
        ]

    @property
    def resolved_supabase_issuer(self) -> str | None:
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer.rstrip("/")
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1"
        return None

    @property
    def resolved_supabase_jwks_url(self) -> str | None:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        issuer = self.resolved_supabase_issuer
        return f"{issuer}/.well-known/jwks.json" if issuer else None


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.analysis_workspace.is_absolute():
        settings.analysis_workspace = REPOSITORY_ROOT / settings.analysis_workspace
    return settings
