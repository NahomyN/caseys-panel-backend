"""Safety rules engine with registry pattern."""
from dataclasses import dataclass
from typing import List, Dict, Any, Callable
from abc import ABC, abstractmethod


@dataclass
class SafetyIssue:
    """Represents a safety issue found by a rule."""
    rule_id: str
    message: str
    severity: str = "warning"  # warning, error, critical
    node_key: str = ""


class SafetyRule(ABC):
    """Base class for safety rules."""
    
    def __init__(self, rule_id: str, description: str):
        self.rule_id = rule_id
        self.description = description
    
    @abstractmethod
    def applies(self, state: Dict[str, Any]) -> List[SafetyIssue]:
        """Check if this rule applies to the given state and return any issues."""
        pass


class SafetyRuleRegistry:
    """Registry for managing safety rules."""
    
    def __init__(self):
        self._rules: Dict[str, SafetyRule] = {}
    
    def register(self, rule: SafetyRule) -> None:
        """Register a safety rule."""
        self._rules[rule.rule_id] = rule
    
    def get_rule(self, rule_id: str) -> SafetyRule:
        """Get a rule by ID."""
        return self._rules.get(rule_id)
    
    def list_active_rules(self) -> List[Dict[str, str]]:
        """List all active rules."""
        return [
            {"rule_id": rule.rule_id, "description": rule.description}
            for rule in self._rules.values()
        ]
    
    def check_all_rules(self, state: Dict[str, Any], node_key: str = "") -> List[SafetyIssue]:
        """Check all registered rules against the given state."""
        issues = []
        for rule in self._rules.values():
            rule_issues = rule.applies(state)
            for issue in rule_issues:
                if not issue.node_key:
                    issue.node_key = node_key
            issues.extend(rule_issues)
        return issues


# Global registry instance
registry = SafetyRuleRegistry()


def register_rule(rule_class: type) -> Callable:
    """Decorator to register a safety rule."""
    def wrapper(*args, **kwargs):
        rule_instance = rule_class(*args, **kwargs)
        registry.register(rule_instance)
        return rule_instance
    return wrapper


# Define specific safety rules

class VTEProphylaxisRule(SafetyRule):
    """VTE prophylaxis safety rule."""
    
    def __init__(self):
        super().__init__("vte_prophylaxis", "VTE prophylaxis assessment for high-risk patients")
    
    def applies(self, state: Dict[str, Any]) -> List[SafetyIssue]:
        issues = []
        
        # Check both patient.conditions and top-level problems fields
        patient = state.get("patient", {})
        conditions = patient.get("conditions", [])
        problems = state.get("problems", [])
        all_conditions = conditions + problems
        
        # VTE risk factors
        surgical_risk = any(risk in all_conditions for risk in ["surgery_planned", "surgery", "surgical"])
        medical_risk = any(risk in all_conditions for risk in ["pneumonia", "immobility", "cancer", "heart_failure"])
        
        # Check if already on anticoagulation
        medications = state.get("medications", [])
        orders = state.get("orders", [])
        all_meds = medications + orders
        has_anticoagulation = any("anticoagul" in med.lower() or "heparin" in med.lower() or "warfarin" in med.lower() 
                                for med in all_meds)
        
        if (surgical_risk or medical_risk) and not has_anticoagulation:
            risk_type = "surgical" if surgical_risk else "medical"
            issues.append(SafetyIssue(
                rule_id=self.rule_id,
                message=f"VTE prophylaxis should be considered for {risk_type} patient with risk factors",
                severity="warning"
            ))
        return issues


class RenalDosingRule(SafetyRule):
    """Renal dosing adjustment rule."""
    
    def __init__(self):
        super().__init__("renal_dosing", "Renal dosing adjustment for medications")
    
    def applies(self, state: Dict[str, Any]) -> List[SafetyIssue]:
        issues = []
        patient = state.get("patient", {})
        labs = state.get("labs", {})
        
        creatinine = labs.get("creatinine")
        if creatinine and float(creatinine) > 1.5:
            for med in state.get("medications", []):
                if any(drug in med.lower() for drug in ["metformin", "gabapentin", "atenolol"]):
                    issues.append(SafetyIssue(
                        rule_id=self.rule_id,
                        message=f"Consider renal dose adjustment for {med} (Cr: {creatinine})",
                        severity="warning"
                    ))
        return issues


class NSAIDContraindicationRule(SafetyRule):
    """NSAID contraindication in CKD."""
    
    def __init__(self):
        super().__init__("nsaid_ckd_contraindication", "NSAID contraindication in chronic kidney disease")
    
    def applies(self, state: Dict[str, Any]) -> List[SafetyIssue]:
        issues = []
        patient = state.get("patient", {})
        conditions = patient.get("conditions", [])
        
        has_ckd = "ckd" in [c.lower() for c in conditions]
        nsaid_ordered = any("nsaid" in order.lower() for order in state.get("orders", []))
        
        if has_ckd and nsaid_ordered:
            issues.append(SafetyIssue(
                rule_id=self.rule_id,
                message="NSAID order flagged in CKD",
                severity="error"
            ))
        return issues


class DrugInteractionRule(SafetyRule):
    """Drug interaction detection."""
    
    def __init__(self):
        super().__init__("warfarin_amiodarone_interaction", "Warfarin and amiodarone interaction")
    
    def applies(self, state: Dict[str, Any]) -> List[SafetyIssue]:
        issues = []
        medications = [med.lower() for med in state.get("medications", [])]
        plan_medications = [med.lower() for med in state.get("plan", {}).get("medications", [])]
        all_meds = medications + plan_medications
        
        has_warfarin = any("warfarin" in med for med in all_meds)
        has_amiodarone = any("amiodarone" in med for med in all_meds)
        
        if has_warfarin and has_amiodarone:
            issues.append(SafetyIssue(
                rule_id=self.rule_id,
                message="Monitor INR closely (warfarin + amiodarone)",
                severity="warning"
            ))
        return issues


# Register default rules
registry.register(VTEProphylaxisRule())
registry.register(RenalDosingRule())
registry.register(NSAIDContraindicationRule())
registry.register(DrugInteractionRule())


def list_active_rules() -> List[Dict[str, str]]:
    """Get list of all active safety rules."""
    return registry.list_active_rules()


def check_safety_rules(state: Dict[str, Any], node_key: str = "") -> List[SafetyIssue]:
    """Check all safety rules against the given state."""
    return registry.check_all_rules(state, node_key)