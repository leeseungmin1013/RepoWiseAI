from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.ids import new_id


def utc_now() -> datetime:
    return datetime.now(UTC)


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        Index("uq_repository_provider_owner_name", "provider", "owner", "name", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("repo"))
    provider: Mapped[str] = mapped_column(String(24), default="github")
    owner: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    snapshots: Mapped[list[RepositorySnapshot]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("snap"))
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analysis_fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    base_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reuse_mode: Mapped[str] = mapped_column(String(32), default="full", index=True)
    manifest_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    change_summary: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    parser_version: Mapped[str] = mapped_column(String(32), default="tree-sitter-v1")
    index_version: Mapped[str] = mapped_column(String(32), default="structure-v1")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    symbol_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str] = mapped_column(String(120), default="local-hash-v1")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    repository: Mapped[Repository] = relationship(back_populates="snapshots")
    jobs: Mapped[list[AnalysisJob]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        foreign_keys="AnalysisJob.snapshot_id",
    )
    files: Mapped[list[FileRecord]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    symbols: Mapped[list[Symbol]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    edges: Mapped[list[SymbolEdge]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    navigation_artifacts: Mapped[list[NavigationArtifact]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[CodeChunk]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    guided_paths: Mapped[list[GuidedPath]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    assessment_sessions: Mapped[list[AssessmentSession]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    learning_paths: Mapped[list[LearningPath]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    learning_sessions: Mapped[list[LearningSession]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("job"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    base_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reuse_metrics: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    cost_reservation_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="pending")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    snapshot: Mapped[RepositorySnapshot] = relationship(
        back_populates="jobs", foreign_keys=[snapshot_id]
    )


class FileRecord(Base):
    __tablename__ = "files"
    __table_args__ = (Index("uq_file_snapshot_path", "snapshot_id", "path", unique=True),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("file"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(1000))
    language: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(80))
    byte_size: Mapped[int] = mapped_column(Integer)
    line_count: Mapped[int] = mapped_column(Integer)
    is_documentation: Mapped[bool] = mapped_column(Boolean, default=False)

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="files")
    symbols: Mapped[list[Symbol]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (
        Index("ix_symbol_snapshot_name", "snapshot_id", "display_name"),
        Index("ix_symbol_file_line", "file_id", "start_line"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("sym"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    qualified_name: Mapped[str] = mapped_column(String(1200))
    display_name: Mapped[str] = mapped_column(String(500), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(80))

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="symbols")
    file: Mapped[FileRecord] = relationship(back_populates="symbols")


class SymbolEdge(Base):
    __tablename__ = "symbol_edges"
    __table_args__ = (Index("ix_edge_snapshot_relation", "snapshot_id", "relation"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("edge"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), index=True
    )
    source_symbol_id: Mapped[str | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_symbol_id: Mapped[str | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_path: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    relation: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    analysis_method: Mapped[str] = mapped_column(String(80), default="tree_sitter")
    source_start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="edges")


class NavigationArtifact(Base):
    __tablename__ = "navigation_artifacts"
    __table_args__ = (
        Index(
            "uq_navigation_artifact_snapshot_type_key_version",
            "snapshot_id",
            "artifact_type",
            "artifact_key",
            "artifact_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("navart"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(60), index=True)
    artifact_key: Mapped[str] = mapped_column(String(500))
    artifact_version: Mapped[str] = mapped_column(String(60), index=True)
    dependency_fingerprint: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    evidence_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    confidence_summary: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    generation_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="navigation_artifacts")


class CodeChunk(Base):
    __tablename__ = "code_chunks"
    __table_args__ = (
        Index("ix_chunk_snapshot_file_line", "snapshot_id", "file_id", "start_line"),
        Index("ix_chunk_snapshot_type", "snapshot_id", "chunk_type"),
        Index("ix_chunk_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("chk"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    symbol_id: Mapped[str | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("code_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chunk_type: Mapped[str] = mapped_column(String(40), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(1400))
    language: Mapped[str] = mapped_column(String(40))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(search_text, ''))", persisted=True),
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="chunks")


class GuidedPath(Base):
    __tablename__ = "guided_paths"
    __table_args__ = (
        Index("uq_guided_path_snapshot_version", "snapshot_id", "path_version", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("gpath"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    goal: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(40), default="beginner")
    path_version: Mapped[str] = mapped_column(String(60), default="guided-tour-v1")
    generation_method: Mapped[str] = mapped_column(String(80), default="deterministic-structure-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="guided_paths")
    steps: Mapped[list[GuidedStep]] = relationship(
        back_populates="path",
        cascade="all, delete-orphan",
        order_by="GuidedStep.ordinal",
    )
    sessions: Mapped[list[GuidedTourSession]] = relationship(
        back_populates="path", cascade="all, delete-orphan"
    )


class GuidedStep(Base):
    __tablename__ = "guided_steps"
    __table_args__ = (Index("uq_guided_step_path_ordinal", "path_id", "ordinal", unique=True),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("gstep"))
    path_id: Mapped[str] = mapped_column(
        ForeignKey("guided_paths.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("code_chunks.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(500))
    learning_objective: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    concept_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    checkpoint: Mapped[dict] = mapped_column(JSONB, default=dict)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=3)

    path: Mapped[GuidedPath] = relationship(back_populates="steps")
    chunk: Mapped[CodeChunk] = relationship()
    events: Mapped[list[GuidedStepEvent]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )


class GuidedTourSession(Base):
    __tablename__ = "guided_tour_sessions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("tour"))
    path_id: Mapped[str] = mapped_column(
        ForeignKey("guided_paths.id", ondelete="CASCADE"), index=True
    )
    preferred_style: Mapped[str] = mapped_column(String(40), default="beginner")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    current_step_ordinal: Mapped[int] = mapped_column(Integer, default=1)
    completed_step_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    needs_help_step_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    path: Mapped[GuidedPath] = relationship(back_populates="sessions")
    events: Mapped[list[GuidedStepEvent]] = relationship(
        back_populates="tour_session", cascade="all, delete-orphan"
    )


class GuidedStepEvent(Base):
    __tablename__ = "guided_step_events"
    __table_args__ = (Index("ix_guided_event_session_created", "tour_session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("gse"))
    tour_session_id: Mapped[str] = mapped_column(
        ForeignKey("guided_tour_sessions.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(
        ForeignKey("guided_steps.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tour_session: Mapped[GuidedTourSession] = relationship(back_populates="events")
    step: Mapped[GuidedStep] = relationship(back_populates="events")


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("learn"))
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    anonymous_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    goal: Mapped[str] = mapped_column(String(60), default="understand_whole_project")
    preferred_explanation: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["line_by_line", "analogy"]
    )
    pace: Mapped[str] = mapped_column(String(40), default="careful")
    background: Mapped[dict] = mapped_column(JSONB, default=dict)
    concept_mastery: Mapped[dict] = mapped_column(JSONB, default=dict)
    assessment_version: Mapped[str] = mapped_column(String(60), default="stack-diagnostic-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"
    __table_args__ = (
        Index(
            "uq_assessment_snapshot_profile_version",
            "snapshot_id",
            "learner_profile_id",
            "assessment_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("asm"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    learner_profile_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    detected_stack: Mapped[list[str]] = mapped_column(JSONB, default=list)
    questions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    assessment_version: Mapped[str] = mapped_column(String(60), default="stack-diagnostic-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="assessment_sessions")
    profile: Mapped[LearnerProfile] = relationship()
    responses: Mapped[list[AssessmentResponse]] = relationship(
        back_populates="assessment_session", cascade="all, delete-orphan"
    )


class AssessmentResponse(Base):
    __tablename__ = "assessment_responses"
    __table_args__ = (
        Index(
            "uq_assessment_response_session_item",
            "assessment_session_id",
            "item_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("asr"))
    assessment_session_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_sessions.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(String(80), index=True)
    answer: Mapped[str] = mapped_column(String(500))
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score_delta: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    assessment_session: Mapped[AssessmentSession] = relationship(back_populates="responses")


class LearningPath(Base):
    __tablename__ = "learning_paths"
    __table_args__ = (
        Index(
            "uq_learning_path_snapshot_profile_version",
            "snapshot_id",
            "learner_profile_id",
            "path_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("lpath"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    learner_profile_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    goal: Mapped[str] = mapped_column(String(60), default="understand_whole_project")
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    path_version: Mapped[str] = mapped_column(String(60), default="adaptive-curriculum-v1")
    generation_method: Mapped[str] = mapped_column(String(80), default="verified-structure-v1")
    coverage: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="learning_paths")
    profile: Mapped[LearnerProfile] = relationship()
    modules: Mapped[list[LearningModule]] = relationship(
        back_populates="path", cascade="all, delete-orphan", order_by="LearningModule.ordinal"
    )
    sessions: Mapped[list[LearningSession]] = relationship(
        back_populates="path", cascade="all, delete-orphan"
    )


class LearningModule(Base):
    __tablename__ = "learning_modules"
    __table_args__ = (Index("uq_learning_module_path_ordinal", "path_id", "ordinal", unique=True),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("lmod"))
    path_id: Mapped[str] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    module_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(500))
    objective: Mapped[str] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0)
    coverage_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)

    path: Mapped[LearningPath] = relationship(back_populates="modules")
    lessons: Mapped[list[LearningLesson]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="LearningLesson.ordinal",
    )


class LearningLesson(Base):
    __tablename__ = "learning_lessons"
    __table_args__ = (
        Index("uq_learning_lesson_module_ordinal", "module_id", "ordinal", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("lesson"))
    module_id: Mapped[str] = mapped_column(
        ForeignKey("learning_modules.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    lesson_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(500))
    objective: Mapped[str] = mapped_column(Text)
    required_concept_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    checkpoint: Mapped[dict] = mapped_column(JSONB, default=dict)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=5)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)

    module: Mapped[LearningModule] = relationship(back_populates="lessons")
    steps: Mapped[list[LearningStep]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LearningStep.ordinal",
    )


class LearningStep(Base):
    __tablename__ = "learning_steps"
    __table_args__ = (
        Index("uq_learning_step_lesson_ordinal", "lesson_id", "ordinal", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("lstep"))
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("learning_lessons.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[str] = mapped_column(String(60))
    chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey("code_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    concept_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    instruction: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    lesson: Mapped[LearningLesson] = relationship(back_populates="steps")
    chunk: Mapped[CodeChunk | None] = relationship()
    activities: Mapped[list[LearningActivity]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )


class LearningActivity(Base):
    __tablename__ = "learning_activities"
    __table_args__ = (
        Index(
            "uq_learning_activity_step_type_version",
            "step_id",
            "activity_type",
            "generator_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(
        String(48), primary_key=True, default=lambda: new_id("activity")
    )
    step_id: Mapped[str] = mapped_column(
        ForeignKey("learning_steps.id", ondelete="CASCADE"), index=True
    )
    activity_type: Mapped[str] = mapped_column(String(60), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    answer_key: Mapped[str] = mapped_column(String(80))
    explanation: Mapped[str] = mapped_column(Text)
    concept_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_hash: Mapped[str] = mapped_column(String(80))
    generator_version: Mapped[str] = mapped_column(String(60), default="grounded-checkpoint-v1")
    verification_status: Mapped[str] = mapped_column(String(32), default="verified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    step: Mapped[LearningStep] = relationship(back_populates="activities")
    attempts: Mapped[list[ActivityAttempt]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id: Mapped[str] = mapped_column(
        String(48), primary_key=True, default=lambda: new_id("learnses")
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    learner_profile_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True
    )
    path_id: Mapped[str] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="CASCADE"), index=True
    )
    current_module_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_modules.id", ondelete="SET NULL"), nullable=True
    )
    current_lesson_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_lessons.id", ondelete="SET NULL"), nullable=True
    )
    current_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_steps.id", ondelete="SET NULL"), nullable=True
    )
    completed_lesson_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    return_stack: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    current_selection: Mapped[dict] = mapped_column(JSONB, default=dict)
    focus_concept_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    teaching_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="learning_sessions")
    profile: Mapped[LearnerProfile] = relationship()
    path: Mapped[LearningPath] = relationship(back_populates="sessions")
    events: Mapped[list[JourneyEvent]] = relationship(
        back_populates="learning_session", cascade="all, delete-orphan"
    )
    activity_attempts: Mapped[list[ActivityAttempt]] = relationship(
        back_populates="learning_session", cascade="all, delete-orphan"
    )
    mastery_events: Mapped[list[MasteryEvent]] = relationship(back_populates="learning_session")


class ActivityAttempt(Base):
    __tablename__ = "activity_attempts"
    __table_args__ = (
        Index("ix_activity_attempt_session_created", "learning_session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("attempt"))
    learning_session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    activity_id: Mapped[str] = mapped_column(
        ForeignKey("learning_activities.id", ondelete="CASCADE"), index=True
    )
    selected_choice_id: Mapped[str] = mapped_column(String(80))
    is_correct: Mapped[bool] = mapped_column(Boolean, index=True)
    score_delta: Mapped[float] = mapped_column(Float)
    feedback: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    learning_session: Mapped[LearningSession] = relationship(back_populates="activity_attempts")
    activity: Mapped[LearningActivity] = relationship(back_populates="attempts")


class MasteryEvent(Base):
    __tablename__ = "mastery_events"
    __table_args__ = (
        Index(
            "ix_mastery_profile_concept_created", "learner_profile_id", "concept_id", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("mastery"))
    learner_profile_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"), index=True
    )
    learning_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    concept_id: Mapped[str] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    source_type: Mapped[str] = mapped_column(String(60), index=True)
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    previous_score: Mapped[float] = mapped_column(Float)
    new_score: Mapped[float] = mapped_column(Float)
    previous_confidence: Mapped[float] = mapped_column(Float)
    new_confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    policy_version: Mapped[str] = mapped_column(String(60), default="mastery-policy-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    learning_session: Mapped[LearningSession | None] = relationship(back_populates="mastery_events")


class JourneyEvent(Base):
    __tablename__ = "journey_events"
    __table_args__ = (
        Index("ix_journey_event_session_created", "learning_session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("jev"))
    learning_session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    module_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    lesson_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    step_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    learning_session: Mapped[LearningSession] = relationship(back_populates="events")


class RemediationBranch(Base):
    __tablename__ = "remediation_branches"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("branch"))
    learning_session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    source_lesson_id: Mapped[str] = mapped_column(
        ForeignKey("learning_lessons.id", ondelete="CASCADE"), index=True
    )
    source_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_steps.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    concept_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    return_lesson_id: Mapped[str] = mapped_column(String(48))
    return_step_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExplanationArtifact(Base):
    __tablename__ = "explanation_artifacts"
    __table_args__ = (
        Index(
            "uq_explanation_chunk_type_depth_version",
            "chunk_id",
            "artifact_type",
            "depth_band",
            "segmenter_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("explain"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("code_chunks.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(60), default="line_by_line")
    depth_band: Mapped[str] = mapped_column(String(40), default="beginner")
    segments: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    source_hash: Mapped[str] = mapped_column(String(80))
    segmenter_version: Mapped[str] = mapped_column(String(60), default="tree-sitter-statements-v1")
    model_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    verification_status: Mapped[str] = mapped_column(String(32), default="verified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        Index("uq_knowledge_source_concept_url", "concept_id", "canonical_url", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("ksrc"))
    concept_id: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(500))
    publisher: Mapped[str] = mapped_column(String(160))
    canonical_url: Mapped[str] = mapped_column(String(1000))
    source_tier: Mapped[str] = mapped_column(String(40), default="official")
    difficulty: Mapped[str] = mapped_column(String(40), default="beginner")
    language: Mapped[str] = mapped_column(String(20), default="ko")
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=10)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(80), index=True)
    difficulty: Mapped[str] = mapped_column(String(40), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    graph_version: Mapped[str] = mapped_column(String(60), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ConceptEdge(Base):
    __tablename__ = "concept_edges"
    __table_args__ = (
        Index(
            "uq_concept_edge_version_relation",
            "source_concept_id",
            "target_concept_id",
            "relation",
            "graph_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("cedge"))
    source_concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    target_concept_id: Mapped[str] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    rationale: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(120), default="curated")
    graph_version: Mapped[str] = mapped_column(String(60), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("ses"))
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    goal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferred_style: Mapped[str] = mapped_column(String(40), default="beginner")
    teaching_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    current_selection: Mapped[dict] = mapped_column(JSONB, default=dict)
    navigation_context: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    learning_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="chat_sessions")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("msg"))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), index=True)
    content: Mapped[str] = mapped_column(Text)
    structured_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class DeepTask(Base):
    __tablename__ = "deep_tasks"
    __table_args__ = (
        Index(
            "ix_deep_task_learning_status_created",
            "learning_session_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_deep_task_learning_idempotency",
            "learning_session_id",
            "idempotency_key",
            unique=True,
        ),
        Index(
            "uq_deep_task_chat_idempotency",
            "chat_session_id",
            "idempotency_key",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("dtask"))
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cost_reservation_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    learning_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chat_session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)
    modality: Mapped[str] = mapped_column(String(20), default="text")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)
    selection: Mapped[dict] = mapped_column(JSONB, default=dict)
    context_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    teaching_style: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="심층 작업을 준비하고 있습니다.")
    rq_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    result_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    result_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetrievalRun(Base):
    __tablename__ = "retrieval_runs"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("run"))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    query_text: Mapped[str] = mapped_column(Text)
    resolved_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    intent: Mapped[str] = mapped_column(String(40), index=True)
    retrieval_plan: Mapped[dict] = mapped_column(JSONB, default=dict)
    index_version: Mapped[str] = mapped_column(String(60))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    token_usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    cache_source_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cache_status: Mapped[str] = mapped_column(String(32), default="miss", index=True)
    cache_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalCandidate(Base):
    __tablename__ = "retrieval_candidates"
    __table_args__ = (Index("ix_candidate_run_rank", "retrieval_run_id", "retriever", "rank"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("cand"))
    retrieval_run_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_runs.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[str] = mapped_column(String(48), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="repository_code")
    source_id: Mapped[str] = mapped_column(
        ForeignKey("code_chunks.id", ondelete="CASCADE"), index=True
    )
    retriever: Mapped[str] = mapped_column(String(40), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    raw_score: Mapped[float] = mapped_column(Float)
    rrf_score: Mapped[float] = mapped_column(Float, default=0.0)
    rerank_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (Index("uq_organization_slug", "slug", unique=True),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("org"))
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220))
    kind: Mapped[str] = mapped_column(String(32), default="personal", index=True)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        Index("uq_membership_organization_user", "organization_id", "user_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("mem"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="member", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class OrganizationRepository(Base):
    __tablename__ = "organization_repositories"
    __table_args__ = (
        Index("uq_organization_repository", "organization_id", "repository_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("orgrepo"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    added_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    visibility: Mapped[str] = mapped_column(String(32), default="organization")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferences_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SourceBlob(Base):
    __tablename__ = "source_blobs"

    content_hash: Mapped[str] = mapped_column(String(80), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    line_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FileParseArtifact(Base):
    __tablename__ = "file_parse_artifacts"
    __table_args__ = (
        Index(
            "uq_parse_artifact_identity",
            "content_hash",
            "language",
            "parser_version",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("parse"))
    content_hash: Mapped[str] = mapped_column(
        ForeignKey("source_blobs.content_hash", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(40))
    parser_version: Mapped[str] = mapped_column(String(80))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChunkTemplate(Base):
    __tablename__ = "chunk_templates"
    __table_args__ = (
        Index("uq_chunk_template_identity", "content_hash", "chunker_fingerprint", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("ctpl"))
    content_hash: Mapped[str] = mapped_column(
        ForeignKey("source_blobs.content_hash", ondelete="CASCADE"), index=True
    )
    chunker_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"
    __table_args__ = (
        Index(
            "uq_embedding_cache_identity",
            "provider",
            "model",
            "dimensions",
            "prompt_version",
            "text_hash",
            unique=True,
        ),
        Index(
            "ix_embedding_cache_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("emb"))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    dimensions: Mapped[int] = mapped_column(Integer)
    prompt_version: Mapped[str] = mapped_column(String(80))
    text_hash: Mapped[str] = mapped_column(String(80), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    token_usage: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SnapshotManifest(Base):
    __tablename__ = "snapshot_manifests"
    __table_args__ = (Index("uq_snapshot_manifest_path", "snapshot_id", "path", unique=True),)

    id: Mapped[str] = mapped_column(
        String(48), primary_key=True, default=lambda: new_id("manifest")
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(80), index=True)
    language: Mapped[str] = mapped_column(String(40))
    byte_size: Mapped[int] = mapped_column(BigInteger)


class SnapshotFileLineage(Base):
    __tablename__ = "snapshot_file_lineage"
    __table_args__ = (Index("uq_snapshot_lineage_path", "snapshot_id", "path", unique=True),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("lineage"))
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    base_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), nullable=True, index=True
    )
    path: Mapped[str] = mapped_column(String(1000))
    previous_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    change_kind: Mapped[str] = mapped_column(String(32), index=True)
    reused_parse: Mapped[bool] = mapped_column(Boolean, default=False)
    reused_chunks: Mapped[bool] = mapped_column(Boolean, default=False)
    reused_embeddings: Mapped[int] = mapped_column(Integer, default=0)


class SemanticCacheEntry(Base):
    __tablename__ = "semantic_cache_entries"
    __table_args__ = (
        Index(
            "uq_semantic_cache_exact_scope",
            "cache_kind",
            "scope",
            "scope_id",
            "exact_key",
            unique=True,
        ),
        Index(
            "ix_semantic_cache_scope_snapshot_intent",
            "scope",
            "scope_id",
            "snapshot_id",
            "intent",
            "created_at",
        ),
        Index(
            "ix_semantic_cache_embedding_hnsw",
            "query_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"query_embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("cache"))
    cache_kind: Mapped[str] = mapped_column(String(24), index=True)
    scope: Mapped[str] = mapped_column(String(24), index=True)
    scope_id: Mapped[str] = mapped_column(String(128), default="public", index=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    compatible_evidence_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    exact_key: Mapped[str] = mapped_column(String(80), index=True)
    normalized_query: Mapped[str] = mapped_column(Text)
    query_embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    intent: Mapped[str] = mapped_column(String(40), index=True)
    context_fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_manifest: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    index_version: Mapped[str] = mapped_column(String(80))
    source_run_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("plan"))
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    monthly_allowance_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    policy_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class OrganizationSubscription(Base):
    __tablename__ = "organization_subscriptions"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class QuotaPeriod(Base):
    __tablename__ = "quota_periods"
    __table_args__ = (Index("uq_quota_org_period", "organization_id", "period_start", unique=True),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("quota"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    allowance_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    consumed_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    bonus_consumed_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FeatureLimit(Base):
    __tablename__ = "feature_limits"
    __table_args__ = (Index("uq_feature_limit_plan_feature", "plan_id", "feature", unique=True),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("flimit"))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    feature: Mapped[str] = mapped_column(String(80), index=True)
    request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    concurrent_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_input_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BonusCreditGrant(Base):
    __tablename__ = "bonus_credit_grants"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("bonus"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    amount_micro_usd: Mapped[int] = mapped_column(BigInteger)
    remaining_micro_usd: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(String(240))
    granted_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UsageReservation(Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (
        Index(
            "uq_usage_reservation_idempotency", "organization_id", "idempotency_key", unique=True
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("reserve"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quota_period_id: Mapped[str] = mapped_column(
        ForeignKey("quota_periods.id", ondelete="CASCADE"), index=True
    )
    feature: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(240))
    estimated_cost_micro_usd: Mapped[int] = mapped_column(BigInteger)
    settled_cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(40), default="reserved", index=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index("uq_usage_event_idempotency", "organization_id", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("usage"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reservation_id: Mapped[str | None] = mapped_column(
        ForeignKey("usage_reservations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feature: Mapped[str] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(40), default="settlement", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(240))
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    price_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    usage_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    estimated_cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    settled_cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    cache_status: Mapped[str] = mapped_column(String(32), default="miss")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class ModelPrice(Base):
    __tablename__ = "model_prices"
    __table_args__ = (
        Index(
            "uq_model_price_version", "provider", "model", "usage_type", "effective_at", unique=True
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("price"))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    usage_type: Mapped[str] = mapped_column(String(60))
    unit: Mapped[str] = mapped_column(String(40))
    micro_usd_per_unit: Mapped[int] = mapped_column(BigInteger)
    version: Mapped[str] = mapped_column(String(80))
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageDailyRollup(Base):
    __tablename__ = "usage_daily_rollups"
    __table_args__ = (
        Index(
            "uq_usage_rollup_key",
            "organization_id",
            "day",
            "feature",
            "provider",
            "model",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("rollup"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    feature: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(40), default="internal")
    model: Mapped[str] = mapped_column(String(120), default="none")
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit_count: Mapped[int] = mapped_column(Integer, default=0)
    usage_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    settled_cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("audit"))
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(120), index=True)
    target_type: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
