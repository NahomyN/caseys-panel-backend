import pytest
import asyncio
from app.agents.stage_a import Agent6
from app.schemas.base import AgentInput


def test_orders_vte_rule():
    """Test VTE prophylaxis rule for immobile patients."""
    
    # Test case 1: Immobile patient without VTE prophylaxis should trigger issue
    input_immobile_no_vte = AgentInput(
        patient_id="test_patient_vte",
        raw_text_refs=["Patient is bedbound", "chest pain"],
        context_flags={"immobile": True}
    )
    
    async def run_test_missing_vte():
        agent = Agent6()
        # Temporarily modify the orders to not include VTE prophylaxis
        original_process = agent.process
        
        async def mock_process_no_vte(input_data):
            await asyncio.sleep(0.1)
            
            issues = []
            patient_immobile = agent._check_patient_immobile(input_data)
            orders_text = "EKG Chest X-ray CBC BMP Troponin Continuous cardiac monitoring IV access O2 if needed Fall precautions"  # No VTE
            
            if patient_immobile and not agent._has_vte_prophylaxis(orders_text):
                issues.append("VTE prophylaxis missing.")
            
            from app.schemas.agents import Agent6Output
            result = Agent6Output(
                content_md="# Initial Orders\n\n**Diagnostics:**\n- EKG\n- Chest X-ray\n\n**Management:**\n- Continuous cardiac monitoring\n- IV access",
                diagnostics=["EKG", "Chest X-ray", "CBC", "BMP", "Troponin"],
                management=["Continuous cardiac monitoring", "IV access", "O2 if needed"],
                consults=["Cardiology if indicated"],
                followups=["Serial troponins"],
                misc=["Fall precautions"]  # No VTE prophylaxis
            )
            
            if issues:
                result.flags["issues"] = issues
                
            return result
        
        agent.process = mock_process_no_vte
        result = await agent.process(input_immobile_no_vte)
        return result
    
    result = asyncio.run(run_test_missing_vte())
    
    # Verify issue was raised
    assert "issues" in result.flags
    assert "VTE prophylaxis missing." in result.flags["issues"]
    
    # Test case 2: Immobile patient WITH VTE prophylaxis should NOT trigger issue
    input_immobile_with_vte = AgentInput(
        patient_id="test_patient_vte_ok",
        raw_text_refs=["Patient is bedbound", "chest pain"],
        context_flags={"immobile": True}
    )
    
    async def run_test_with_vte():
        agent = Agent6()
        result = await agent.process(input_immobile_with_vte)
        return result
    
    result_with_vte = asyncio.run(run_test_with_vte())
    
    # Should have VTE prophylaxis in misc orders (default behavior)
    assert "VTE prophylaxis" in " ".join(result_with_vte.misc)
    # Should NOT have issues flag or should be empty
    assert "issues" not in result_with_vte.flags or not result_with_vte.flags.get("issues", [])
    
    # Test case 3: Mobile patient should NOT trigger issue
    input_mobile = AgentInput(
        patient_id="test_patient_mobile",
        raw_text_refs=["Patient ambulating", "chest pain"],
        context_flags={}
    )
    
    async def run_test_mobile():
        agent = Agent6()
        result = await agent.process(input_mobile)
        return result
    
    result_mobile = asyncio.run(run_test_mobile())
    
    # Should NOT have VTE issue
    assert "issues" not in result_mobile.flags or "VTE prophylaxis missing." not in result_mobile.flags.get("issues", [])


if __name__ == "__main__":
    test_orders_vte_rule()
    print("✓ VTE rule tests passed")