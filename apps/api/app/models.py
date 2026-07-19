from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Computed, DateTime, Float, ForeignKey, Index, Integer, String, Text
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
        back_populates="snapshot", cascade="all, delete-orphan"
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

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="jobs")


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

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="edges")


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
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    goal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferred_style: Mapped[str] = mapped_column(String(40), default="beginner")
    teaching_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    current_selection: Mapped[dict] = mapped_column(JSONB, default=dict)
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
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("dtask"))
    learning_session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    chat_session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), index=True)
    modality: Mapped[str] = mapped_column(String(20), default="text")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    prompt: Mapped[str] = mapped_column(Text)
    selection: Mapped[dict] = mapped_column(JSONB, default=dict)
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
