import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from rq.exceptions import DuplicateJobError

from app import queue
from app.api import deep_tasks
from app.core.config import Settings
from app.core.db import get_db
from app.schemas import (
    ChangeBriefResponse,
    ChatAnswerResponse,
    DeepTaskCreate,
)
from app.workers import deep_tasks as deep_task_worker

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _task(**overrides):
    values = {
        "id": "dtask_1",
        "learning_session_id": "learnses_1",
        "chat_session_id": "ses_1",
        "kind": "deep_explanation",
        "modality": "text",
        "idempotency_key": "request-1",
        "prompt": "인증 흐름을 깊게 설명해줘",
        "selection": {},
        "context_json": {},
        "teaching_style": "beginner",
        "status": "queued",
        "progress": 0,
        "message": "심층 작업이 대기열에 등록되었습니다.",
        "rq_job_id": None,
        "result_message_id": None,
        "result_payload": None,
        "model_metadata": {},
        "error_code": None,
        "error_detail": None,
        "created_at": NOW,
        "updated_at": NOW,
        "started_at": None,
        "finished_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CreateDb:
    def __init__(self, learning_session, scalar_results: list[object]) -> None:
        self.learning_session = learning_session
        self.scalar_results = iter(scalar_results)
        self.added = None
        self.commits = 0

    def get(self, _model, identifier):
        assert identifier == self.learning_session.id
        return self.learning_session

    def scalar(self, _statement):
        return next(self.scalar_results)

    def add(self, task) -> None:
        self.added = task
        task.id = "dtask_1"
        task.result_payload = None
        task.error_code = None
        task.error_detail = None
        task.model_metadata = {}

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def refresh(self, _task) -> None:
        pass


def test_create_deep_task_snapshots_context_and_enqueues_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learning = SimpleNamespace(
        id="learnses_1",
        snapshot_id="snap_1",
        current_selection={},
    )
    chat = SimpleNamespace(
        id="ses_1",
        current_selection={},
        preferred_style="advanced",
    )
    file = SimpleNamespace(id="file_1", line_count=30)
    db = CreateDb(learning, [None, chat, file])
    queued: list[str] = []

    def fake_enqueue(task_id: str) -> str:
        queued.append(task_id)
        return "rq_1"

    monkeypatch.setattr(deep_tasks, "enqueue_deep_task", fake_enqueue)
    payload = DeepTaskCreate(
        kind="impact_analysis",
        prompt="  이 변경의 영향을 분석해줘  ",
        selection={"file_id": "file_1", "start_line": 4, "end_line": 9},
        modality="voice",
    )

    response = deep_tasks.create_deep_task(
        "learnses_1",
        payload,
        db,
        " request-1 ",
    )

    assert response.model_dump(exclude_none=True) == {
        "id": "dtask_1",
        "status": "queued",
        "kind": "impact_analysis",
        "progress": 0,
        "message": "심층 작업이 대기열에 등록되었습니다.",
    }
    assert queued == ["dtask_1"]
    assert db.added.idempotency_key == "request-1"
    assert db.added.prompt == "이 변경의 영향을 분석해줘"
    assert db.added.selection == {"file_id": "file_1", "start_line": 4, "end_line": 9}
    assert db.added.teaching_style == "advanced"
    assert db.added.modality == "voice"
    assert db.added.rq_job_id == "rq_1"
    assert db.commits == 2


def test_deep_task_post_contract_is_202_and_requires_idempotency_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learning = SimpleNamespace(
        id="learnses_1",
        snapshot_id="snap_1",
        current_selection={},
    )
    chat = SimpleNamespace(
        id="ses_1",
        current_selection={},
        preferred_style="beginner",
    )
    db = CreateDb(learning, [None, chat])
    monkeypatch.setattr(deep_tasks, "enqueue_deep_task", lambda _task_id: "rq_1")
    app = FastAPI()
    app.include_router(deep_tasks.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    body = {
        "kind": "deep_explanation",
        "prompt": "인증 흐름을 설명해줘",
        "modality": "text",
    }

    missing = client.post("/api/learning-sessions/learnses_1/deep-tasks", json=body)
    accepted = client.post(
        "/api/learning-sessions/learnses_1/deep-tasks",
        json=body,
        headers={"Idempotency-Key": "request-1"},
    )

    assert missing.status_code == 422
    assert accepted.status_code == 202
    assert accepted.json() == {
        "id": "dtask_1",
        "status": "queued",
        "kind": "deep_explanation",
        "progress": 0,
        "message": "심층 작업이 대기열에 등록되었습니다.",
    }


def test_create_deep_task_returns_existing_idempotent_task_without_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learning = SimpleNamespace(id="learnses_1")
    existing = _task(status="running", progress=35, message="분석 중입니다.")
    db = CreateDb(learning, [existing])
    monkeypatch.setattr(
        deep_tasks,
        "enqueue_deep_task",
        lambda _task_id: pytest.fail("duplicate task must not be enqueued"),
    )

    response = deep_tasks.create_deep_task(
        "learnses_1",
        DeepTaskCreate(kind="impact_analysis", prompt="영향을 분석해줘"),
        db,
        "request-1",
    )

    assert response.id == "dtask_1"
    assert response.status == "running"
    assert response.progress == 35
    assert db.added is None


def test_research_materials_is_accepted_by_the_verified_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learning = SimpleNamespace(id="learnses_1", snapshot_id="snap_1", current_selection={})
    chat = SimpleNamespace(id="ses_1", current_selection={}, preferred_style="beginner")
    db = CreateDb(learning, [None, chat])
    monkeypatch.setattr(deep_tasks, "enqueue_deep_task", lambda _task_id: "rq_1")

    response = deep_tasks.create_deep_task(
        "learnses_1",
        DeepTaskCreate(kind="research_materials", prompt="공식 자료를 찾아줘"),
        db,
        "request-1",
    )

    assert response.status == "queued"
    assert db.added.kind == "research_materials"


class NavigationCreateDb:
    def __init__(self, chat_session, scalar_results: list[object]) -> None:
        self.chat_session = chat_session
        self.scalar_results = iter(scalar_results)
        self.added = None
        self.commits = 0

    def get(self, model, identifier):
        if model is deep_tasks.ChatSession and identifier == self.chat_session.id:
            return self.chat_session
        return None

    def scalar(self, _statement):
        return next(self.scalar_results)

    def add(self, task) -> None:
        self.added = task
        task.id = "dtask_navigation"
        task.rq_job_id = None
        task.result_payload = None
        task.error_code = None
        task.error_detail = None
        task.model_metadata = {}

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def refresh(self, _task) -> None:
        pass


def test_navigation_deep_task_snapshots_safe_context_without_learning_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = SimpleNamespace(
        id="ses_nav",
        snapshot_id="snap_1",
        current_selection={},
        navigation_context={},
        preferred_style="beginner",
    )
    file = SimpleNamespace(id="file_1", line_count=40)
    db = NavigationCreateDb(chat, [None, file])
    monkeypatch.setattr(deep_tasks, "enqueue_deep_task", lambda _task_id: "rq_nav")

    response = deep_tasks.create_navigation_deep_task(
        chat.id,
        DeepTaskCreate(
            kind="impact_analysis",
            prompt="로그인 결과를 바꾸면 어디가 달라질까?",
            selection={"file_id": "file_1", "start_line": 4, "end_line": 9},
            navigation_context={
                "feature_key": "login-flow",
                "flow_step_id": "step-submit",
                "explanation_depth": "change",
            },
        ),
        db,
        "nav-request-1",
    )

    assert response.status == "queued"
    assert db.added.learning_session_id is None
    assert db.added.chat_session_id == chat.id
    assert db.added.context_json == {
        "scope": "navigation",
        "navigation_context": {
            "feature_key": "login-flow",
            "flow_step_id": "step-submit",
            "explanation_depth": "change",
            "selection": {"file_id": "file_1", "start_line": 4, "end_line": 9},
        },
    }
    assert chat.navigation_context == db.added.context_json["navigation_context"]
    assert db.added.rq_job_id == "rq_nav"


def test_navigation_deep_task_rejects_non_impact_kind() -> None:
    chat = SimpleNamespace(id="ses_nav")
    db = NavigationCreateDb(chat, [])

    with pytest.raises(HTTPException) as error:
        deep_tasks.create_navigation_deep_task(
            chat.id,
            DeepTaskCreate(kind="deep_explanation", prompt="자세히 설명해줘"),
            db,
            "nav-request-1",
        )

    assert error.value.status_code == 422


def test_navigation_deep_task_returns_idempotent_chat_task_without_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = SimpleNamespace(id="ses_nav")
    existing = _task(
        learning_session_id=None,
        chat_session_id=chat.id,
        status="running",
        progress=55,
        context_json={"scope": "navigation"},
    )
    db = NavigationCreateDb(chat, [existing])
    monkeypatch.setattr(
        deep_tasks,
        "enqueue_deep_task",
        lambda _task_id: pytest.fail("idempotent navigation task must not enqueue again"),
    )

    response = deep_tasks.create_navigation_deep_task(
        chat.id,
        DeepTaskCreate(kind="impact_analysis", prompt="영향을 분석해줘"),
        db,
        "nav-request-1",
    )

    assert response.id == existing.id
    assert response.status == "running"
    assert db.added is None


def test_idempotent_retry_recovers_queued_task_missing_rq_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learning = SimpleNamespace(id="learnses_1")
    existing = _task(rq_job_id=None)
    db = CreateDb(learning, [existing])
    queued: list[str] = []

    def fake_enqueue(task_id: str) -> str:
        queued.append(task_id)
        return task_id

    monkeypatch.setattr(deep_tasks, "enqueue_deep_task", fake_enqueue)

    response = deep_tasks.create_deep_task(
        "learnses_1",
        DeepTaskCreate(kind="deep_explanation", prompt="코드를 설명해줘"),
        db,
        "request-1",
    )

    assert response.status == "queued"
    assert queued == ["dtask_1"]
    assert existing.rq_job_id == "dtask_1"
    assert db.commits == 1


@pytest.mark.parametrize("key", ["   ", "x" * 201])
def test_create_deep_task_rejects_invalid_idempotency_key(key: str) -> None:
    learning = SimpleNamespace(id="learnses_1")
    db = CreateDb(learning, [])

    with pytest.raises(HTTPException) as error:
        deep_tasks.create_deep_task(
            "learnses_1",
            DeepTaskCreate(kind="deep_explanation", prompt="코드를 설명해줘"),
            db,
            key,
        )

    assert error.value.status_code == 422


class ReadDb:
    def __init__(self, task) -> None:
        self.task = task

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        pass

    def get(self, _model, _identifier):
        return self.task


def test_deep_task_sse_emits_status_transitions_and_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states = iter(
        [
            _task(),
            _task(status="running", progress=30, message="분석 중입니다.", updated_at=NOW),
            _task(
                status="completed",
                progress=100,
                message="완료되었습니다.",
                updated_at=NOW,
            ),
        ]
    )
    monkeypatch.setattr(deep_tasks, "SessionLocal", lambda: ReadDb(next(states)))
    monkeypatch.setattr(deep_tasks.time, "sleep", lambda _seconds: None)

    events = list(
        deep_tasks.deep_task_event_stream(
            "dtask_1",
            poll_interval=0,
            heartbeat_interval=0,
        )
    )

    assert events[0].startswith("event: queued\n")
    assert events[1].startswith("event: heartbeat\n")
    assert events[2].startswith("event: running\n")
    assert events[3].startswith("event: heartbeat\n")
    assert events[4].startswith("event: completed\n")
    completed_data = json.loads(events[4].split("data: ", 1)[1])
    assert completed_data["progress"] == 100


class WorkerDb(ReadDb):
    def __init__(self, task) -> None:
        super().__init__(task)
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def scalar(self, _statement):
        return self.task


def test_worker_uses_escalation_model_and_persists_compatible_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(kind="roadmap_proposal", modality="voice")
    db = WorkerDb(task)
    captured: dict = {}
    response = ChatAnswerResponse(
        id="msg_1",
        session_id="ses_1",
        question=task.prompt,
        answer="심층 답변",
        status="grounded",
        intent="architecture",
        retrieval_run_id="run_1",
        citations=[
            {
                "evidence_id": "ev_1",
                "snapshot_id": "snap_1",
                "file_id": "file_1",
                "path": "src/auth.ts",
                "language": "typescript",
                "title": "login",
                "chunk_type": "symbol",
                "start_line": 1,
                "end_line": 5,
                "preview": "login",
                "score": 1.0,
                "retrievers": ["exact"],
            }
        ],
        follow_up=None,
        voice_summary="짧은 음성 요약",
        generation_mode="openai",
        model_name="sol-test",
        created_at=NOW,
    )

    def fake_grounded(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return response

    settings = Settings(
        deep_model="terra-test",
        deep_reasoning_effort="medium",
        deep_escalation_model="sol-test",
        deep_escalation_reasoning_effort="high",
    )
    monkeypatch.setattr(deep_task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(deep_task_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(deep_task_worker, "create_grounded_message", fake_grounded)

    deep_task_worker.run_deep_task("dtask_1")

    assert captured["args"] == (db,)
    assert captured["kwargs"]["generation_model_override"] == "sol-test"
    assert captured["kwargs"]["reasoning_effort"] == "high"
    assert captured["kwargs"]["allow_retrieval_fallback"] is False
    assert captured["kwargs"]["task_kind"] == "roadmap_proposal"
    assert captured["kwargs"]["metadata_overrides"] == {
        "route": "roadmap_proposal",
        "model": "sol-test",
        "reasoning_effort": "high",
        "prompt_version": "deep-tutor-v1",
        "modality": "voice",
        "deep_task_id": "dtask_1",
    }
    assert task.status == "completed"
    assert task.progress == 100
    assert task.result_message_id == "msg_1"
    assert task.result_payload == response.model_dump(mode="json")
    assert task.model_metadata["model"] == "sol-test"
    assert db.commits == 2


def test_worker_persists_structured_navigation_change_brief(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(
        kind="impact_analysis",
        learning_session_id=None,
        context_json={"scope": "navigation", "navigation_context": {}},
    )
    db = WorkerDb(task)
    brief = ChangeBriefResponse(
        id="change_1",
        snapshot_id="snap_1",
        analysis_version="change-brief-v1",
        request_summary=task.prompt,
        selection={"file_id": "file_1", "start_line": 1, "end_line": 5},
        candidate_locations=[
            {
                "title": "login",
                "reason": "선택 위치",
                "confidence": "verified",
                "evidence": {
                    "file_id": "file_1",
                    "path": "src/auth.ts",
                    "start_line": 1,
                    "end_line": 5,
                    "reason": "선택 근거",
                },
            }
        ],
        confirmed_direct_impacts=[],
        possible_impacts_to_verify=[],
        unknown_boundaries=["런타임 호출"],
        risk_level="unknown",
        risk_rationale="근거 부족",
        verification_steps=["테스트 실행"],
        rollback_guidance=["커밋 되돌리기"],
        evidence=[
            {
                "file_id": "file_1",
                "path": "src/auth.ts",
                "start_line": 1,
                "end_line": 5,
                "reason": "선택 근거",
            }
        ],
        limitations=["정적 분석"],
    )
    monkeypatch.setattr(deep_task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(deep_task_worker, "get_settings", Settings)
    monkeypatch.setattr(deep_task_worker, "generate_change_brief", lambda *_args: brief)
    monkeypatch.setattr(
        deep_task_worker,
        "create_grounded_message",
        lambda *_args, **_kwargs: pytest.fail("navigation task must not use free-form generation"),
    )

    deep_task_worker.run_deep_task(task.id)

    assert task.status == "completed"
    assert task.result_payload == brief.model_dump(mode="json")
    assert task.model_metadata["generation_mode"] == "deterministic_semantic_graph"
    assert task.result_message_id is None


def test_worker_persists_provider_failure_instead_of_false_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    db = WorkerDb(task)
    monkeypatch.setattr(deep_task_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(deep_task_worker, "get_settings", lambda: Settings())
    monkeypatch.setattr(
        deep_task_worker,
        "create_grounded_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider failed")),
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        deep_task_worker.run_deep_task("dtask_1")

    assert task.status == "failed"
    assert task.error_code == "generation_failed"
    assert task.error_detail == "심층 모델 응답을 생성하지 못했습니다."
    assert task.finished_at is not None


def test_failed_task_response_does_not_expose_internal_error_detail() -> None:
    task = _task(
        status="failed",
        message="심층 작업을 완료하지 못했습니다.",
        error_code="RuntimeError",
        error_detail="postgresql://user:secret@internal/database",
    )

    response = deep_tasks._task_response(task)

    assert response.error is not None
    assert response.error.code == "RuntimeError"
    assert response.error.message == "심층 작업을 완료하지 못했습니다."
    assert "secret" not in response.model_dump_json()


def test_cancel_deep_task_marks_terminal_and_requests_rq_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(status="running", progress=35, rq_job_id="rq_1")
    db = WorkerDb(task)
    stopped: list[str] = []
    monkeypatch.setattr(
        deep_tasks,
        "cancel_deep_task_job",
        lambda job_id: stopped.append(job_id) or True,
    )

    response = deep_tasks.cancel_deep_task("dtask_1", db)

    assert response.status == "cancelled"
    assert response.progress == 100
    assert task.finished_at is not None
    assert stopped == ["rq_1"]
    assert db.commits == 1


def test_cancel_deep_task_is_idempotent_for_terminal_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task(status="completed", progress=100, rq_job_id="rq_1")
    db = WorkerDb(task)
    monkeypatch.setattr(
        deep_tasks,
        "cancel_deep_task_job",
        lambda _job_id: pytest.fail("terminal task must not touch RQ"),
    )

    response = deep_tasks.cancel_deep_task("dtask_1", db)

    assert response.status == "completed"
    assert db.commits == 0


def test_enqueue_deep_task_uses_dedicated_queue_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    class FakeQueue:
        def enqueue(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return SimpleNamespace(id="rq_1")

    monkeypatch.setattr(queue, "get_deep_task_queue", lambda: FakeQueue())
    monkeypatch.setattr(
        queue,
        "get_settings",
        lambda: Settings(deep_task_timeout_seconds=321),
    )

    job_id = queue.enqueue_deep_task("dtask_1")

    assert job_id == "rq_1"
    assert captured["args"] == (
        "app.workers.deep_tasks.run_deep_task",
        "dtask_1",
    )
    assert captured["kwargs"]["job_timeout"] == 321
    assert captured["kwargs"]["job_id"] == "dtask_1"
    assert captured["kwargs"]["unique"] is True


def test_enqueue_deep_task_treats_existing_deterministic_job_as_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DuplicateQueue:
        def enqueue(self, *_args, **_kwargs):
            raise DuplicateJobError

    monkeypatch.setattr(queue, "get_deep_task_queue", lambda: DuplicateQueue())
    monkeypatch.setattr(queue, "get_settings", Settings)

    assert queue.enqueue_deep_task("dtask_1") == "dtask_1"


def test_cancel_deep_task_job_stops_running_job(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = object()
    fake_job = SimpleNamespace(get_status=lambda refresh: "started")
    stopped: list[tuple[object, str]] = []
    monkeypatch.setattr(
        queue,
        "get_deep_task_queue",
        lambda: SimpleNamespace(connection=connection),
    )
    monkeypatch.setattr(queue.Job, "fetch", lambda *_args, **_kwargs: fake_job)
    monkeypatch.setattr(
        queue,
        "send_stop_job_command",
        lambda conn, job_id: stopped.append((conn, job_id)),
    )

    assert queue.cancel_deep_task_job("dtask_1") is True
    assert stopped == [(connection, "dtask_1")]
