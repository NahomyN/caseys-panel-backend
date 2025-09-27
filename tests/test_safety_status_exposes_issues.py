import time
import uuid
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.api.workflows import router
from app.auth.security import generate_test_token
from app.services.database import Base, engine

app = FastAPI()
app.include_router(router)
client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {generate_test_token(['resident']) }"}

def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_safety_issues_surface_in_status():
    patient_id = f"pt_{uuid.uuid4().hex[:6]}"
    resp = client.post(f"/workflows/{patient_id}/start?sync=1", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    # Poll until completion
    # Allow more cycles for asynchronous background execution
    # Synchronous run means status should already be terminal
    s = client.get(f"/workflows/{run_id}/status")
    assert s.status_code == 200
    data = s.json()
    assert data["status"] in {"completed", "failed"}
    assert "safety_issues" in data
    assert isinstance(data["safety_issues"], list)
    if data["safety_issues"]:
        first = data["safety_issues"][0]
        for k in ["rule_id", "message", "severity", "source", "created_at"]:
            assert k in first
