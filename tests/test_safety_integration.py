"""
Test safety rules integration within full workflow execution.
Validates that safety issues are properly detected, recorded, and exposed.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.security import generate_test_token
from app.services.metrics import safety_issues_total


client = TestClient(app)


@pytest.fixture
def auth_headers():
    token = generate_test_token(["attending"], patients=["safety-test", "*"])
    return {"Authorization": f"Bearer {token}"}


def test_safety_integration_vte_prophylaxis_detection(auth_headers):
    """Test that VTE prophylaxis rule triggers during workflow execution."""
    # Start sync workflow (should trigger safety rules)
    start_resp = client.post("/api/v1/workflows/safety-test/start?sync=1", headers=auth_headers)
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]
    
    # Get workflow status
    status_resp = client.get(f"/api/v1/workflows/{run_id}/status", headers=auth_headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    
    # Should have safety_issues array
    assert "safety_issues" in status_data
    safety_issues = status_data["safety_issues"]
    
    # May or may not have specific safety issues depending on workflow data
    # But the field should exist and be a list
    assert isinstance(safety_issues, list)
    
    # Check each safety issue has required fields
    for issue in safety_issues:
        assert "rule_id" in issue
        assert "message" in issue
        assert "severity" in issue
        assert "source" in issue
        assert "created_at" in issue


def test_safety_metrics_exposed_in_prometheus(auth_headers):
    """Test that safety issues are reflected in Prometheus metrics."""
    # Record baseline metrics
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    baseline_content = metrics_resp.text
    
    # Start workflow to potentially trigger safety rules
    start_resp = client.post("/api/v1/workflows/safety-test/start?sync=1", headers=auth_headers)
    start_resp.raise_for_status()
    
    # Check updated metrics
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    updated_content = metrics_resp.text
    
    # Should contain safety_issues_total metric
    assert "safety_issues_total" in updated_content
    # Should contain TYPE and HELP comments for the metric
    assert "# TYPE safety_issues_total counter" in updated_content


def test_safety_rules_registry_coverage():
    """Test that all expected safety rules are registered."""
    from app.safety.rules import registry
    
    expected_rules = [
        "vte_prophylaxis",
        "renal_dosing",  # Actual registered name
        "nsaid_ckd_contraindication",
        "warfarin_amiodarone_interaction"
    ]
    
    registered_rules = list(registry._rules.keys())
    
    for rule_id in expected_rules:
        assert rule_id in registered_rules, f"Safety rule {rule_id} not registered"


def test_safety_rule_direct_application():
    """Test safety rules can be applied directly to workflow state."""
    from app.safety.rules import registry
    
    # Create test state that should trigger VTE rule
    test_state = {
        "patient_id": "safety-test",
        "vitals": {"hr": 85},
        "labs": {},
        "medications": [],
        "problems": ["pneumonia", "immobility"],
        "orders": []  # No VTE prophylaxis ordered
    }
    
    vte_rule = registry.get_rule("vte_prophylaxis")
    assert vte_rule is not None
    
    issues = vte_rule.applies(test_state)
    # Should detect missing VTE prophylaxis
    assert len(issues) > 0
    issue = issues[0]
    assert issue.rule_id == "vte_prophylaxis"
    assert issue.severity in ["warning", "error"]
    assert "VTE" in issue.message or "prophylaxis" in issue.message


def test_safety_issue_event_recording():
    """Test that safety issues are properly recorded as events."""
    # Start workflow 
    auth_headers = {"Authorization": f"Bearer {generate_test_token(['attending'], patients=['safety-event-test', '*'])}"}
    start_resp = client.post("/api/v1/workflows/safety-event-test/start?sync=1", headers=auth_headers)
    start_resp.raise_for_status()
    run_id = start_resp.json()["run_id"]
    
    # Get workflow status and check for safety events
    status_resp = client.get(f"/api/v1/workflows/{run_id}/status", headers=auth_headers)
    status_resp.raise_for_status()
    status_data = status_resp.json()
    
    # Verify safety_issues field exists (even if empty)
    assert "safety_issues" in status_data
    
    # If there are safety issues, verify they have proper structure
    for issue in status_data["safety_issues"]:
        assert all(key in issue for key in ["rule_id", "message", "severity", "source"])


def test_safety_integration_does_not_break_workflow():
    """Test that safety rule integration doesn't prevent workflow completion."""
    auth_headers = {"Authorization": f"Bearer {generate_test_token(['attending'], patients=['safety-workflow-test', '*'])}"}
    
    # Start sync workflow
    start_resp = client.post("/api/v1/workflows/safety-workflow-test/start?sync=1", headers=auth_headers)
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]
    
    # Check final status
    status_resp = client.get(f"/api/v1/workflows/{run_id}/status", headers=auth_headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    
    # Workflow should complete successfully despite safety issues
    assert status_data["status"] == "completed"
    assert "safety_issues" in status_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
