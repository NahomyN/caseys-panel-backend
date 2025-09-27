"""Test Prometheus metrics endpoint functionality."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.metrics import (
    runs_started_total, runs_completed_total, record_run_started, 
    record_run_completed, record_fallback_used, record_safety_issue
)


client = TestClient(app)


def test_metrics_endpoint_basic():
    """Test that metrics endpoint is accessible and returns Prometheus format."""
    # Test that metrics endpoint exists
    response = client.get("/metrics")
    assert response.status_code == 200
    
    # Should return prometheus content type
    assert "text/plain" in response.headers.get("content-type", "")
    
    # Should contain at least runs_started_total metric
    content = response.text
    assert "runs_started_total" in content
    
    # Should be valid prometheus format (contains TYPE and HELP comments)
    assert "# TYPE" in content
    assert "# HELP" in content
    
    print("✅ Metrics endpoint accessible and returns Prometheus format")


def test_metrics_instrumentation():
    """Test that metrics are properly instrumented."""
    # Get baseline metrics
    response = client.get("/metrics")
    baseline_content = response.text
    
    # Record some metrics
    record_run_started()
    record_run_started()
    record_run_completed("completed")
    record_run_completed("failed")
    record_fallback_used("agent_1")
    record_safety_issue("vte_prophylaxis", "warning")
    
    # Get updated metrics
    response = client.get("/metrics")
    assert response.status_code == 200
    updated_content = response.text
    
    # Should show updated counts (at least runs_started should be >= 2)
    lines = updated_content.split('\n')
    for line in lines:
        if line.startswith('runs_started_total') and not line.startswith('#'):
            count = float(line.split()[-1])
            assert count >= 2, f"runs_started_total should be at least 2, got {count}"
            break
    else:
        assert False, "runs_started_total metric not found in output"
    
    # Should contain completed and failed runs
    assert 'runs_completed_total{status="completed"}' in updated_content
    assert 'runs_completed_total{status="failed"}' in updated_content
    
    # Should contain fallback and safety metrics
    assert 'fallbacks_total{node_key="agent_1"}' in updated_content
    assert 'safety_issues_total{rule_id="vte_prophylaxis",severity="warning"}' in updated_content
    
    print("✅ Metrics instrumentation working correctly")


def test_metrics_workflow_integration():
    """Test that workflow operations are reflected in metrics."""
    from app.auth.security import generate_test_token
    
    # Get baseline
    response = client.get("/metrics")
    baseline_content = response.text
    
    # Extract baseline runs_started count
    baseline_started = 0
    for line in baseline_content.split('\n'):
        if line.startswith('runs_started_total') and not line.startswith('#'):
            baseline_started = float(line.split()[-1])
            break
    
    # Start a workflow (should increment runs_started)
    token = generate_test_token(["attending"])
    headers = {"Authorization": f"Bearer {token}"}
    
    response = client.post("/api/v1/workflows/metrics_test_patient/start", headers=headers)
    # Don't assert success here since workflow might fail, we just want to test metrics
    
    # Check metrics again
    response = client.get("/metrics")
    assert response.status_code == 200
    updated_content = response.text
    
    # Should show incremented runs_started
    updated_started = 0
    for line in updated_content.split('\n'):
        if line.startswith('runs_started_total') and not line.startswith('#'):
            updated_started = float(line.split()[-1])
            break
    
    assert updated_started > baseline_started, "runs_started should have incremented"
    
    print(f"✅ Workflow integration metrics: baseline {baseline_started}, updated {updated_started}")


def test_metrics_histogram_buckets():
    """Test that histogram metrics have proper buckets."""
    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.text
    
    # Should contain histogram buckets for node_duration_ms
    expected_buckets = ["50.0", "100.0", "250.0", "500.0", "1000.0", "2000.0", "5000.0", "10000.0", "+Inf"]
    
    for bucket in expected_buckets:
        assert f'node_duration_ms_bucket{{le="{bucket}"' in content or f'le="{bucket}"' in content, f"Missing bucket {bucket}"
    
    print("✅ Histogram buckets configured correctly")


def test_metrics_labels():
    """Test that metrics with labels work correctly."""
    # Record some labeled metrics
    record_fallback_used("agent_1")
    record_fallback_used("agent_7")
    record_safety_issue("nsaid_ckd_contraindication", "error")
    record_safety_issue("warfarin_amiodarone_interaction", "warning")
    
    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.text
    
    # Should contain different label values
    assert 'fallbacks_total{node_key="agent_1"}' in content
    assert 'fallbacks_total{node_key="agent_7"}' in content
    assert 'safety_issues_total{rule_id="nsaid_ckd_contraindication",severity="error"}' in content
    assert 'safety_issues_total{rule_id="warfarin_amiodarone_interaction",severity="warning"}' in content
    
    print("✅ Metrics labels working correctly")


if __name__ == "__main__":
    test_metrics_endpoint_basic()
    test_metrics_instrumentation()
    test_metrics_workflow_integration()
    test_metrics_histogram_buckets()
    test_metrics_labels()