"""Test model usage persistence and cost calculation."""
import pytest
from app.services.database import SessionLocal
from app.services.models import RunModelUsage, WorkflowRun, WorkflowStatus
from app.services.telemetry import record_model_usage, RATE_MAP


def test_model_usage_persistence():
    """Test that model usage is recorded with correct cost calculation."""
    db = SessionLocal()
    
    try:
        # Create a test workflow run
        run_id = "test_run_usage_123"
        workflow_run = WorkflowRun(
            run_id=run_id,
            patient_id="test_patient_usage",
            status=WorkflowStatus.RUNNING
        )
        db.add(workflow_run)
        db.commit()
        
        # Test usage data
        usage_dict = {
            "provider": "test-provider",
            "model_name": "generic-primary",
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        
        # Record model usage
        record_model_usage(run_id, "agent_1", usage_dict, db)
        
        # Verify the record was created
        usage_record = db.query(RunModelUsage).filter_by(run_id=run_id).first()
        assert usage_record is not None
        assert usage_record.node_key == "agent_1"
        assert usage_record.provider == "test-provider"
        assert usage_record.model_name == "generic-primary"
        assert usage_record.prompt_tokens == 100
        assert usage_record.completion_tokens == 50
        assert usage_record.total_tokens == 150
        
        # Verify cost calculation
        expected_cost = 150 * RATE_MAP["generic-primary"]
        assert float(usage_record.estimated_cost_usd) == expected_cost
        
        print(f"✅ Model usage recorded with cost: ${usage_record.estimated_cost_usd}")
        
    finally:
        # Cleanup
        db.query(RunModelUsage).filter_by(run_id=run_id).delete()
        db.query(WorkflowRun).filter_by(run_id=run_id).delete()
        db.commit()
        db.close()


def test_model_usage_fallback_rate():
    """Test that fallback model uses different rate."""
    db = SessionLocal()
    
    try:
        # Create a test workflow run
        run_id = "test_run_fallback_456"
        workflow_run = WorkflowRun(
            run_id=run_id,
            patient_id="test_patient_fallback",
            status=WorkflowStatus.RUNNING
        )
        db.add(workflow_run)
        db.commit()
        
        # Test fallback usage
        usage_dict = {
            "provider": "fallback-provider",
            "model_name": "generic-fallback",
            "prompt_tokens": 200,
            "completion_tokens": 100,
        }
        
        record_model_usage(run_id, "agent_7", usage_dict, db)
        
        usage_record = db.query(RunModelUsage).filter_by(run_id=run_id).first()
        assert usage_record is not None
        assert usage_record.total_tokens == 300
        
        # Verify fallback rate applied
        expected_cost = 300 * RATE_MAP["generic-fallback"]
        assert float(usage_record.estimated_cost_usd) == expected_cost
        
        print(f"✅ Fallback usage recorded with cost: ${usage_record.estimated_cost_usd}")
        
    finally:
        # Cleanup
        db.query(RunModelUsage).filter_by(run_id=run_id).delete()
        db.query(WorkflowRun).filter_by(run_id=run_id).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    test_model_usage_persistence()
    test_model_usage_fallback_rate()