from .base import BaseAgent
from ..schemas.base import AgentInput
from ..schemas.agents import Agent10Input, Agent10Output
import asyncio


class Agent10(BaseAgent):
    def __init__(self):
        super().__init__(10, "Final Compiler + Billing")
    
    async def process(self, input_data: Agent10Input) -> Agent10Output:
        await asyncio.sleep(0.1)
        
        final_note = self._compile_final_note(input_data.all_outputs)
        billing_attestation = self._generate_billing_attestation()
        
        return Agent10Output(
            content_md=final_note,
            final_note=final_note,
            billing_attestation=billing_attestation,
            time_spent=45,
            complexity_level="moderate"
        )
    
    def _compile_final_note(self, all_outputs) -> str:
        note_sections = []
        
        note_sections.append("# Inpatient Admission Note")
        note_sections.append("")
        
        if "agent_1" in all_outputs:
            note_sections.append(all_outputs["agent_1"].content_md)
            note_sections.append("")
        
        if "agent_2" in all_outputs:
            note_sections.append(all_outputs["agent_2"].content_md)
            note_sections.append("")
        
        if "agent_3" in all_outputs:
            note_sections.append(all_outputs["agent_3"].content_md)
            note_sections.append("")
        
        if "agent_4" in all_outputs:
            note_sections.append(all_outputs["agent_4"].content_md)
            note_sections.append("")
        
        if "agent_5" in all_outputs:
            note_sections.append(all_outputs["agent_5"].content_md)
            note_sections.append("")
        
        if "agent_7" in all_outputs:
            note_sections.append(all_outputs["agent_7"].content_md)
            note_sections.append("")
        
        if "agent_8" in all_outputs:
            note_sections.append(all_outputs["agent_8"].content_md)
            note_sections.append("")
        
        if "agent_9" in all_outputs:
            note_sections.append(all_outputs["agent_9"].content_md)
            note_sections.append("")
        
        return "\n".join(note_sections)
    
    def _generate_billing_attestation(self) -> str:
        return """
**Billing Attestation:**
I personally examined the patient and reviewed all available data. This note represents my clinical assessment and plan. Time spent on patient care: 45 minutes. Moderate complexity level due to multiple medical problems and diagnostic uncertainty.
        """.strip()

    async def fallback_process(self, input_data: Agent10Input, error: Exception):  # type: ignore[override]
        minimal = "# Inpatient Admission Note (Fallback)\n\nSections unavailable due to prior errors. Core summary only."
        return Agent10Output(
            content_md=minimal,
            final_note=minimal,
            billing_attestation="**Billing Attestation:** Limited note produced via fallback.",
            time_spent=None,
            complexity_level="undetermined"
        )