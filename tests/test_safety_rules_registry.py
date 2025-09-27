"""Test safety rules registry functionality."""
import pytest
from app.safety.rules import registry, list_active_rules, check_safety_rules, SafetyRule, SafetyIssue


def test_safety_rules_registry_exposes_rules():
    """Test that the registry exposes all registered safety rules."""
    # Get list of active rules
    rules = list_active_rules()
    
    # Should have at least the default rules
    rule_ids = [rule["rule_id"] for rule in rules]
    
    expected_rules = [
        "vte_prophylaxis",
        "renal_dosing", 
        "nsaid_ckd_contraindication",
        "warfarin_amiodarone_interaction"
    ]
    
    for expected_rule in expected_rules:
        assert expected_rule in rule_ids, f"Expected rule {expected_rule} not found"
    
    # Each rule should have a description
    for rule in rules:
        assert "rule_id" in rule
        assert "description" in rule
        assert len(rule["description"]) > 0
    
    print(f"✅ Registry exposes {len(rules)} safety rules")


def test_safety_rules_integration():
    """Test that safety rules can be checked through the registry."""
    # Test state that should trigger multiple rules
    test_state = {
        "patient": {
            "conditions": ["ckd", "surgery_planned"]
        },
        "orders": ["NSAID ibuprofen 400mg"],
        "medications": ["warfarin 5mg"],
        "plan": {
            "medications": ["amiodarone 200mg"]
        },
        "labs": {
            "creatinine": "2.1"
        }
    }
    
    # Check all rules
    issues = check_safety_rules(test_state, "agent_6")
    
    # Should find multiple issues
    assert len(issues) > 0
    
    # Check that issues have proper structure
    for issue in issues:
        assert hasattr(issue, 'rule_id')
        assert hasattr(issue, 'message')
        assert hasattr(issue, 'severity')
        assert hasattr(issue, 'node_key')
        assert issue.node_key == "agent_6"
    
    # Should include NSAID contraindication
    nsaid_issues = [i for i in issues if i.rule_id == "nsaid_ckd_contraindication"]
    assert len(nsaid_issues) == 1
    
    # Should include drug interaction
    interaction_issues = [i for i in issues if i.rule_id == "warfarin_amiodarone_interaction"]
    assert len(interaction_issues) == 1
    
    print(f"✅ Found {len(issues)} safety issues through registry")


def test_custom_rule_registration():
    """Test that custom rules can be registered and work."""
    
    class TestCustomRule(SafetyRule):
        def __init__(self):
            super().__init__("test_custom", "Test custom rule")
        
        def applies(self, state):
            if state.get("test_flag"):
                return [SafetyIssue(
                    rule_id=self.rule_id,
                    message="Test flag detected",
                    severity="info"
                )]
            return []
    
    # Register the custom rule
    custom_rule = TestCustomRule()
    registry.register(custom_rule)
    
    try:
        # Test that it's now in the list
        rules = list_active_rules()
        rule_ids = [rule["rule_id"] for rule in rules]
        assert "test_custom" in rule_ids
        
        # Test that it's triggered
        test_state = {"test_flag": True}
        issues = check_safety_rules(test_state)
        
        custom_issues = [i for i in issues if i.rule_id == "test_custom"]
        assert len(custom_issues) == 1
        assert custom_issues[0].message == "Test flag detected"
        
        print("✅ Custom rule registration and execution works")
        
    finally:
        # Clean up - remove the test rule (in real use, rules persist)
        if "test_custom" in registry._rules:
            del registry._rules["test_custom"]


if __name__ == "__main__":
    test_safety_rules_registry_exposes_rules()
    test_safety_rules_integration()
    test_custom_rule_registration()