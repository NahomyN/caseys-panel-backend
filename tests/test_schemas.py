import pytest
from pydantic import ValidationError
from app.schemas.base import (
    BaseWorkflowState, AgentInput, AgentOutput, 
    WorkflowEventMessage, CanvasUpdatedMessage,
    WorkflowStatus, EventType
)
from app.schemas.agents import (
    Agent1Output, Agent2Output, Agent7Output, Agent10Output
)


def test_base_workflow_state():
    state = BaseWorkflowState(patient_id="patient_123")
    assert state.patient_id == "patient_123"
    assert state.raw_text_refs == []
    assert state.vitals is None
    assert state.context_flags == {}


def test_agent_input():
    input_data = AgentInput(
        patient_id="patient_123",
        raw_text_refs=["ref1", "ref2"],
        vitals={"bp": "120/80", "hr": 72},
        context_flags={"urgent": True}
    )
    assert input_data.patient_id == "patient_123"
    assert len(input_data.raw_text_refs) == 2
    assert input_data.vitals["bp"] == "120/80"
    assert input_data.context_flags["urgent"] is True


def test_agent_output():
    output = AgentOutput(
        agent_no=1,
        content_md="# Test Output",
        confidence=0.95,
        flags={"reviewed": True}
    )
    assert output.agent_no == 1
    assert output.content_md == "# Test Output"
    assert output.confidence == 0.95
    assert output.flags["reviewed"] is True


def test_agent1_output():
    output = Agent1Output(
        content_md="# HPI & ROS\nTest content",
        hpi="Patient presents with chest pain",
        ros_positive=["chest pain", "dyspnea"],
        ros_negative=["fever", "nausea"],
        differentials=["MI", "PE", "pneumonia"]
    )
    assert output.agent_no == 1
    assert output.hpi == "Patient presents with chest pain"
    assert "chest pain" in output.ros_positive
    assert "fever" in output.ros_negative
    assert len(output.differentials) == 3


def test_agent2_output():
    output = Agent2Output(
        content_md="# PMH & Medications",
        reconciled_meds=[{"name": "Lisinopril", "dose": "10mg"}],
        pmh=["HTN", "DM"],
        allergies=[{"allergen": "PCN", "reaction": "rash"}]
    )
    assert output.agent_no == 2
    assert len(output.reconciled_meds) == 1
    assert output.reconciled_meds[0]["name"] == "Lisinopril"
    assert "HTN" in output.pmh


def test_agent7_output():
    output = Agent7Output(
        content_md="# A&P",
        one_liner="65M with chest pain, r/o ACS",
        problems=[
            {"heading": "Chest pain", "plan": ["EKG", "troponins"]}
        ],
        specialist_needed="cardiology",
        pharmacist_needed=True
    )
    assert output.agent_no == 7
    assert output.one_liner.startswith("65M")
    assert len(output.problems) == 1
    assert output.specialist_needed == "cardiology"
    assert output.pharmacist_needed is True


def test_agent10_output():
    output = Agent10Output(
        content_md="# Final Note",
        final_note="Complete admission note...",
        billing_attestation="I examined the patient...",
        time_spent=45,
        complexity_level="high"
    )
    assert output.agent_no == 10
    assert output.time_spent == 45
    assert output.complexity_level == "high"


def test_workflow_event_message():
    event = WorkflowEventMessage(
        run_id="run_123",
        node_key="agent_1",
        phase=EventType.STARTED,
        payload={"message": "Starting Agent 1"}
    )
    assert event.run_id == "run_123"
    assert event.node_key == "agent_1"
    assert event.phase == EventType.STARTED
    assert event.payload["message"] == "Starting Agent 1"


def test_canvas_updated_message():
    message = CanvasUpdatedMessage(
        patient_id="patient_123",
        agent_no=1,
        version=2
    )
    assert message.patient_id == "patient_123"
    assert message.agent_no == 1
    assert message.version == 2


def test_workflow_status_enum():
    assert WorkflowStatus.PENDING == "pending"
    assert WorkflowStatus.RUNNING == "running"
    assert WorkflowStatus.COMPLETED == "completed"
    assert WorkflowStatus.FAILED == "failed"


def test_event_type_enum():
    assert EventType.STARTED == "started"
    assert EventType.COMPLETED == "completed"
    assert EventType.FAILED == "failed"


def test_validation_error_on_missing_required_field():
    with pytest.raises(ValidationError):
        AgentInput()
    
    with pytest.raises(ValidationError):
        AgentOutput(content_md="test")


def test_validation_error_on_wrong_type():
    with pytest.raises(ValidationError):
        AgentInput(
            patient_id=123,
            raw_text_refs="not a list"
        )