import uuid
from fastapi.testclient import TestClient
from app.api.workflows import router
from fastapi import FastAPI
from app.services.checkpointer import checkpointer
from app.services.database import Base, engine, SessionLocal
from app.services.models import WorkflowRun, WorkflowStatus

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_progress_and_resume_stub():
    patient_id = f"pt_{uuid.uuid4().hex[:6]}"
    run_id = checkpointer.create_run_id(patient_id)
    # simulate completed nodes
    for n in ["agent_1", "agent_2", "agent_3"]:
        checkpointer.save_checkpoint(run_id, n, {"status": "completed", "output": {"dummy": True}})
    # status
    resp = client.get(f"/workflows/{run_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["progress_pct"] >= 0
    # resume
    r2 = client.post(f"/workflows/{run_id}/resume")
    assert r2.status_code == 200
    d2 = r2.json()
    assert "agent_1" in d2["completed_nodes"]
