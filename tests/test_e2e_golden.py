import pytest
import asyncio
from app.graph.workflow import create_workflow, WorkflowState
from app.services.checkpointer import PostgresCheckpointer
from unittest.mock import Mock, patch
import uuid


@pytest.mark.asyncio
async def test_golden_workflow_e2e():
    """
    Golden E2E test that runs a fake input through the complete A->B->C workflow
    with stubbed LLM calls to ensure deterministic outputs.
    """
    
    patient_id = f"test_patient_{uuid.uuid4().hex[:8]}"
    run_id = f"run_{patient_id}_{uuid.uuid4().hex[:8]}"
    
    mock_checkpointer = Mock(spec=PostgresCheckpointer)
    mock_checkpointer.save_checkpoint.return_value = "checkpoint_id"
    mock_checkpointer.create_run_id.return_value = run_id
    
    with patch('app.services.checkpointer.checkpointer', mock_checkpointer):  # unchanged path still valid for module attribute
        
        workflow = create_workflow()
        app = workflow.compile()
        
        initial_state = WorkflowState(
            run_id=run_id,
            patient_id=patient_id,
            raw_text_refs=["ED_NOTE_001"],
            vitals={
                "temperature": 98.6,
                "heart_rate": 88,
                "blood_pressure": "140/90",
                "respiratory_rate": 16,
                "oxygen_saturation": 95
            },
            labs={
                "glucose": 120,
                "creatinine": 1.1,
                "troponin": 0.02
            },
            context_flags={
                "chest_pain": True,
                "shortness_of_breath": False,
                "urgent": True
            }
        )
        
        final_state = await app.ainvoke(initial_state)
        # LangGraph may return an AddableValuesDict mapping instead of the original pydantic model
        if not hasattr(final_state, 'run_id') and isinstance(final_state, dict):
            final_state = WorkflowState(**final_state)

        assert final_state.run_id == run_id
        assert final_state.patient_id == patient_id
        
        assert len(final_state.stage_a_outputs) == 6
        for i in range(1, 7):
            agent_key = f"agent_{i}"
            assert agent_key in final_state.stage_a_outputs
            assert final_state.stage_a_outputs[agent_key].agent_no == i
            assert len(final_state.stage_a_outputs[agent_key].content_md) > 0
        
        assert "agent_7" in final_state.stage_b_outputs
        orchestrator_output = final_state.stage_b_outputs["agent_7"]
        assert orchestrator_output.agent_no == 7
        assert len(orchestrator_output.one_liner) > 0
        assert len(orchestrator_output.problems) > 0
        
        if orchestrator_output.specialist_needed:
            assert "agent_8" in final_state.stage_b_outputs
            specialist_output = final_state.stage_b_outputs["agent_8"]
            assert specialist_output.agent_no == 8
            assert specialist_output.specialty == orchestrator_output.specialist_needed
        
        if orchestrator_output.pharmacist_needed:
            assert "agent_9" in final_state.stage_b_outputs
            pharmacist_output = final_state.stage_b_outputs["agent_9"]
            assert pharmacist_output.agent_no == 9
        
        assert "agent_10" in final_state.stage_c_outputs
        compiler_output = final_state.stage_c_outputs["agent_10"]
        assert compiler_output.agent_no == 10
        assert len(compiler_output.final_note) > 0
        assert len(compiler_output.billing_attestation) > 0
        
        expected_checkpoints = ["agent_1", "agent_2", "agent_3", "agent_4", "agent_5", "agent_6", "agent_7"]
        if "agent_8" in final_state.stage_b_outputs:
            expected_checkpoints.append("agent_8")
        if "agent_9" in final_state.stage_b_outputs:
            expected_checkpoints.append("agent_9")
        expected_checkpoints.append("agent_10")
        
        assert mock_checkpointer.save_checkpoint.call_count >= len(expected_checkpoints)
        
        saved_checkpoints = []
        for call in mock_checkpointer.save_checkpoint.call_args_list:
            args, kwargs = call
            saved_checkpoints.append(args[1])
        
        for expected_checkpoint in expected_checkpoints:
            assert expected_checkpoint in saved_checkpoints
        
        assert len(final_state.errors) == 0, f"Workflow completed with errors: {final_state.errors}"
        
        expected_completed_nodes = [
            "agent_1", "agent_2", "agent_3", "agent_4", "agent_5", "agent_6", 
            "agent_7", "agent_10"
        ]
        if "agent_8" in final_state.stage_b_outputs:
            expected_completed_nodes.append("agent_8")
        if "agent_9" in final_state.stage_b_outputs:
            expected_completed_nodes.append("agent_9")
        
        for node in expected_completed_nodes:
            assert node in final_state.completed_nodes
        
        print(f"✅ Golden E2E test passed!")
        print(f"   - Completed {len(final_state.completed_nodes)} nodes")
        print(f"   - Stage A outputs: {len(final_state.stage_a_outputs)}")
        print(f"   - Stage B outputs: {len(final_state.stage_b_outputs)}")
        print(f"   - Stage C outputs: {len(final_state.stage_c_outputs)}")
        print(f"   - Final note length: {len(compiler_output.final_note)} chars")


@pytest.mark.asyncio 
async def test_workflow_with_errors_and_retries():
    """
    Test workflow behavior when nodes fail and retry logic is triggered.
    """
    from app.agents.base import BaseAgent
    from app.schemas.base import AgentInput, AgentOutput
    
    class FailingAgent(BaseAgent):
        def __init__(self):
            super().__init__(99, "Failing Test Agent")
            self.attempt_count = 0
        
        async def process(self, input_data: AgentInput) -> AgentOutput:
            self.attempt_count += 1
            if self.attempt_count < 3:
                raise Exception(f"Simulated failure attempt {self.attempt_count}")
            return AgentOutput(
                agent_no=99,
                content_md="# Success after retries"
            )
    
    failing_agent = FailingAgent()
    
    input_data = AgentInput(
        patient_id="test_patient",
        raw_text_refs=["test_ref"]
    )
    
    result = await failing_agent.run_with_retry(input_data)
    
    assert result.agent_no == 99
    assert result.content_md == "# Success after retries"
    assert failing_agent.attempt_count == 3
    
    print("✅ Retry logic test passed!")


@pytest.mark.asyncio
async def test_workflow_max_retries_exceeded():
    """
    Test that workflow properly handles cases where max retries are exceeded.
    """
    from app.agents.base import BaseAgent
    from app.schemas.base import AgentInput
    
    class AlwaysFailingAgent(BaseAgent):
        def __init__(self):
            super().__init__(98, "Always Failing Agent")
            self.attempt_count = 0
        
        async def process(self, input_data: AgentInput):
            self.attempt_count += 1
            raise Exception(f"Always fails - attempt {self.attempt_count}")
    
    failing_agent = AlwaysFailingAgent()
    
    input_data = AgentInput(
        patient_id="test_patient",
        raw_text_refs=["test_ref"]
    )
    
    with pytest.raises(Exception) as exc_info:
        await failing_agent.run_with_retry(input_data)
    
    assert "Always fails - attempt 4" in str(exc_info.value)
    assert failing_agent.attempt_count == 4
    
    print("✅ Max retries exceeded test passed!")


if __name__ == "__main__":
    asyncio.run(test_golden_workflow_e2e())