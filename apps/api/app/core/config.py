from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    app_name: str = "RepoWise AI API"
    app_env: str = "development"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://repowise:repowise@localhost:5432/repowise"
    redis_url: str = "redis://localhost:6379/0"
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

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env", REPOSITORY_ROOT / "apps" / "api" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

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


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.analysis_workspace.is_absolute():
        settings.analysis_workspace = REPOSITORY_ROOT / settings.analysis_workspace
    return settings
