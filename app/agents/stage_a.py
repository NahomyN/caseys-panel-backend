from .base import BaseAgent
from ..schemas.base import AgentInput
from ..schemas.agents import (
    Agent1Output, Agent2Output, Agent3Output, 
    Agent4Output, Agent5Output, Agent6Output
)
import asyncio


class Agent1(BaseAgent):
    def __init__(self):
        super().__init__(1, "Senior Resident (HPI & ROS)")
    
    async def process(self, input_data: AgentInput) -> Agent1Output:
        await asyncio.sleep(0.1)
        # Simulate potential failure for testing fallback
        if getattr(input_data, '_force_primary_failure', False):
            from .base import TransientAgentError
            raise TransientAgentError("Simulated primary model failure")
            
        return Agent1Output(
            content_md="# HPI & ROS\n\n**HPI:** [Placeholder HPI content]\n\n**ROS:** [Placeholder ROS content]",
            hpi="Placeholder HPI content based on raw text",
            ros_positive=["chest pain", "shortness of breath"],
            ros_negative=["fever", "nausea"],
            differentials=["acute coronary syndrome", "pulmonary embolism"]
        )
    
    async def fallback_process(self, input_data: AgentInput, error) -> Agent1Output:
        """Fallback implementation with simpler/cheaper model or logic."""
        await asyncio.sleep(0.05)  # Faster fallback processing
        return Agent1Output(
            content_md="# HPI & ROS (Fallback)\n\n**HPI:** [Fallback HPI - simpler analysis]\n\n**ROS:** [Basic ROS review]",
            hpi="Fallback HPI with basic template",
            ros_positive=["chest symptoms"],
            ros_negative=["no fever"],
            differentials=["cardiac etiology"]
        )


class Agent2(BaseAgent):
    def __init__(self):
        super().__init__(2, "PMH & Med Rec")
    
    async def process(self, input_data: AgentInput) -> Agent2Output:
        await asyncio.sleep(0.1)
        return Agent2Output(
            content_md="# PMH & Medications\n\n**PMH:** [Placeholder PMH]\n\n**Medications:** [Placeholder med list]",
            reconciled_meds=[{"name": "Lisinopril", "dose": "10mg", "frequency": "daily", "source": "patient"}],
            pmh=["Hypertension", "Diabetes Type 2"],
            psh=["Appendectomy 2015"],
            allergies=[{"allergen": "Penicillin", "reaction": "rash"}]
        )


class Agent3(BaseAgent):
    def __init__(self):
        super().__init__(3, "Social & Functional History")
    
    async def process(self, input_data: AgentInput) -> Agent3Output:
        await asyncio.sleep(0.1)
        return Agent3Output(
            content_md="# Social & Functional History\n\n[Placeholder social history content]",
            social_history="Lives with spouse, retired, no tobacco/alcohol",
            functional_history="Independent in ADLs, walks with walker",
            living_situation="Lives at home with spouse"
        )


class Agent4(BaseAgent):
    def __init__(self):
        super().__init__(4, "Physical Exam")
    
    async def process(self, input_data: AgentInput) -> Agent4Output:
        await asyncio.sleep(0.1)
        return Agent4Output(
            content_md="# Physical Exam\n\n• VS: BP 140/90, HR 88, RR 16, O2 95% RA\n• General: NAD\n• HEENT: PERRL\n• CV: RRR, no murmur\n• Pulm: CTAB\n• Abd: Soft, NT, ND\n• Ext: No edema",
            vitals={"bp": "140/90", "hr": 88, "rr": 16, "o2sat": 95},
            physical_exam=["VS: BP 140/90, HR 88, RR 16, O2 95% RA", "General: NAD", "HEENT: PERRL"]
        )


class Agent5(BaseAgent):
    def __init__(self):
        super().__init__(5, "Initial Assessment")
    
    async def process(self, input_data: AgentInput) -> Agent5Output:
        await asyncio.sleep(0.1)
        return Agent5Output(
            content_md="# Initial Assessment\n\n[Placeholder assessment reasoning]",
            reasoning="Based on presentation and exam findings, considering cardiac vs pulmonary etiology",
            uncertainties=["Exact cause of chest pain", "Severity of symptoms"],
            immediate_concerns=["Rule out MI", "Assess respiratory status"]
        )


class Agent6(BaseAgent):
    def __init__(self):
        super().__init__(6, "Orders")
    
    async def process(self, input_data: AgentInput) -> Agent6Output:
        await asyncio.sleep(0.1)
        
        # Safety Rule: VTE prophylaxis check
        issues = []
        patient_immobile = self._check_patient_immobile(input_data)
        orders_text = "EKG Chest X-ray CBC BMP Troponin Continuous cardiac monitoring IV access O2 if needed VTE prophylaxis Fall precautions"
        
        if patient_immobile and not self._has_vte_prophylaxis(orders_text):
            issues.append("VTE prophylaxis missing.")
        
        result = Agent6Output(
            content_md="# Initial Orders\n\n**Diagnostics:**\n- EKG\n- Chest X-ray\n\n**Management:**\n- Continuous cardiac monitoring\n- IV access",
            diagnostics=["EKG", "Chest X-ray", "CBC", "BMP", "Troponin"],
            management=["Continuous cardiac monitoring", "IV access", "O2 if needed"],
            consults=["Cardiology if indicated"],
            followups=["Serial troponins"],
            misc=["VTE prophylaxis", "Fall precautions"]
        )
        
        if issues:
            result.flags["issues"] = issues
            
        return result
    
    def _check_patient_immobile(self, input_data: AgentInput) -> bool:
        """Check if patient is flagged as immobile or bedbound."""
        # Check context flags
        if input_data.context_flags and input_data.context_flags.get("immobile"):
            return True
        
        # Check for bedbound keyword in raw text
        raw_text = " ".join(input_data.raw_text_refs).lower()
        if "bedbound" in raw_text or "bed bound" in raw_text:
            return True
            
        return False
    
    def _has_vte_prophylaxis(self, orders_text: str) -> bool:
        """Check if orders contain VTE prophylaxis medications."""
        vte_keywords = {'heparin', 'enoxaparin', 'lovenox', 'vte', 'dvt prophylaxis'}
        orders_lower = orders_text.lower()
        return any(keyword in orders_lower for keyword in vte_keywords)