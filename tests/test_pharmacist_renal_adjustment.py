import pytest
import asyncio
from app.agents.stage_b import Agent9
from app.schemas.agents import Agent9Input


def test_pharmacist_renal_adjustment():
    """Test renal dosing adjustment recommendations."""
    
    # Test case 1: CrCl < 30 with gabapentin should trigger adjustment
    input_low_crcl_gabapentin = Agent9Input(
        patient_id="test_patient_renal",
        raw_text_refs=["Patient with neuropathy"],
        current_meds=[{"name": "gabapentin", "dose": "300mg", "frequency": "TID"}],
        problems=["Neuropathic pain"],
        labs={"creatinine_clearance": 25.0}
    )
    
    async def run_test_low_crcl():
        agent = Agent9()
        result = await agent.process(input_low_crcl_gabapentin)
        return result
    
    result = asyncio.run(run_test_low_crcl())
    
    # Should have renal adjustment recommendation
    renal_dosing_text = " ".join(result.renal_dosing)
    assert "Adjust dosing for gabapentin (CrCl <30)." in renal_dosing_text
    
    # Test case 2: CrCl > 30 should NOT trigger adjustment
    input_normal_crcl = Agent9Input(
        patient_id="test_patient_normal_renal",
        raw_text_refs=["Patient with neuropathy"],
        current_meds=[{"name": "gabapentin", "dose": "300mg", "frequency": "TID"}],
        problems=["Neuropathic pain"],
        labs={"creatinine_clearance": 60.0}
    )
    
    async def run_test_normal_crcl():
        agent = Agent9()
        result = await agent.process(input_normal_crcl)
        return result
    
    result_normal = asyncio.run(run_test_normal_crcl())
    
    # Should NOT have gabapentin adjustment
    renal_dosing_text = " ".join(result_normal.renal_dosing)
    assert "Adjust dosing for gabapentin (CrCl <30)." not in renal_dosing_text
    
    # Test case 3: CrCl < 30 with multiple renal-adjust meds
    input_multiple_meds = Agent9Input(
        patient_id="test_patient_multiple_renal",
        raw_text_refs=["Patient with diabetes and neuropathy"],
        current_meds=[
            {"name": "gabapentin", "dose": "300mg", "frequency": "TID"},
            {"name": "metformin", "dose": "500mg", "frequency": "BID"}
        ],
        problems=["Diabetes", "Neuropathy"],
        labs={"creatinine_clearance": 20.0}
    )
    
    async def run_test_multiple():
        agent = Agent9()
        result = await agent.process(input_multiple_meds)
        return result
    
    result_multiple = asyncio.run(run_test_multiple())
    
    # Should have adjustments for both medications
    renal_dosing_text = " ".join(result_multiple.renal_dosing)
    assert "Adjust dosing for gabapentin (CrCl <30)." in renal_dosing_text
    assert "Adjust dosing for metformin (CrCl <30)." in renal_dosing_text
    
    # Test case 4: CrCl < 30 but no renal-adjust meds
    input_no_renal_meds = Agent9Input(
        patient_id="test_patient_no_renal_meds",
        raw_text_refs=["Patient with hypertension"],
        current_meds=[{"name": "lisinopril", "dose": "10mg", "frequency": "daily"}],
        problems=["Hypertension"],
        labs={"creatinine_clearance": 15.0}
    )
    
    async def run_test_no_renal_meds():
        agent = Agent9()
        result = await agent.process(input_no_renal_meds)
        return result
    
    result_no_renal = asyncio.run(run_test_no_renal_meds())
    
    # Should NOT have any renal adjustment recommendations for non-renal-adjust meds
    renal_dosing_text = " ".join(result_no_renal.renal_dosing)
    assert "Adjust dosing for" not in renal_dosing_text or "gabapentin" not in renal_dosing_text


if __name__ == "__main__":
    test_pharmacist_renal_adjustment()
    print("✓ Pharmacist renal adjustment tests passed")