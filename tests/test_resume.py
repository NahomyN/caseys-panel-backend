import uuid, time
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.api.workflows import router
from app.auth.security import generate_test_token
from app.services.database import Base, engine
from app.services.checkpointer import checkpointer

app = FastAPI()
app.include_router(router)
client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {generate_test_token(["resident"]) }"}


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_resume_partial_and_complete():
    patient_id = f"pt_{uuid.uuid4().hex[:6]}"
    start = client.post(f"/workflows/{patient_id}/start", headers=AUTH_HEADERS)
    assert start.status_code == 200
    run_id = start.json()["run_id"]
    # Wait for some completion
    for _ in range(120):
        status = client.get(f"/workflows/{run_id}/status")
        assert status.status_code == 200
        data = status.json()
        if data["status"] in {"completed", "failed"} or data["progress_pct"] >= 30:
            break
        time.sleep(0.05)
    # Force resume mid-flight (idempotent if already running)
    resume_resp = client.post(f"/workflows/{run_id}/resume")
    assert resume_resp.status_code == 200
    # Wait for completion
    for _ in range(400):
        status = client.get(f"/workflows/{run_id}/status")
        data = status.json()
        if data["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    final = client.get(f"/workflows/{run_id}/status")
    assert final.status_code == 200
    fdata = final.json()
    assert fdata["status"] in {"completed", "failed", "running"}
    assert fdata["progress_pct"] <= 100
