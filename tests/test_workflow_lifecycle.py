"""
Test workflow lifecycle management: list, cancel, resume operations.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token
from app.services.models import WorkflowStatus


client = TestClient(app)


@pytest.fixture
def auth_headers():
    token = generate_test_token(["attending"], patients=["test-lifecycle", "*"])
    return {"Authorization": f"Bearer {token}"}


def test_list_workflows_empty(auth_headers):
    """Test listing workflows when none exist for patient."""
    response = client.get("/api/v1/workflows?patient_id=nonexistent&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["count"] == 0
    assert data["items"] == []


def test_list_workflows_with_pagination(auth_headers):
    """Test workflow listing with pagination parameters."""
    # Start multiple workflows
    run_ids = []
    for i in range(3):
        resp = client.post("/api/v1/workflows/test-lifecycle/start?sync=1", headers=auth_headers)
        resp.raise_for_status()
        run_ids.append(resp.json()["run_id"])
    
    # Test pagination
    response = client.get("/api/v1/workflows?limit=2&offset=0", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["items"]) == 2
    
    # Test second page
    response = client.get("/api/v1/workflows?limit=2&offset=2", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["count"] <= 2  # May be less if fewer total runs


def test_list_workflows_status_filter(auth_headers):
    """Test filtering workflows by status."""
    # Start one sync (completed) and one async (may be running)
    sync_resp = client.post("/api/v1/workflows/test-lifecycle/start?sync=1", headers=auth_headers)
    sync_resp.raise_for_status()
    
    async_resp = client.post("/api/v1/workflows/test-lifecycle/start", headers=auth_headers)
    async_resp.raise_for_status()
    async_run_id = async_resp.json()["run_id"]
    
    # Filter by completed status
    response = client.get("/api/v1/workflows?status=completed&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # Should have at least the sync run
    completed_runs = [item for item in data["items"] if item["status"] == "completed"]
    assert len(completed_runs) >= 1
    
    # Cancel the async run
    cancel_resp = client.post(f"/api/v1/workflows/{async_run_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200


def test_cancel_workflow_lifecycle(auth_headers):
    """Test complete workflow cancellation lifecycle."""
    # Start async workflow
    start_resp = client.post("/api/v1/workflows/test-lifecycle/start", headers=auth_headers)
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]
    
    # Cancel it
    cancel_resp = client.post(f"/api/v1/workflows/{run_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.json()
    assert cancel_data["run_id"] == run_id
    assert cancel_data["status"] == "cancelled"
    
    # Verify status shows cancelled
    status_resp = client.get(f"/api/v1/workflows/{run_id}/status", headers=auth_headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "cancelled"
    
    # Try to cancel again (should fail - already terminal)
    cancel_again_resp = client.post(f"/api/v1/workflows/{run_id}/cancel", headers=auth_headers)
    assert cancel_again_resp.status_code == 400
    assert "already terminal" in cancel_again_resp.json()["detail"]


def test_cancel_nonexistent_workflow(auth_headers):
    """Test cancelling a workflow that doesn't exist."""
    response = client.post("/api/v1/workflows/nonexistent-run/cancel", headers=auth_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_resume_workflow_already_completed(auth_headers):
    """Test resuming a workflow that's already completed."""
    # Start sync workflow (completes immediately)
    start_resp = client.post("/api/v1/workflows/test-lifecycle/start?sync=1", headers=auth_headers)
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]
    
    # Try to resume completed workflow
    resume_resp = client.post(f"/api/v1/workflows/{run_id}/resume", headers=auth_headers)
    # Should either succeed with "already completed" message or return 400
    assert resume_resp.status_code in [200, 400]
    if resume_resp.status_code == 200:
        assert "completed" in resume_resp.json().get("message", "").lower()


def test_invalid_status_filter(auth_headers):
    """Test list endpoint with invalid status filter."""
    response = client.get("/api/v1/workflows?status=invalid_status", headers=auth_headers)
    assert response.status_code == 400
    assert "Invalid status filter" in response.json()["detail"]


def test_workflow_status_includes_safety_issues(auth_headers):
    """Test that workflow status includes safety_issues array."""
    # Start sync workflow
    start_resp = client.post("/api/v1/workflows/test-lifecycle/start?sync=1", headers=auth_headers)
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]
    
    # Get status
    status_resp = client.get(f"/api/v1/workflows/{run_id}/status", headers=auth_headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    
    # Should include safety_issues array (may be empty)
    assert "safety_issues" in status_data
    assert isinstance(status_data["safety_issues"], list)


def test_list_workflow_large_limit_boundary(auth_headers):
    """Test list endpoint respects maximum limit."""
    response = client.get("/api/v1/workflows?limit=250", headers=auth_headers)
    assert response.status_code == 422  # Should reject limit > 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
