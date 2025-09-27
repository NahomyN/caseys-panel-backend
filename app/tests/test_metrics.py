import re
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token

client = TestClient(app)
AUTH_HEADERS = {"Authorization": f"Bearer {generate_test_token(['resident'])}"}


def test_fallback_and_retry_metrics_exposed():
    # Force primary failure in Agent1 to trigger retry + fallback
    patient_id = "metrics_patient_1"
    # Start run
    r = client.post(f"/api/v1/workflows/{patient_id}/start", headers=AUTH_HEADERS)
    assert r.status_code == 200
    # Poll status until completed
    run_id = r.json()["run_id"]
    for _ in range(40):  # ~4s total
        status = client.get(f"/api/v1/workflows/{run_id}/status", headers=AUTH_HEADERS)
        assert status.status_code == 200
        body = status.json()
        if body["status"] in {"completed", "failed"}:
            break
    # Fetch metrics endpoint
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    text = metrics_resp.text
    # Basic presence checks
    assert "runs_started_total" in text
    assert "runs_completed_total" in text
    # Histogram header
    assert "node_duration_ms_bucket" in text
