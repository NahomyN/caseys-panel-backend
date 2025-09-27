from .base import BaseAgent
from ..schemas.base import AgentInput
from ..schemas.agents import (
    Agent7Input, Agent7Output, Agent8Input, Agent8Output, 
    Agent9Input, Agent9Output
)
import asyncio
import re


class Agent7(BaseAgent):
    def __init__(self):
        super().__init__(7, "Hospitalist Orchestrator (A&P Reasoner)")
    
    async def process(self, input_data: Agent7Input) -> Agent7Output:
        await asyncio.sleep(0.2)
        
        need_specialist = self._assess_specialist_need(input_data.stage_a_outputs)
        need_pharmacist = self._assess_pharmacist_need(input_data.stage_a_outputs)
        
        problems = [
            {
                "heading": "Chest pain - rule out ACS",
                "assessment": "Atypical presentation but concerning features",
                "plan": ["Serial troponins", "EKG monitoring", "Cardiology consult"]
            },
            {
                "heading": "Hypertension", 
                "assessment": "Well controlled on current regimen",
                "plan": ["Continue lisinopril", "Monitor BP"]
            }
        ]
        
        # Cross-agent medication coherence validation
        issues = []
        coherence_issues = self._validate_medication_coherence(input_data.stage_a_outputs, problems)
        issues.extend(coherence_issues)
        
        result = Agent7Output(
            content_md="# Assessment & Plan\n\n**One-liner:** 65 year old with chest pain, ruling out ACS.\n\n**Problems:**\n1. Chest pain - rule out ACS\n2. Hypertension - continue home medications",
            one_liner="65 year old with chest pain, ruling out ACS",
            problems=problems,
            specialist_needed="cardiology" if need_specialist else None,
            pharmacist_needed=need_pharmacist
        )
        
        if issues:
            result.flags["issues"] = issues
            
        return result
    
    def _assess_specialist_need(self, outputs) -> bool:
        return True
    
    def _assess_pharmacist_need(self, outputs) -> bool:
        return True
    
    def _validate_medication_coherence(self, stage_a_outputs, problems) -> list:
        """Validate that medications in plan exist in reconciled med list."""
        issues = []
        
        # Get reconciled medications from Agent 2
        reconciled_meds = []
        if "agent_2" in stage_a_outputs:
            agent2_output = stage_a_outputs["agent_2"]
            if hasattr(agent2_output, 'reconciled_meds'):
                reconciled_meds = [
                    med.get('name', '').lower() if isinstance(med, dict) else str(med).lower() 
                    for med in agent2_output.reconciled_meds
                ]
        
        # Extract medication names from plan lines
        plan_medications = set()
        for problem in problems:
            plan_lines = problem.get('plan', [])
            for line in plan_lines:
                # Look for medication names in plan text (alphabetic words >= 3 chars)
                words = re.findall(r'\b[A-Za-z]{3,}\b', line)
                for word in words:
                    word_lower = word.lower()
                    # Basic medication name pattern - could be improved
                    if self._looks_like_medication(word_lower):
                        plan_medications.add(word_lower)
        
        # Check coherence
        for med in plan_medications:
            if med not in reconciled_meds:
                issues.append(f"Medication {med} not in reconciled list.")
        
        return issues
    
    def _looks_like_medication(self, word: str) -> bool:
        """Basic heuristic to identify potential medication names."""
        # Known medication patterns/suffixes
        med_patterns = [
            'lisinopril', 'amlodipine', 'metformin', 'gabapentin', 'atorvastatin',
            'hydrochlorothiazide', 'carvedilol', 'omeprazole', 'aspirin'
        ]
        
        # Common medication suffixes
        med_suffixes = ['pril', 'statin', 'olol', 'zide', 'pine', 'in']
        
        # Check if word matches known meds or has med-like suffix
        if word in med_patterns:
            return True
            
        for suffix in med_suffixes:
            if word.endswith(suffix) and len(word) >= 6:  # Avoid false positives
                return True
                
        return False

    async def fallback_process(self, input_data: Agent7Input, error: Exception):  # type: ignore[override]
        # Minimal viable A&P skeleton
        return Agent7Output(
            content_md="# Assessment & Plan\n\n**One-liner:** Fallback summarization.\n\n**Problems:**\n- [Problem POA] [] Supportive care",
            one_liner="Fallback one-liner (insufficient data)",
            problems=[{"heading": "Problem (POA)", "assessment": "Fallback", "plan": ["[] Supportive care"]}],
            specialist_needed=None,
            pharmacist_needed=False
        )


class Agent8(BaseAgent):
    def __init__(self):
        super().__init__(8, "Specialist (Dynamic)")
    
    async def process(self, input_data: Agent8Input) -> Agent8Output:
        await asyncio.sleep(0.15)
        
        specialty_recommendations = {
            "cardiology": "Consider stress testing if troponins negative. DAPT if ACS confirmed.",
            "pulmonology": "CT-PE if high suspicion. Bronchodilators if asthma component.",
            "nephrology": "Check creatinine clearance. Adjust medications for renal function.",
        }
        
        recommendation = specialty_recommendations.get(
            input_data.specialty.lower(), 
            f"Specialty consultation for {input_data.specialty} regarding {input_data.consultation_request}"
        )
        
        return Agent8Output(
            content_md=f"# {input_data.specialty.title()} Consultation\n\n{recommendation}",
            specialty=input_data.specialty,
            recommendations=recommendation,
            ap_additions=[f"[] {input_data.specialty} recommendations as above"]
        )


class Agent9(BaseAgent):
    def __init__(self):
        super().__init__(9, "Clinical Pharmacist")
    
    async def process(self, input_data: Agent9Input) -> Agent9Output:
        await asyncio.sleep(0.1)
        
        # Safety Rule: Renal dosing adjustments
        issues = []
        renal_adjustments = []
        
        creatinine_clearance = self._get_creatinine_clearance(input_data)
        if creatinine_clearance and creatinine_clearance < 30:
            # Check medications that need renal adjustment
            renal_adjust_meds = {'gabapentin', 'metformin', 'enoxaparin'}
            medication_text = self._get_medication_text(input_data)
            
            for med in renal_adjust_meds:
                if med.lower() in medication_text.lower():
                    adjustment_text = f"Adjust dosing for {med} (CrCl <30)."
                    renal_adjustments.append(adjustment_text)
        
        base_renal_dosing = ["Lisinopril appropriate for eGFR >30"]
        base_renal_dosing.extend(renal_adjustments)
        
        result = Agent9Output(
            content_md="# Pharmacy Review\n\n**Medication Safety:** No major concerns with current regimen.\n\n**Recommendations:** Continue current medications with monitoring.",
            med_safety_review="Current medications appropriate for indication and renal function",
            renal_dosing=base_renal_dosing,
            interactions=["No significant drug interactions identified"],
            alternatives=["Consider ARB if ACE intolerant"],
            monitoring=["Monitor potassium and creatinine", "Blood pressure monitoring"]
        )
        
        if issues:
            result.flags["issues"] = issues
            
        return result
    
    def _get_creatinine_clearance(self, input_data: Agent9Input) -> float:
        """Extract creatinine clearance from labs context."""
        if input_data.labs and 'creatinine_clearance' in input_data.labs:
            return float(input_data.labs['creatinine_clearance'])
        return None
    
    def _get_medication_text(self, input_data: Agent9Input) -> str:
        """Get text containing medication information."""
        # Check current medications
        med_names = []
        for med in input_data.current_meds:
            if isinstance(med, dict) and 'name' in med:
                med_names.append(med['name'])
        
        # Also check problems text for medication mentions
        problems_text = " ".join(input_data.problems)
        
        return " ".join(med_names) + " " + problems_text