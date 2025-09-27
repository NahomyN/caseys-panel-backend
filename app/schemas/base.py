from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

# Canonical event types now mirror services.models.EventType values.
# We retain a local str Enum for clean JSON schema generation.
class EventType(str, Enum):
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRIED = "retried"


class BaseWorkflowState(BaseModel):
    patient_id: str
    raw_text_refs: List[str] = []
    vitals: Optional[Dict[str, Any]] = None
    labs: Optional[Dict[str, Any]] = None
    context_flags: Dict[str, bool] = {}


class AgentInput(BaseModel):
    patient_id: str
    raw_text_refs: List[str]
    prior_canvases: Dict[str, str] = {}
    vitals: Optional[Dict[str, Any]] = None
    labs: Optional[Dict[str, Any]] = None
    context_flags: Dict[str, bool] = {}
    # Injected internally for event correlation / retries (not user supplied)
    run_id: Optional[str] = None


class AgentOutput(BaseModel):
    agent_no: int
    content_md: str
    content_json: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    flags: Dict[str, Any] = {}


class WorkflowRunResponse(BaseModel):
    run_id: str
    patient_id: str
    status: WorkflowStatus
    created_at: datetime
    updated_at: datetime


class CanvasResponse(BaseModel):
    patient_id: str
    agent_no: int
    version: int
    content_md: str
    content_json: Optional[Dict[str, Any]] = None
    updated_by: str
    updated_at: datetime


class CanvasUpdateRequest(BaseModel):
    content_md: str
    version: int
    content_json: Optional[Dict[str, Any]] = None


class WorkflowEventMessage(BaseModel):
    run_id: str
    node_key: str
    phase: EventType
    payload: Optional[Dict[str, Any]] = None


class CanvasUpdatedMessage(BaseModel):
    patient_id: str
    agent_no: int
    version: int