import pytest
from datetime import datetime
from app.services.checkpointer import PostgresCheckpointer
from app.services.models import WorkflowStatus, WorkflowRun, Base, Checkpoint
from app.services.database import SessionLocal, engine
from fastapi.testclient import TestClient
from app.api.workflows import router as workflows_router
from fastapi import FastAPI


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    # Create tables for test (idempotent for sqlite/postgres dev)
    Base.metadata.create_all(bind=engine)
    yield


def test_checkpointer_idempotent():
    cp = PostgresCheckpointer()
    run_id = cp.create_run_id("patient_demo")
    state_payload = {"output": {"foo": "bar"}, "status": "completed"}
    first_id = cp.save_checkpoint(run_id, "agent_1", state_payload)
    second_id = cp.save_checkpoint(run_id, "agent_1", state_payload)
    assert first_id == second_id, "Duplicate identical checkpoint rows should be collapsed"

    # Mutate state -> new row
    new_payload = {"output": {"foo": "baz"}, "status": "completed"}
    third_id = cp.save_checkpoint(run_id, "agent_1", new_payload)
    assert third_id != first_id


def test_api_status_aggregation(monkeypatch):
    # Build FastAPI app with router
    app = FastAPI()
    app.include_router(workflows_router)
    client = TestClient(app)

    cp = PostgresCheckpointer()
    run_id = cp.create_run_id("patient_status")
    cp.update_run_status(run_id, WorkflowStatus.RUNNING.value)

    cp.save_checkpoint(run_id, "agent_1", {"output": {"content_md": "# HPI"}, "status": "completed"})
    cp.save_checkpoint(run_id, "agent_2", {"output": {"content_md": "# PMH"}, "status": "completed"})

    resp = client.get(f"/workflows/{run_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["status"] in {"running", "completed", "failed", "pending"}
    assert "agent_1" in data["node_states"]
    assert data["node_states"]["agent_1"]["status"] == "completed"

    # Ensure no PHI leakage (we used placeholder content, but check structure only)
    for node, nd in data["node_states"].items():
        assert "output" in nd

