from types import SimpleNamespace

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.navigation.artifacts import (
    ArtifactWrite,
    load_navigation_artifact,
    write_navigation_artifacts,
)


class _Payload(BaseModel):
    name: str
    confidence: str = "verified"
    evidence: list[dict[str, object]] = []


class _ArtifactDb:
    def __init__(
        self,
        artifact: object | None = None,
        fail_write: bool = False,
        fail_read: bool = False,
    ) -> None:
        self.artifact = artifact
        self.fail_write = fail_write
        self.fail_read = fail_read
        self.executed: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def scalar(self, _statement: object) -> object | None:
        if self.fail_read:
            raise SQLAlchemyError("cache read unavailable")
        return self.artifact

    def execute(self, statement: object) -> None:
        if self.fail_write:
            raise SQLAlchemyError("cache unavailable")
        self.executed.append(statement)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _artifact(**overrides: object) -> object:
    values = {
        "snapshot_id": "snap-1",
        "artifact_type": "project_map",
        "artifact_key": "default",
        "artifact_version": "project-map-v2",
        "status": "ready",
        "payload_json": {"name": "Map"},
        "generation_metadata": {"commit_sha": "commit-1"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _load(db: _ArtifactDb) -> _Payload | None:
    return load_navigation_artifact(
        db,  # type: ignore[arg-type]
        snapshot_id="snap-1",
        artifact_type="project_map",
        artifact_key="default",
        artifact_version="project-map-v2",
        payload_model=_Payload,
        commit_sha="commit-1",
    )


def test_loads_only_an_exact_validated_artifact() -> None:
    assert _load(_ArtifactDb(_artifact())) == _Payload(name="Map")
    assert _load(_ArtifactDb(_artifact(artifact_version="project-map-v1"))) is None
    assert _load(_ArtifactDb(_artifact(status="invalid"))) is None
    assert _load(_ArtifactDb(_artifact(generation_metadata={"commit_sha": "old"}))) is None
    assert _load(_ArtifactDb(_artifact(payload_json={"unexpected": True}))) is None

    failing = _ArtifactDb(fail_read=True)
    assert _load(failing) is None
    assert failing.rollbacks == 1


def test_writes_with_atomic_upsert_and_degrades_on_database_failure() -> None:
    payload = _Payload(
        name="Map",
        evidence=[
            {
                "file_id": "file-1",
                "path": "README.md",
                "start_line": 1,
                "end_line": 1,
            }
        ],
    )
    write = ArtifactWrite(
        artifact_type="project_map",
        artifact_key="default",
        artifact_version="project-map-v2",
        payload=payload,
    )
    healthy = _ArtifactDb()

    assert write_navigation_artifacts(
        healthy,  # type: ignore[arg-type]
        snapshot_id="snap-1",
        commit_sha="commit-1",
        artifacts=[write],
    )
    assert len(healthy.executed) == 1
    assert healthy.commits == 1
    assert healthy.rollbacks == 0

    failing = _ArtifactDb(fail_write=True)
    assert not write_navigation_artifacts(
        failing,  # type: ignore[arg-type]
        snapshot_id="snap-1",
        commit_sha="commit-1",
        artifacts=[write],
    )
    assert failing.commits == 0
    assert failing.rollbacks == 1
