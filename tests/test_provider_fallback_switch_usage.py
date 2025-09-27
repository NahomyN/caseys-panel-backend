"""Test provider fallback and usage recording."""
import pytest
from app.services.database import SessionLocal
from app.services.models import WorkflowRun, RunModelUsage, WorkflowStatus
from app.providers.base import ProviderFactory, PrimaryProvider, FallbackProvider
from app.services.telemetry import record_model_usage


def test_provider_fallback_switch_records_two_usage_rows():
    """Test that fallback switch records usage for both primary and fallback providers."""
    db = SessionLocal()
    
    try:
        # Create test workflow run
        run_id = "test_fallback_usage_123"
        workflow_run = WorkflowRun(
            run_id=run_id,
            patient_id="test_patient_fallback",
            status=WorkflowStatus.RUNNING
        )
        db.add(workflow_run)
        db.commit()
        
        # Simulate primary provider attempt
        primary_provider = ProviderFactory.get_primary_provider()
        test_input = {"patient_id": "test123", "context": "test scenario"}
        
        primary_output = primary_provider.generate(test_input)
        primary_usage = primary_provider.get_usage()
        
        # Record primary usage
        record_model_usage(
            run_id, 
            "agent_1", 
            {
                "provider": primary_usage.provider,
                "model_name": primary_usage.model_name,
                "prompt_tokens": primary_usage.prompt_tokens,
                "completion_tokens": primary_usage.completion_tokens
            },
            db
        )
        
        # Simulate fallback due to primary failure
        fallback_provider = ProviderFactory.get_fallback_provider()
        fallback_output = fallback_provider.generate(test_input)
        fallback_usage = fallback_provider.get_usage()
        
        # Record fallback usage
        record_model_usage(
            run_id,
            "agent_1",
            {
                "provider": fallback_usage.provider,
                "model_name": fallback_usage.model_name,
                "prompt_tokens": fallback_usage.prompt_tokens,
                "completion_tokens": fallback_usage.completion_tokens
            },
            db
        )
        
        # Verify two separate usage records exist
        usage_records = db.query(RunModelUsage).filter_by(run_id=run_id).all()
        assert len(usage_records) == 2
        
        # Verify primary and fallback records
        primary_records = [r for r in usage_records if r.provider == "primary"]
        fallback_records = [r for r in usage_records if r.provider == "fallback"]
        
        assert len(primary_records) == 1
        assert len(fallback_records) == 1
        
        # Verify different model names
        assert primary_records[0].model_name == "generic-primary"
        assert fallback_records[0].model_name == "generic-fallback"
        
        # Verify different costs (fallback should be cheaper)
        primary_cost = float(primary_records[0].estimated_cost_usd)
        fallback_cost = float(fallback_records[0].estimated_cost_usd)
        assert primary_cost > fallback_cost  # Primary rate is higher
        
        print(f"✅ Recorded usage for both providers - Primary: ${primary_cost:.6f}, Fallback: ${fallback_cost:.6f}")
        
    finally:
        # Cleanup
        db.query(RunModelUsage).filter_by(run_id=run_id).delete()
        db.query(WorkflowRun).filter_by(run_id=run_id).delete()
        db.commit()
        db.close()


def test_provider_deterministic_output():
    """Test that providers return deterministic output for testing."""
    # Test primary provider
    primary = ProviderFactory.get_primary_provider()
    test_input = {"test": "data"}
    
    output1 = primary.generate(test_input)
    output2 = primary.generate(test_input)
    
    # Should have different generation counts but similar structure
    assert "Primary response 1" in output1["output"]
    assert "Primary response 2" in output2["output"]
    assert output1["confidence"] == output2["confidence"]
    
    # Test fallback provider
    fallback = ProviderFactory.get_fallback_provider()
    
    fallback_output1 = fallback.generate(test_input)
    fallback_output2 = fallback.generate(test_input)
    
    assert "Fallback response 1" in fallback_output1["output"]
    assert "Fallback response 2" in fallback_output2["output"]
    assert fallback_output1["confidence"] < output1["confidence"]  # Lower confidence
    
    print("✅ Providers generate deterministic output for testing")


def test_usage_metadata_accuracy():
    """Test that usage metadata is accurate and consistent."""
    primary = ProviderFactory.get_primary_provider()
    
    # Generate with different input sizes
    small_input = {"key": "value"}
    large_input = {"key": "very long value " * 50}
    
    primary.generate(small_input)
    small_usage = primary.get_usage()
    
    primary.generate(large_input)
    large_usage = primary.get_usage()
    
    # Larger input should result in more tokens
    assert large_usage.prompt_tokens > small_usage.prompt_tokens
    assert large_usage.total_tokens > small_usage.total_tokens
    
    # Usage should have correct provider info
    assert small_usage.provider == "primary"
    assert small_usage.model_name == "generic-primary"
    
    print("✅ Usage metadata scales with input size correctly")


if __name__ == "__main__":
    test_provider_fallback_switch_records_two_usage_rows()
    test_provider_deterministic_output()
    test_usage_metadata_accuracy()