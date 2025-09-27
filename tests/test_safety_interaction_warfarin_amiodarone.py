"""Test drug interaction safety rule."""
import pytest
from app.safety.rules import DrugInteractionRule


def test_safety_interaction_warfarin_amiodarone():
    """Test that warfarin-amiodarone interaction is detected."""
    rule = DrugInteractionRule()
    
    # Test case 1: Both medications present - should flag
    state_with_interaction = {
        "medications": ["warfarin 5mg", "metoprolol 25mg"],
        "plan": {
            "medications": ["amiodarone 200mg", "lisinopril 10mg"]
        }
    }
    
    issues = rule.applies(state_with_interaction)
    assert len(issues) == 1
    assert issues[0].rule_id == "warfarin_amiodarone_interaction"
    assert "Monitor INR closely (warfarin + amiodarone)" in issues[0].message
    assert issues[0].severity == "warning"
    
    # Test case 2: Only warfarin present - no issue
    state_warfarin_only = {
        "medications": ["warfarin 5mg", "metoprolol 25mg"],
        "plan": {
            "medications": ["lisinopril 10mg"]
        }
    }
    
    issues = rule.applies(state_warfarin_only)
    assert len(issues) == 0
    
    # Test case 3: Only amiodarone present - no issue
    state_amiodarone_only = {
        "medications": ["metoprolol 25mg"],
        "plan": {
            "medications": ["amiodarone 200mg", "lisinopril 10mg"]
        }
    }
    
    issues = rule.applies(state_amiodarone_only)
    assert len(issues) == 0
    
    # Test case 4: Both in current medications
    state_both_current = {
        "medications": ["warfarin 5mg", "amiodarone 200mg"],
        "plan": {
            "medications": []
        }
    }
    
    issues = rule.applies(state_both_current)
    assert len(issues) == 1
    
    # Test case 5: Case insensitive detection
    state_case_insensitive = {
        "medications": ["WARFARIN 5mg"],
        "plan": {
            "medications": ["Amiodarone 200mg"]
        }
    }
    
    issues = rule.applies(state_case_insensitive)
    assert len(issues) == 1
    
    print("✅ Warfarin-amiodarone interaction rule working correctly")


if __name__ == "__main__":
    test_safety_interaction_warfarin_amiodarone()