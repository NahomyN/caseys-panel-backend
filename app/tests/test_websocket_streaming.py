import json
import time
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token


client = TestClient(app)
# Pre-generate authorization header for protected workflow start endpoint
AUTH_HEADERS = {"Authorization": f"Bearer {generate_test_token(['resident'])}"}


def test_websocket_receives_workflow_events():
    patient_id = "ws_patient_1"
    with client.websocket_connect(f"/api/v1/ws?patient_id={patient_id}") as ws:
        # Start workflow first (event may arrive quickly)
        r = client.post(f"/api/v1/workflows/{patient_id}/start", headers=AUTH_HEADERS)
        assert r.status_code == 200
        run_id = r.json()["run_id"]

        # Send an echo ping (either echo or event may arrive first)
        ws.send_text("ping")

        messages = []
        # Collect up to two messages (echo + event)
        for _ in range(2):
            try:
                txt = ws.receive_text()
                messages.append(txt)
            except Exception:
                break

        # If event not yet received, allow a brief sleep and attempt one more receive
        if not any("workflow.event" in m for m in messages):
            time.sleep(0.5)
            try:
                messages.append(ws.receive_text())
            except Exception:
                pass

        target_payload = None
        for m in messages:
            try:
                obj = json.loads(m)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "workflow.event":
                target_payload = obj
                break
        assert target_payload is not None, f"Did not receive workflow.event message; got: {messages}"
        inner = target_payload.get("data", {})
        assert inner.get("run_id") == run_id
        assert inner.get("phase") in {"started", "progress", "completed", "failed", "retried"}
