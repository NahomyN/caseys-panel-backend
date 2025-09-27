import pytest
import asyncio
from app.agents.stage_b import Agent7
from app.schemas.agents import Agent7Input, Agent2Output
from app.schemas.base import AgentInput


def test_cross_agent_med_coherence():
    """Test cross-agent medication coherence validation."""
    
    # Mock Agent 2 output with reconciled medications
    agent2_output = Agent2Output(
        agent_no=2,
        content_md="# PMH & Medications\n\n**Medications:** lisinopril",
        reconciled_meds=[{"name": "lisinopril", "dose": "10mg", "frequency": "daily"}],
        pmh=["Hypertension"],
        psh=[],
        allergies=[]
    )
    
    # Create Agent 7 input with stage A outputs
    stage_a_outputs = {
        "agent_2": agent2_output
    }
    
    # Test case 1: Plan includes medication NOT in reconciled list
    input_with_unmatched_med = Agent7Input(
        patient_id="test_patient_coherence",
        raw_text_refs=["Patient with hypertension"],
        stage_a_outputs=stage_a_outputs
    )
    
    async def run_test_unmatched():
        agent = Agent7()
        
        # Override the process method to include amlodipine in plan
        original_process = agent.process
        
        async def mock_process_with_amlodipine(input_data):
            await asyncio.sleep(0.1)
            
            problems = [
                {
                    "heading": "Hypertension", 
                    "assessment": "Not well controlled",
                    "plan": ["Continue lisinopril", "Start amlodipine for BP control"]  # amlodipine not in reconciled list
                }
            ]
            
            # Run coherence validation
            issues = []
            coherence_issues = agent._validate_medication_coherence(input_data.stage_a_outputs, problems)
            issues.extend(coherence_issues)
            
            from app.schemas.agents import Agent7Output
            result = Agent7Output(
                content_md="# Assessment & Plan\n\n**Problems:**\n1. Hypertension - add amlodipine",
                one_liner="Hypertension management",
                problems=problems,
                specialist_needed=None,
                pharmacist_needed=False
            )
            
            if issues:
                result.flags["issues"] = issues
                
            return result
        
        agent.process = mock_process_with_amlodipine
        result = await agent.process(input_with_unmatched_med)
        return result
    
    result = asyncio.run(run_test_unmatched())
    
    # Should have coherence issue for amlodipine
    assert "issues" in result.flags
    issues = result.flags["issues"]
    assert any("amlodipine" in issue and "not in reconciled list" in issue for issue in issues)
    
    # Test case 2: Plan includes only medications in reconciled list
    async def run_test_matched():
        agent = Agent7()
        
        async def mock_process_with_matched_med(input_data):
            await asyncio.sleep(0.1)
            
            problems = [
                {
                    "heading": "Hypertension", 
                    "assessment": "Well controlled",
                    "plan": ["Continue lisinopril", "Monitor BP"]  # lisinopril IS in reconciled list
                }
            ]
            
            # Run coherence validation
            issues = []
            coherence_issues = agent._validate_medication_coherence(input_data.stage_a_outputs, problems)
            issues.extend(coherence_issues)
            
            from app.schemas.agents import Agent7Output
            result = Agent7Output(
                content_md="# Assessment & Plan\n\n**Problems:**\n1. Hypertension - continue current",
                one_liner="Hypertension stable",
                problems=problems,
                specialist_needed=None,
                pharmacist_needed=False
            )
            
            if issues:
                result.flags["issues"] = issues
                
            return result
        
        agent.process = mock_process_with_matched_med
        result = await agent.process(input_with_unmatched_med)
        return result
    
    result_matched = asyncio.run(run_test_matched())
    
    # Should NOT have coherence issues
    assert "issues" not in result_matched.flags or not result_matched.flags.get("issues", [])
    
    # Test case 3: Multiple medications, some matched, some not
    async def run_test_mixed():
        agent = Agent7()
        
        # Mock Agent 2 with multiple meds
        agent2_multiple = Agent2Output(
            agent_no=2,
            content_md="# PMH & Medications",
            reconciled_meds=[
                {"name": "lisinopril", "dose": "10mg", "frequency": "daily"},
                {"name": "metformin", "dose": "500mg", "frequency": "BID"}
            ],
            pmh=["Hypertension", "Diabetes"],
            psh=[],
            allergies=[]
        )
        
        stage_a_multiple = {"agent_2": agent2_multiple}
        input_multiple = Agent7Input(
            patient_id="test_patient_multiple",
            raw_text_refs=["Patient with multiple conditions"],
            stage_a_outputs=stage_a_multiple
        )
        
        async def mock_process_mixed_meds(input_data):
            await asyncio.sleep(0.1)
            
            problems = [
                {
                    "heading": "Diabetes", 
                    "assessment": "Poor control",
                    "plan": ["Continue metformin", "Add atorvastatin for lipids"]  # metformin OK, atorvastatin missing
                }
            ]
            
            # Run coherence validation
            issues = []
            coherence_issues = agent._validate_medication_coherence(input_data.stage_a_outputs, problems)
            issues.extend(coherence_issues)
            
            from app.schemas.agents import Agent7Output
            result = Agent7Output(
                content_md="# Assessment & Plan",
                one_liner="Mixed medication management",
                problems=problems,
                specialist_needed=None,
                pharmacist_needed=False
            )
            
            if issues:
                result.flags["issues"] = issues
                
            return result
        
        agent.process = mock_process_mixed_meds
        result = await agent.process(input_multiple)
        return result
    
    result_mixed = asyncio.run(run_test_mixed())
    
    # Should have issue for atorvastatin but not metformin
    assert "issues" in result_mixed.flags
    issues = result_mixed.flags["issues"]
    assert any("atorvastatin" in issue for issue in issues)
    assert not any("metformin" in issue for issue in issues)


if __name__ == "__main__":
    test_cross_agent_med_coherence()
    print("✓ Cross-agent medication coherence tests passed")