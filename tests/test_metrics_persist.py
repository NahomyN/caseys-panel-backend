import pytest
import asyncio
from app.services.checkpointer import checkpointer
from app.services.database import SessionLocal, engine
from app.services.models import Base, RunNodeMetrics
from app.graph.workflow import create_workflow, WorkflowState


def test_metrics_persist_and_idempotent():
    """Test that node metrics are persisted and that persistence is idempotent."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    # Create a test run
    run_id = checkpointer.create_run_id("test_patient_123")
    
    # Sample metrics data
    test_metrics = {
        "attempts": 2,
        "retries": 1,
        "duration_ms": 1500.5,
        "fallback_used": False
    }
    
    # Persist metrics first time
    checkpointer.persist_node_metrics(run_id, "agent_1", "completed", test_metrics)
    
    # Verify metrics were persisted
    persisted = checkpointer.get_persisted_metrics(run_id, "agent_1")
    assert len(persisted) == 1
    
    pm = persisted[0]
    assert pm["node_key"] == "agent_1"
    assert pm["status"] == "completed" 
    assert pm["attempts"] == 2
    assert pm["retries"] == 1
    assert pm["success_duration_ms"] == 1500.5
    assert pm["failure_duration_ms"] is None
    assert pm["fallback_used"] is False
    
    # Try to persist same metrics again (should be idempotent)
    checkpointer.persist_node_metrics(run_id, "agent_1", "completed", test_metrics)
    
    # Verify still only one record
    persisted_after = checkpointer.get_persisted_metrics(run_id, "agent_1")
    assert len(persisted_after) == 1
    
    # Test failed status
    fail_metrics = {
        "attempts": 3,
        "retries": 2,
        "duration_ms": 2000.0,
        "fallback_used": True
    }
    checkpointer.persist_node_metrics(run_id, "agent_2", "failed", fail_metrics)
    
    failed_metrics = checkpointer.get_persisted_metrics(run_id, "agent_2")
    assert len(failed_metrics) == 1
    fm = failed_metrics[0]
    assert fm["status"] == "failed"
    assert fm["success_duration_ms"] is None
    assert fm["failure_duration_ms"] == 2000.0
    assert fm["fallback_used"] is True


if __name__ == "__main__":
    test_metrics_persist_and_idempotent()
    print("✓ Metrics persistence test passed")