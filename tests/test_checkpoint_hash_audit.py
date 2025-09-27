from fastapi.testclient import TestClient
from app.api.workflows import router
from fastapi import FastAPI
from app.services.checkpointer import checkpointer
from app.services.database import Base, engine, SessionLocal
from app.services.models import AuditLog
from app.auth.security import generate_test_token
import uuid

app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_checkpoint_hash_dedupe_and_audit():
    run_id = checkpointer.create_run_id(f"pt_{uuid.uuid4().hex[:6]}")
    state = {"status": "completed", "output": {"val": 1}}
    id1 = checkpointer.save_checkpoint(run_id, "agent_1", state)
    id2 = checkpointer.save_checkpoint(run_id, "agent_1", state)
    assert id1 == id2  # deduped by hash

    # Canvas update triggers audit log
    patient_id = f"pt_{uuid.uuid4().hex[:6]}"
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(f"/api/v1/canvases/{patient_id}/1", json={"content_md": "# Test", "version": 1, "content_json": {}}, headers=headers)
    assert resp.status_code == 200
    db = SessionLocal()
    logs = db.query(AuditLog).filter(AuditLog.patient_id == patient_id).all()
    assert len(logs) == 1
    db.close()
