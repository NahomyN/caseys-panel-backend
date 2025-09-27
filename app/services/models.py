from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import enum


class WorkflowStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(enum.Enum):
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRIED = "retried"


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    run_id = Column(String, primary_key=True)
    patient_id = Column(String, nullable=False, index=True)
    status = Column(Enum(WorkflowStatus), nullable=False, default=WorkflowStatus.PENDING)
    tenant_id = Column(String, nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # convenient reverse relations
    checkpoints = relationship("Checkpoint", back_populates="workflow_run", cascade="all,delete-orphan")
    events = relationship("Event", back_populates="workflow_run", cascade="all,delete-orphan")

    __table_args__ = (
        # A patient should not have two active (non terminal) runs concurrently (soft business rule).
        # We enforce via partial index at the DB level ideally; here we just prepare for custom validation.
        Index("ix_workflow_runs_patient_active", "patient_id", "status"),
        Index("ix_workflow_runs_tenant", "tenant_id"),
    )


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("workflow_runs.run_id"), nullable=False, index=True)
    node_key = Column(String, nullable=False)
    state_json = Column(JSON, nullable=False)
    state_hash = Column(String, nullable=True, index=True)
    tenant_id = Column(String, nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow_run = relationship("WorkflowRun", back_populates="checkpoints")

    __table_args__ = (
        # Latest checkpoint per (run_id, node_key) matters; we also add an index for retrieval ordering.
        Index("ix_checkpoints_run_node", "run_id", "node_key"),
        Index("ix_checkpoints_tenant", "tenant_id"),
        UniqueConstraint("run_id", "node_key", "state_hash", name="uq_checkpoint_dedup"),
    )


class Canvas(Base):
    __tablename__ = "canvases"

    patient_id = Column(String, primary_key=True)
    agent_no = Column(Integer, primary_key=True)
    tenant_id = Column(String, primary_key=True, default="default")
    version = Column(Integer, nullable=False, default=1)
    content_md = Column(Text, nullable=False)
    content_json = Column(JSON, nullable=True)
    updated_by = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Facilitate queries for all canvases of a patient ordered by agent.
        Index("ix_canvases_patient_agent", "patient_id", "agent_no"),
        Index("ix_canvases_tenant", "tenant_id"),
    )


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("workflow_runs.run_id"), nullable=False, index=True)
    node_key = Column(String, nullable=False)
    event_type = Column(Enum(EventType), nullable=False)
    event_payload_json = Column(JSON, nullable=True)
    tenant_id = Column(String, nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow_run = relationship("WorkflowRun", back_populates="events")

    __table_args__ = (
        Index("ix_events_run_node_time", "run_id", "node_key", "created_at"),
        Index("ix_events_tenant", "tenant_id"),
    )


class Attachment(Base):
    __tablename__ = "attachments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    uri = Column(String, nullable=False)
    size = Column(Integer, nullable=True)
    tenant_id = Column(String, nullable=False, default="default", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    patient_id = Column(String, nullable=True, index=True)
    details_json = Column(JSON, nullable=True)
    tenant_id = Column(String, nullable=False, default="default", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RunNodeMetrics(Base):
    __tablename__ = "run_node_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("workflow_runs.run_id"), nullable=False, index=True)
    node_key = Column(String, nullable=False)
    status = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    success_duration_ms = Column(Integer, nullable=True)
    failure_duration_ms = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    retries = Column(Integer, nullable=False, default=0)
    fallback_used = Column(Integer, nullable=False, default=0)  # 0=false, 1=true
    tenant_id = Column(String, nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    workflow_run = relationship("WorkflowRun")
    
    __table_args__ = (
        # Ensure one metrics record per run_id + node_key combination
        UniqueConstraint("run_id", "node_key", name="uq_run_node_metrics"),
        Index("ix_run_node_metrics_run_status", "run_id", "status"),
        Index("ix_run_node_metrics_tenant", "tenant_id"),
    )


class RunModelUsage(Base):
    __tablename__ = "run_model_usage"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("workflow_runs.run_id"), nullable=False, index=True)
    node_key = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(String, nullable=True)  # Store as string for precision
    tenant_id = Column(String, nullable=False, default="default")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    workflow_run = relationship("WorkflowRun")
    
    __table_args__ = (
        Index("ix_run_model_usage_run_node", "run_id", "node_key"),
        Index("ix_run_model_usage_provider", "provider", "model_name"),
        Index("ix_run_model_usage_tenant", "tenant_id"),
    )


class DailyRunStats(Base):
    __tablename__ = "daily_run_stats"
    # Composite key (date + tenant) for multi-tenant aggregation
    date = Column(String, primary_key=True)  # YYYY-MM-DD format
    tenant_id = Column(String, primary_key=True, default="default")
    runs_started = Column(Integer, nullable=False, default=0)
    runs_completed = Column(Integer, nullable=False, default=0)
    avg_total_duration_ms = Column(Integer, nullable=True)
    failures = Column(Integer, nullable=False, default=0)
    fallbacks_used = Column(Integer, nullable=False, default=0)
    __table_args__ = (
        # Aid frequent lookups by tenant/date ranges
        Index("ix_daily_run_stats_tenant_date", "tenant_id", "date"),
    )