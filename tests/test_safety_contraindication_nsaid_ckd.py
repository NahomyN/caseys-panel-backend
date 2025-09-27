"""Test NSAID contraindication safety rule."""
import pytest
from app.safety.rules import NSAIDContraindicationRule


def test_safety_contraindication_nsaid_ckd():
    """Test that NSAID contraindication is flagged for CKD patients."""
    rule = NSAIDContraindicationRule()
    
    # Test case 1: CKD patient with NSAID order - should flag
    state_with_issue = {
        "patient": {
            "conditions": ["diabetes", "ckd", "hypertension"]
        },
        "orders": ["NSAID ibuprofen 400mg", "lisinopril 10mg"]
    }
    
    issues = rule.applies(state_with_issue)
    assert len(issues) == 1
    assert issues[0].rule_id == "nsaid_ckd_contraindication"
    assert "NSAID order flagged in CKD" in issues[0].message
    assert issues[0].severity == "error"
    
    # Test case 2: CKD patient without NSAID - no issue
    state_no_nsaid = {
        "patient": {
            "conditions": ["diabetes", "ckd", "hypertension"]
        },
        "orders": ["acetaminophen 500mg", "lisinopril 10mg"]
    }
    
    issues = rule.applies(state_no_nsaid)
    assert len(issues) == 0
    
    # Test case 3: Non-CKD patient with NSAID - no issue
    state_no_ckd = {
        "patient": {
            "conditions": ["diabetes", "hypertension"]
        },
        "orders": ["NSAID ibuprofen 400mg", "lisinopril 10mg"]
    }
    
    issues = rule.applies(state_no_ckd)
    assert len(issues) == 0
    
    # Test case 4: Case insensitive detection
    state_case_insensitive = {
        "patient": {
            "conditions": ["CKD"]
        },
        "orders": ["nsaid naproxen 200mg"]
    }
    
    issues = rule.applies(state_case_insensitive)
    assert len(issues) == 1
    
    print("✅ NSAID contraindication rule working correctly")


if __name__ == "__main__":
    test_safety_contraindication_nsaid_ckd()