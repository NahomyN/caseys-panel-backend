from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from .base import AgentInput, AgentOutput


class Agent1Output(AgentOutput):
    agent_no: int = 1
    hpi: str
    ros_positive: List[str] = []
    ros_negative: List[str] = []
    differentials: List[str] = []


class Agent2Output(AgentOutput):
    agent_no: int = 2
    reconciled_meds: List[Dict[str, Any]] = []
    pmh: List[str] = []
    psh: List[str] = []
    allergies: List[Dict[str, str]] = []
    high_risk_flags: List[str] = []


class Agent3Output(AgentOutput):
    agent_no: int = 3
    social_history: str
    functional_history: str
    living_situation: str


class Agent4Output(AgentOutput):
    agent_no: int = 4
    vitals: Dict[str, Any]
    physical_exam: List[str]


class Agent5Output(AgentOutput):
    agent_no: int = 5
    reasoning: str
    uncertainties: List[str] = []
    immediate_concerns: List[str] = []


class Agent6Output(AgentOutput):
    agent_no: int = 6
    diagnostics: List[str] = []
    management: List[str] = []
    consults: List[str] = []
    followups: List[str] = []
    misc: List[str] = []


class Agent7Input(AgentInput):
    stage_a_outputs: Dict[str, AgentOutput]


class Agent7Output(AgentOutput):
    agent_no: int = 7
    one_liner: str
    problems: List[Dict[str, Any]] = []
    specialist_needed: Optional[str] = None
    pharmacist_needed: bool = False


class Agent8Input(AgentInput):
    specialty: str
    consultation_request: str
    relevant_data: Dict[str, Any]


class Agent8Output(AgentOutput):
    agent_no: int = 8
    specialty: str
    recommendations: str
    ap_additions: List[str] = []


class Agent9Input(AgentInput):
    current_meds: List[Dict[str, Any]]
    problems: List[str]
    labs: Optional[Dict[str, Any]] = None


class Agent9Output(AgentOutput):
    agent_no: int = 9
    med_safety_review: str
    renal_dosing: List[str] = []
    interactions: List[str] = []
    alternatives: List[str] = []
    monitoring: List[str] = []


class Agent10Input(AgentInput):
    all_outputs: Dict[str, AgentOutput]


class Agent10Output(AgentOutput):
    agent_no: int = 10
    final_note: str
    billing_attestation: str
    time_spent: Optional[int] = None
    complexity_level: str = "moderate"