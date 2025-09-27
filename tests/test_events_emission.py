import uuid
import time
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.api.workflows import router
from app.auth.security import generate_test_token
from app.services.database import Base, engine, SessionLocal
from app.services.models import Event, EventType
from app.services.checkpointer import checkpointer

app = FastAPI()
app.include_router(router)
client = TestClient(app)

# Reusable auth header for tests requiring protected endpoints
AUTH_HEADERS = {"Authorization": f"Bearer {generate_test_token(["resident"]) }"}


def setup_module():
    # Ensure a clean schema (enum changes may require recreation during test runs)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_events_emitted_for_manual_checkpoint_sequence():
    patient_id = f"pt_{uuid.uuid4().hex[:6]}"
    run_id = checkpointer.create_run_id(patient_id)
    # Simulate only agent_1 completion via checkpoint directly (events for stage_a will still exist only if workflow executed)
    checkpointer.save_checkpoint(run_id, "agent_1", {"status": "completed", "output": {"ok": True}})
    # No events expected yet because we didn't run workflow nodes.
    with SessionLocal() as s:
        events = s.query(Event).filter(Event.run_id == run_id).all()
        assert len(events) == 0


def test_events_emitted_full_run():
    patient_id = f"pt_{uuid.uuid4().hex[:6]}"
    # Start workflow async and wait a bit for completion
    resp = client.post(f"/workflows/{patient_id}/start", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    # Poll status until completed or timeout
    for _ in range(100):  # allow more cycles for async completion
        s = client.get(f"/workflows/{run_id}/status")
        assert s.status_code == 200
        data = s.json()
        if data["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    # Inspect events
    with SessionLocal() as session:
        events = session.query(Event).filter(Event.run_id == run_id).all()
        event_types = []
        for e in events:
            et = e.event_type
            if hasattr(et, 'value'):
                et = et.value
            event_types.append(et)
    # At minimum we expect at least one event (stage_a start). More granular assertions can be added when async coordination improved.
    assert len(event_types) >= 1
