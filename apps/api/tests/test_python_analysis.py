from app.analysis.python import PythonAnalyzer


def test_extracts_python_routes_database_effects_and_failures() -> None:
    source = """from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from app.models import RepositorySnapshot

router = APIRouter()

@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, db):
    snapshot = db.scalar(select(RepositorySnapshot))
    if snapshot is None:
        raise HTTPException(status_code=404)
    return snapshot
"""

    result = PythonAnalyzer().parse("apps/api/app/api/repositories.py", source)

    route = next(symbol for symbol in result.symbols if symbol.display_name == "get_snapshot")
    assert route.kind == "route"
    assert route.exported_names == ("GET",)
    assert route.metadata["request_paths"] == ["/snapshots/{snapshot_id}"]

    relations = {edge.relation for edge in result.edges}
    assert {"IMPORTS", "CALLS", "READS", "RAISES"} <= relations
    read = next(edge for edge in result.edges if edge.relation == "READS")
    assert read.target == "database:RepositorySnapshot"
    assert read.metadata["storage_kind"] == "database"


def test_extracts_python_external_sdk_and_write_operations() -> None:
    source = """from openai import OpenAI

def generate(db, payload):
    client = OpenAI()
    db.add(payload)
    db.commit()
    return client.responses.create(input="hello")
"""

    result = PythonAnalyzer().parse("app/service.py", source)
    writes = [edge for edge in result.edges if edge.relation == "WRITES"]
    external = [edge for edge in result.edges if edge.relation == "USES_EXTERNAL"]

    assert len(writes) == 2
    assert external
    assert all(edge.target == "external:OpenAI" for edge in external)
