import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Checkpoint, WorkflowRun, Event, EventType, WorkflowStatus, RunNodeMetrics, RunModelUsage
import uuid
from datetime import datetime, timezone
import hashlib
import logging
import asyncio

from ..schemas.base import WorkflowEventMessage, EventType as SchemaEventType
from .websocket import ws_manager

logger = logging.getLogger(__name__)


class PostgresCheckpointer:
    def __init__(self):
        self.session_factory = SessionLocal
    
    def save_checkpoint(self, run_id: str, node_key: str, state: Dict[str, Any], tenant_id: str = "default") -> str:
        """Persist a checkpoint.

        Idempotency: if the latest stored state for (run_id,node_key) already has the
        same content hash, do not create a duplicate row. (Simple JSON compare now; could hash later.)
        """
        serialized = json.dumps(state, sort_keys=True).encode("utf-8")
        state_hash = hashlib.sha256(serialized).hexdigest()
        with self.session_factory() as session:
            existing = session.query(Checkpoint).filter(
                Checkpoint.run_id == run_id,
                Checkpoint.node_key == node_key,
                Checkpoint.state_hash == state_hash
            ).first()
            if existing:
                return str(existing.id)
            checkpoint = Checkpoint(
                run_id=run_id,
                node_key=node_key,
                state_json=state,
                state_hash=state_hash,
                tenant_id=tenant_id
            )
            session.add(checkpoint)
            session.commit()
            return str(checkpoint.id)
    
    def get_checkpoint(self, run_id: str, node_key: str) -> Optional[Dict[str, Any]]:
        with self.session_factory() as session:
            checkpoint = session.query(Checkpoint).filter(
                Checkpoint.run_id == run_id,
                Checkpoint.node_key == node_key
            ).order_by(Checkpoint.created_at.desc()).first()
            
            if checkpoint:
                return checkpoint.state_json
            return None
    
    def list_checkpoints(self, run_id: str) -> List[Dict[str, Any]]:
        with self.session_factory() as session:
            checkpoints = session.query(Checkpoint).filter(
                Checkpoint.run_id == run_id
            ).order_by(Checkpoint.created_at.desc()).all()
            
            return [
                {
                    "id": cp.id,
                    "node_key": cp.node_key,
                    "state": cp.state_json,
                    "created_at": cp.created_at
                }
                for cp in checkpoints
            ]
    
    def get_latest_state(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.session_factory() as session:
            latest_checkpoint = session.query(Checkpoint).filter(
                Checkpoint.run_id == run_id
            ).order_by(Checkpoint.created_at.desc()).first()
            
            if latest_checkpoint:
                return latest_checkpoint.state_json
            return None
    
    def clear_checkpoints(self, run_id: str) -> int:
        with self.session_factory() as session:
            count = session.query(Checkpoint).filter(
                Checkpoint.run_id == run_id
            ).delete()
            session.commit()
            return count
    
    def create_run_id(self, patient_id: str, tenant_id: str = "default") -> str:
        run_id = f"run_{patient_id}_{uuid.uuid4().hex[:8]}"
        with self.session_factory() as session:
            try:
                workflow_run = WorkflowRun(
                    run_id=run_id,
                    patient_id=patient_id,
                    tenant_id=tenant_id
                )
                session.add(workflow_run)
                session.commit()
            except Exception as e:
                # Auto-repair path for legacy SQLite dev.db missing new columns (e.g., tenant_id)
                if "tenant_id" in str(e).lower():
                    from .database import Base, engine
                    logger.warning("Detected legacy schema without tenant_id; rebuilding SQLite schema in-place")
                    Base.metadata.drop_all(bind=engine)
                    Base.metadata.create_all(bind=engine)
                    workflow_run = WorkflowRun(
                        run_id=run_id,
                        patient_id=patient_id,
                        tenant_id=tenant_id
                    )
                    session.add(workflow_run)
                    session.commit()
                else:
                    raise
        return run_id
    
    def update_run_status(self, run_id: str, status: str) -> None:
        with self.session_factory() as session:
            workflow_run = session.query(WorkflowRun).filter(
                WorkflowRun.run_id == run_id
            ).first()
            if workflow_run:
                # Accept either enum value or raw string
                if isinstance(status, WorkflowStatus):
                    workflow_run.status = status
                else:
                    workflow_run.status = WorkflowStatus(status)
                workflow_run.updated_at = datetime.now(timezone.utc)
                session.commit()
    
    def get_run_status(self, run_id: str) -> Optional[str]:
        with self.session_factory() as session:
            workflow_run = session.query(WorkflowRun).filter(
                WorkflowRun.run_id == run_id
            ).first()
            if workflow_run:
                return workflow_run.status.value
            return None

    # Event recording (future WS streaming)
    def save_event(self, run_id: str, node_key: str, event_type: EventType, payload: Optional[Dict[str, Any]] = None, tenant_id: str = "default") -> int:
        with self.session_factory() as session:
            event = Event(
                run_id=run_id,
                node_key=node_key,
                event_type=event_type,
                event_payload_json=payload or {},
                tenant_id=tenant_id
            )
            session.add(event)
            session.commit()
            event_id = event.id

            # Attempt to broadcast over websocket (best-effort, non-blocking)
            try:
                patient_id = session.query(WorkflowRun.patient_id).filter(WorkflowRun.run_id == run_id).scalar()
                if patient_id:
                    schema_event_type = SchemaEventType(event_type.value)
                    msg = WorkflowEventMessage(
                        run_id=run_id,
                        node_key=node_key,
                        phase=schema_event_type,
                        payload=payload or {}
                    )
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(ws_manager.broadcast_workflow_event(msg, patient_id))
                    except RuntimeError:
                        # No running loop (e.g., during sync tests) -> ignore
                        pass
            except Exception as be:
                logger.debug(f"Failed to broadcast event {event_id} for run {run_id}: {be}")
            return event_id

    def persist_node_metrics(self, run_id: str, node_key: str, status: str, metrics: Optional[Dict[str, Any]] = None, tenant_id: str = "default") -> None:
        """Persist node execution metrics. Idempotent - only inserts if not already present."""
        if not metrics:
            return
            
        with self.session_factory() as session:
            # Check if metrics already exist for this run_id + node_key
            existing = session.query(RunNodeMetrics).filter(
                RunNodeMetrics.run_id == run_id,
                RunNodeMetrics.node_key == node_key
            ).first()
            
            if existing:
                # Already exists, don't duplicate
                return
            
            # Extract metrics data
            attempts = metrics.get("attempts", 0)
            retries = metrics.get("retries", 0)
            duration_ms = metrics.get("duration_ms", 0)
            fallback_used = 1 if metrics.get("fallback_used", False) else 0
            
            # Determine durations based on status
            success_duration_ms = duration_ms if status == "completed" else None
            failure_duration_ms = duration_ms if status == "failed" else None
            
            # Create metrics record
            metrics_record = RunNodeMetrics(
                run_id=run_id,
                node_key=node_key,
                status=status,
                started_at=datetime.now(timezone.utc),  # Approximate since we don't track exact start
                completed_at=datetime.now(timezone.utc),
                success_duration_ms=success_duration_ms,
                failure_duration_ms=failure_duration_ms,
                attempts=attempts,
                retries=retries,
                fallback_used=fallback_used,
                tenant_id=tenant_id
            )
            
            session.add(metrics_record)
            session.commit()
            logger.debug(f"Persisted metrics for {run_id}/{node_key}: {metrics}")

    def get_persisted_metrics(self, run_id: str, node_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get persisted metrics for a run, optionally filtered by node_key."""
        with self.session_factory() as session:
            query = session.query(RunNodeMetrics).filter(RunNodeMetrics.run_id == run_id)
            if node_key:
                query = query.filter(RunNodeMetrics.node_key == node_key)
            
            metrics = query.all()
            return [
                {
                    "node_key": m.node_key,
                    "status": m.status,
                    "attempts": m.attempts,
                    "retries": m.retries,
                    "success_duration_ms": m.success_duration_ms,
                    "failure_duration_ms": m.failure_duration_ms,
                    "fallback_used": bool(m.fallback_used),
                    "created_at": m.created_at
                }
                for m in metrics
            ]

    def record_model_usage(self, run_id: str, node_key: str, provider: str, model_name: str, prompt_tokens: int, completion_tokens: int, cost_usd: str, tenant_id: str = "default") -> None:
        total = prompt_tokens + completion_tokens
        with self.session_factory() as session:
            usage = RunModelUsage(
                run_id=run_id,
                node_key=node_key,
                provider=provider,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
                estimated_cost_usd=cost_usd,
                tenant_id=tenant_id
            )
            session.add(usage)
            session.commit()


# Structured logging helper with PHI scrubbing
from ..middleware.phi import scrub_dict, scrub_phi_text

def log_structured(logger, level: str, msg: str, **fields):
    safe_fields = scrub_dict(fields) if fields else {}
    safe_msg = scrub_phi_text(msg) if isinstance(msg, str) else msg
    log_data = {"message": safe_msg, **safe_fields}
    line = json.dumps(log_data)
    getattr(logger, level)(line)


checkpointer = PostgresCheckpointer()