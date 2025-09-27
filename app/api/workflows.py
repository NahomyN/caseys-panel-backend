from fastapi import APIRouter, HTTPException, Depends, Request, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import asyncio
import logging
import time

from ..services.database import get_db
from ..services.models import WorkflowRun, Canvas, WorkflowStatus, Event, AuditLog, DailyRunStats
from ..services.checkpointer import checkpointer
from ..services.models import EventType
from ..schemas.base import WorkflowRunResponse, CanvasResponse, CanvasUpdateRequest, CanvasUpdatedMessage
from ..graph.workflow import create_workflow, WorkflowState
from ..services.models import EventType
from ..auth.security import require_roles, require_patient_access, verify_jwt, enforce_patient_scope
from ..services.analytics import recompute_daily_stats
from ..services.metrics import record_run_started, record_run_completed
from ..services.tenant import get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/workflows/{patient_id}/start")
async def start_workflow(
    patient_id: str,
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_roles(["attending", "resident", "scribe"])),
    tenant_id: str = Depends(get_tenant_id)
) -> Dict[str, Any]:
    try:
        enforce_patient_scope(auth, patient_id)
        run_id = checkpointer.create_run_id(patient_id, tenant_id=tenant_id)
        workflow = create_workflow()
        app = workflow.compile()
        initial_state = WorkflowState(
            run_id=run_id,
            patient_id=patient_id,
            raw_text_refs=["placeholder_raw_text"],
            vitals={"bp": "120/80", "hr": 72, "rr": 16, "temp": 98.6},
            labs={},
            context_flags={}
        )
        checkpointer.update_run_status(run_id, WorkflowStatus.RUNNING.value)
        record_run_started()
        sync_flag = request.query_params.get("sync") in {"1", "true", "yes"}
        if sync_flag:
            logger.info(f"Running workflow synchronously for patient {patient_id}, run_id: {run_id}")
            await run_workflow_async(app, initial_state)
        else:
            asyncio.create_task(run_workflow_async(app, initial_state))
            logger.info(f"Started workflow (async) for patient {patient_id}, run_id: {run_id}")
        return {"run_id": run_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


async def run_workflow_async(app, initial_state: WorkflowState):
    start_time = time.time()
    try:
        logger.info(f"Running workflow async for {initial_state.run_id}")
        # Emit a workflow-level STARTED event (node_key 'workflow') so tests always see at least one event
        try:
            checkpointer.save_event(initial_state.run_id, "workflow", EventType.STARTED, {"patient_id": initial_state.patient_id})
        except Exception as ie:
            logger.warning(f"Failed to record workflow start event: {ie}")
        
        final_state = await app.ainvoke(initial_state)
        # Coerce mapping result into WorkflowState if finalize node not executed due to internal graph behavior
        if not hasattr(final_state, 'errors') and isinstance(final_state, dict):
            try:
                final_state = WorkflowState(**dict(final_state))
            except Exception:
                pass
        # Re-read current run status to honor external cancellation
        current_status = checkpointer.get_run_status(initial_state.run_id)
        if current_status == WorkflowStatus.CANCELLED.value:
            logger.info(f"Workflow {initial_state.run_id} was cancelled; skipping terminal status update")
            return
        
        # Calculate workflow duration
        duration_ms = (time.time() - start_time) * 1000
        
        if final_state.errors:
            checkpointer.update_run_status(initial_state.run_id, WorkflowStatus.FAILED.value)
            record_run_completed("failed", duration_ms)
            logger.error(f"Workflow {initial_state.run_id} completed with errors: {final_state.errors}")
            # Audit
            from .workflows import get_db  # local import to avoid circular
            try:
                from .workflows import get_db as _
                # direct session use
                from ..services.database import SessionLocal
                with SessionLocal() as session:
                    session.add(AuditLog(actor="system", action="workflow.fail", patient_id=initial_state.patient_id, details_json={"run_id": initial_state.run_id, "errors": final_state.errors}))
                    session.commit()
            except Exception:
                pass
        else:
            checkpointer.update_run_status(initial_state.run_id, WorkflowStatus.COMPLETED.value)
            record_run_completed("completed", duration_ms)
            logger.info(f"Workflow {initial_state.run_id} completed successfully")
            try:
                from ..services.database import SessionLocal
                with SessionLocal() as session:
                    session.add(AuditLog(actor="system", action="workflow.complete", patient_id=initial_state.patient_id, details_json={"run_id": initial_state.run_id}))
                    session.commit()
            except Exception:
                pass
            
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        checkpointer.update_run_status(initial_state.run_id, WorkflowStatus.FAILED.value)
        record_run_completed("failed", duration_ms)
        logger.error(f"Workflow {initial_state.run_id} failed: {str(e)}")


@router.get("/workflows/{run_id}/status")
async def get_workflow_status(run_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)) -> Dict[str, Any]:
    try:
        workflow_run = db.query(WorkflowRun).filter(
            WorkflowRun.run_id == run_id,
            WorkflowRun.tenant_id == tenant_id
        ).first()
        
        if not workflow_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        
        checkpoints = checkpointer.list_checkpoints(run_id)
        
        node_states = {}
        for checkpoint in checkpoints:
            state_payload = checkpoint["state"]
            metrics = state_payload.get("metrics") or {}
            node_states[checkpoint["node_key"]] = {
                "status": state_payload.get("status", "unknown"),
                "created_at": checkpoint["created_at"],
                "output": state_payload.get("output"),
                "metrics": metrics
            }
        
        # Merge in persisted metrics where available (takes precedence over computed metrics)
        persisted_metrics = checkpointer.get_persisted_metrics(run_id)
        for pm in persisted_metrics:
            node_key = pm["node_key"]
            if node_key in node_states:
                node_states[node_key]["persisted_metrics"] = pm
                # Override with persisted values where available
                node_states[node_key]["metrics"].update({
                    "attempts": pm["attempts"],
                    "retries": pm["retries"],
                    "fallback_used": pm["fallback_used"],
                    "status": pm["status"]
                })
                if pm["success_duration_ms"]:
                    node_states[node_key]["metrics"]["duration_ms"] = pm["success_duration_ms"]
                elif pm["failure_duration_ms"]:
                    node_states[node_key]["metrics"]["duration_ms"] = pm["failure_duration_ms"]
        
        total_nodes = 10  # fixed number per PRODUCT.md
        completed = sum(1 for v in node_states.values() if v["status"] == "completed")
        progress_pct = round((completed / total_nodes) * 100, 1)

        # Basic timing info using events table if present
        events = db.query(Event).filter(
            Event.run_id == run_id,
            Event.tenant_id == tenant_id
        ).order_by(Event.created_at.asc()).all()
        # Derive STARTED->COMPLETED and STARTED->FAILED durations
        start_times = {}
        success_durations_ms = {}
        failure_durations_ms = {}
        fail_counts = {}
        success_counts = {}
        for ev in events:
            if ev.event_type == EventType.STARTED:
                start_times[ev.node_key] = ev.created_at
            elif ev.event_type == EventType.COMPLETED and ev.node_key in start_times:
                delta = (ev.created_at - start_times[ev.node_key]).total_seconds() * 1000.0
                success_durations_ms[ev.node_key] = round(delta, 2)
                success_counts[ev.node_key] = success_counts.get(ev.node_key, 0) + 1
            elif ev.event_type == EventType.FAILED and ev.node_key in start_times:
                delta = (ev.created_at - start_times[ev.node_key]).total_seconds() * 1000.0
                failure_durations_ms[ev.node_key] = round(delta, 2)
                fail_counts[ev.node_key] = fail_counts.get(ev.node_key, 0) + 1
        # Attach metrics
        for node_key, d_ms in success_durations_ms.items():
            if node_key in node_states:
                node_states[node_key]["metrics"]["event_success_duration_ms"] = d_ms
        for node_key, d_ms in failure_durations_ms.items():
            if node_key in node_states:
                node_states[node_key]["metrics"]["event_failure_duration_ms"] = d_ms
                node_states[node_key]["metrics"]["failures"] = fail_counts.get(node_key, 0)
        for node_key, cnt in success_counts.items():
            if node_key in node_states:
                node_states[node_key]["metrics"]["successes"] = cnt
        critical_path_ms = sum(success_durations_ms.get(f"agent_{i}", 0) for i in range(1, 11)) or None
        total_failures = sum(fail_counts.values())
        total_successes = sum(success_counts.values())

        # Aggregate roll-up metrics (e.g., total duration) if metrics available
        total_duration = sum(v.get("metrics", {}).get("duration_ms", 0) for v in node_states.values())
        total_attempts = sum(v.get("metrics", {}).get("attempts", 0) for v in node_states.values())
        total_retries = sum(v.get("metrics", {}).get("retries", 0) for v in node_states.values())
        fallback_count = sum(1 for v in node_states.values() if v.get("metrics", {}).get("fallback_used"))

        # Extract safety issues from events (node_key == 'safety')
        safety_issues = []
        for ev in events:
            if ev.node_key == 'safety' and ev.payload_json:
                payload = ev.payload_json
                # Expected keys: rule_id, message, severity, source
                safety_issues.append({
                    "rule_id": payload.get("rule_id"),
                    "message": payload.get("message"),
                    "severity": payload.get("severity"),
                    "source": payload.get("source"),
                    "created_at": ev.created_at
                })

        return {
            "run_id": run_id,
            "patient_id": workflow_run.patient_id,
            "status": workflow_run.status.value,
            "created_at": workflow_run.created_at,
            "updated_at": workflow_run.updated_at,
            "progress_pct": progress_pct,
            "node_states": node_states,
            "aggregate_metrics": {
                "total_duration_ms": round(total_duration, 2),
                "total_attempts": total_attempts,
                "total_retries": total_retries,
                "fallbacks_used": fallback_count,
                "event_critical_path_ms": critical_path_ms,
                "event_total_successes": total_successes,
                "event_total_failures": total_failures
            },
            "safety_issues": safety_issues
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {str(e)}")


@router.get("/workflows")
async def list_workflows(
    patient_id: Optional[str] = Query(None, description="Filter by patient_id"),
    status: Optional[str] = Query(None, description="Filter by status (pending,running,completed,failed,cancelled)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
) -> Dict[str, Any]:
    """List workflow runs with optional filtering and pagination."""
    try:
        q = db.query(WorkflowRun).filter(WorkflowRun.tenant_id == tenant_id)
        if patient_id:
            q = q.filter(WorkflowRun.patient_id == patient_id)
        if status:
            try:
                status_enum = WorkflowStatus(status)
                q = q.filter(WorkflowRun.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid status filter")
        total = q.count()
        runs = q.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit).all()
        items = [
            {
                "run_id": r.run_id,
                "patient_id": r.patient_id,
                "status": r.status.value,
                "created_at": r.created_at,
                "updated_at": r.updated_at
            } for r in runs
        ]
        return {"total": total, "count": len(items), "items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list workflows: {str(e)}")


@router.post("/workflows/{run_id}/cancel")
async def cancel_workflow(run_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)) -> Dict[str, Any]:
    """Attempt to cancel an in-flight workflow run."""
    try:
        workflow_run = db.query(WorkflowRun).filter(
            WorkflowRun.run_id == run_id,
            WorkflowRun.tenant_id == tenant_id
        ).first()
        if not workflow_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        if workflow_run.status in {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}:
            raise HTTPException(status_code=400, detail="Workflow already terminal")
        checkpointer.update_run_status(run_id, WorkflowStatus.CANCELLED.value)
        # Emit cancellation event
        try:
            checkpointer.save_event(run_id, "workflow", EventType.PROGRESS, {"cancelled": True})
        except Exception:
            pass
        return {"run_id": run_id, "status": "cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel workflow: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel workflow: {str(e)}")
@router.post("/workflows/{run_id}/resume")
async def resume_workflow(run_id: str, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)) -> Dict[str, Any]:
    try:
        workflow_run = db.query(WorkflowRun).filter(
            WorkflowRun.run_id == run_id,
            WorkflowRun.tenant_id == tenant_id
        ).first()
        if not workflow_run:
            raise HTTPException(status_code=404, detail="Workflow run not found")

        if workflow_run.status not in {WorkflowStatus.FAILED, WorkflowStatus.RUNNING, WorkflowStatus.PENDING}:
            raise HTTPException(status_code=400, detail="Workflow not resumable")

        checkpoints = checkpointer.list_checkpoints(run_id)
        # Rebuild partial state
        stage_a_outputs: Dict[str, Any] = {}
        stage_b_outputs: Dict[str, Any] = {}
        stage_c_outputs: Dict[str, Any] = {}
        completed_nodes = []
        for cp in checkpoints:
            node = cp["node_key"]
            st = cp["state"]
            if st.get("status") == "completed":
                completed_nodes.append(node)
                out = st.get("output") or {}
                if node.startswith("agent_"):
                    # categorize
                    num = int(node.split("_")[1])
                    if 1 <= num <= 6:
                        stage_a_outputs[node] = out
                    elif num in {7,8,9}:
                        stage_b_outputs[node] = out
                    elif num == 10:
                        stage_c_outputs[node] = out

        # If already fully complete just return status
        if {f"agent_{i}" for i in range(1,11)}.issubset(set(completed_nodes)):
            return {"run_id": run_id, "message": "Already completed", "completed_nodes": completed_nodes}

        # Build state object
        state = WorkflowState(
            run_id=run_id,
            patient_id=workflow_run.patient_id,
            raw_text_refs=["placeholder_raw_text"],
            vitals={},
            labs={},
            context_flags={},
            stage_a_outputs=stage_a_outputs,
            stage_b_outputs=stage_b_outputs,
            stage_c_outputs=stage_c_outputs,
            completed_nodes=completed_nodes,
            errors=[]
        )

        workflow = create_workflow()
        app_graph = workflow.compile()
        # Emit resume event
        checkpointer.save_event(run_id, "workflow", EventType.PROGRESS, {"resumed": True, "completed_nodes": len(completed_nodes)})
        try:
            from ..services.database import SessionLocal
            with SessionLocal() as session:
                session.add(AuditLog(actor="system", action="workflow.resume", patient_id=workflow_run.patient_id, details_json={"run_id": run_id, "completed_nodes": completed_nodes}))
                session.commit()
        except Exception:
            pass
        checkpointer.update_run_status(run_id, WorkflowStatus.RUNNING.value)
        asyncio.create_task(run_workflow_async(app_graph, state))
        return {"run_id": run_id, "message": "Resume started", "completed_nodes": completed_nodes}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {str(e)}")


@router.get("/canvases/{patient_id}")
async def get_all_canvases(patient_id: str, request: Request, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)) -> Dict[str, CanvasResponse]:
    try:
        # Decode token & enforce patient scope
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing")
        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        enforce_patient_scope(payload, patient_id)
        canvases = db.query(Canvas).filter(
            Canvas.patient_id == patient_id,
            Canvas.tenant_id == tenant_id
        ).all()
        
        result = {}
        for canvas in canvases:
            result[f"agent_{canvas.agent_no}"] = CanvasResponse(
                patient_id=canvas.patient_id,
                agent_no=canvas.agent_no,
                version=canvas.version,
                content_md=canvas.content_md,
                content_json=canvas.content_json,
                updated_by=canvas.updated_by,
                updated_at=canvas.updated_at
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get canvases: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get canvases: {str(e)}")


@router.get("/canvases/{patient_id}/{agent_no}")
async def get_canvas(patient_id: str, agent_no: int, request: Request, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)) -> CanvasResponse:
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing")
        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        enforce_patient_scope(payload, patient_id)
        canvas = db.query(Canvas).filter(
            Canvas.patient_id == patient_id,
            Canvas.agent_no == agent_no,
            Canvas.tenant_id == tenant_id
        ).first()
        
        if not canvas:
            raise HTTPException(status_code=404, detail="Canvas not found")
        
        return CanvasResponse(
            patient_id=canvas.patient_id,
            agent_no=canvas.agent_no,
            version=canvas.version,
            content_md=canvas.content_md,
            content_json=canvas.content_json,
            updated_by=canvas.updated_by,
            updated_at=canvas.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get canvas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get canvas: {str(e)}")


@router.post("/canvases/{patient_id}/{agent_no}")
async def update_canvas(
    patient_id: str, 
    agent_no: int, 
    update_request: CanvasUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_roles(["attending", "resident", "scribe"])),
    tenant_id: str = Depends(get_tenant_id)
) -> CanvasResponse:
    try:
        # Enforce patient access
        enforce_patient_scope(auth, patient_id)
        canvas = db.query(Canvas).filter(
            Canvas.patient_id == patient_id,
            Canvas.agent_no == agent_no,
            Canvas.tenant_id == tenant_id
        ).first()
        
        # Enforce version conflict detection - client must provide expected version
        if canvas and canvas.version != update_request.version:
            raise HTTPException(
                status_code=409, 
                detail={
                    "error": "Version conflict - client version is stale",
                    "client_version": update_request.version,
                    "current_version": canvas.version,
                    "current_content_md": canvas.content_md,
                    "current_content_json": canvas.content_json
                }
            )
        if canvas:
            canvas.content_md = update_request.content_md
            canvas.content_json = update_request.content_json
            canvas.version += 1
            canvas.updated_by = "user"
        else:
            canvas = Canvas(
                patient_id=patient_id,
                agent_no=agent_no,
                tenant_id=tenant_id,
                version=1,
                content_md=update_request.content_md,
                content_json=update_request.content_json,
                updated_by="user"
            )
            db.add(canvas)

        db.commit()

        audit = AuditLog(
            actor="user", action="canvas.update", patient_id=patient_id,
            details_json={"agent_no": agent_no, "version": canvas.version}
        )
        db.add(audit)
        db.commit()
        db.refresh(canvas)
        
        response = CanvasResponse(
            patient_id=canvas.patient_id,
            agent_no=canvas.agent_no,
            version=canvas.version,
            content_md=canvas.content_md,
            content_json=canvas.content_json,
            updated_by=canvas.updated_by,
            updated_at=canvas.updated_at
        )
        # Best-effort websocket broadcast
        try:
            from ..services.websocket import ws_manager
            msg = CanvasUpdatedMessage(
                patient_id=canvas.patient_id,
                agent_no=canvas.agent_no,
                version=canvas.version
            )
            await ws_manager.broadcast_canvas_updated(msg)
        except Exception as be:
            logger.debug(f"Canvas broadcast failed: {be}")
        
        # Re-queue Agent 7 (Orchestrator) to reassess after any canvas edit
        # We resume the most recent workflow for this patient/tenant using existing checkpoints
        try:
            from ..services.models import WorkflowRun, WorkflowStatus
            latest_run = db.query(WorkflowRun).filter(
                WorkflowRun.patient_id == patient_id,
                WorkflowRun.tenant_id == tenant_id
            ).order_by(WorkflowRun.created_at.desc()).first()
            if latest_run:
                # Build state from checkpoints similar to resume_workflow
                checkpoints = checkpointer.list_checkpoints(latest_run.run_id)
                stage_a_outputs: Dict[str, Any] = {}
                stage_b_outputs: Dict[str, Any] = {}
                stage_c_outputs: Dict[str, Any] = {}
                completed_nodes = []
                for cp in checkpoints:
                    node = cp["node_key"]
                    st = cp["state"]
                    if st.get("status") == "completed":
                        completed_nodes.append(node)
                        out = st.get("output") or {}
                        if node.startswith("agent_"):
                            num = int(node.split("_")[1])
                            if 1 <= num <= 6:
                                stage_a_outputs[node] = out
                            elif num in {7, 8, 9}:
                                stage_b_outputs[node] = out
                            elif num == 10:
                                stage_c_outputs[node] = out
                state = WorkflowState(
                    run_id=latest_run.run_id,
                    patient_id=patient_id,
                    raw_text_refs=["placeholder_raw_text"],
                    vitals={},
                    labs={},
                    context_flags={},
                    stage_a_outputs=stage_a_outputs,
                    stage_b_outputs=stage_b_outputs,
                    stage_c_outputs=stage_c_outputs,
                    completed_nodes=completed_nodes,
                    errors=[]
                )
                workflow = create_workflow()
                app_graph = workflow.compile()
                # Ensure run is marked running
                checkpointer.update_run_status(latest_run.run_id, WorkflowStatus.RUNNING.value)
                # Emit edit-trigger event
                checkpointer.save_event(latest_run.run_id, "agent_7", EventType.PROGRESS, {"requeued_due_to_canvas_edit": True, "agent_no": agent_no})
                asyncio.create_task(run_workflow_async(app_graph, state))
        except Exception as rq:
            logger.debug(f"Agent 7 re-queue after canvas edit failed: {rq}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update canvas: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update canvas: {str(e)}")


@router.get("/final-note/{patient_id}")
async def get_final_note(
    patient_id: str,
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
) -> Dict[str, str]:
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing")
        token = auth_header.split(" ", 1)[1]
        payload = verify_jwt(token)
        enforce_patient_scope(payload, patient_id)
        latest_run = db.query(WorkflowRun).filter(
            WorkflowRun.patient_id == patient_id,
            WorkflowRun.status == WorkflowStatus.COMPLETED,
            WorkflowRun.tenant_id == tenant_id
        ).order_by(WorkflowRun.created_at.desc()).first()
        
        if not latest_run:
            raise HTTPException(status_code=404, detail="No completed workflow found for patient")
        
        final_checkpoint = checkpointer.get_checkpoint(latest_run.run_id, "agent_10")
        
        if not final_checkpoint:
            raise HTTPException(status_code=404, detail="Final note not available")
        
        output = final_checkpoint.get("output", {})
        
        return {
            "patient_id": patient_id,
            "final_note": output.get("final_note", ""),
            "billing_attestation": output.get("billing_attestation", ""),
            "run_id": latest_run.run_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get final note: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get final note: {str(e)}")


@router.get("/admin/daily-stats/{date}")
async def get_daily_stats(
    date: str,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_roles(["attending", "admin"])),
    tenant_id: str = Depends(get_tenant_id)
) -> Dict[str, Any]:
    """Get daily run statistics for a specific date (tenant scoped unless '*' provided)."""
    try:
        query = db.query(DailyRunStats).filter(DailyRunStats.date == date)
        if tenant_id != "*":
            query = query.filter(DailyRunStats.tenant_id == tenant_id)
        stats = query.first()
        if not stats:
            raise HTTPException(status_code=404, detail="Stats not found for this date")
        
        return {
            "date": stats.date,
            "tenant_id": stats.tenant_id,
            "runs_started": stats.runs_started,
            "runs_completed": stats.runs_completed,
            "avg_total_duration_ms": stats.avg_total_duration_ms,
            "failures": stats.failures,
            "fallbacks_used": stats.fallbacks_used
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get daily stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get daily stats: {str(e)}")


@router.get("/admin/safety-rules")
async def list_safety_rules(
    auth: dict = Depends(require_roles(["attending", "admin"]))
) -> List[Dict[str, str]]:
    """List all active safety rules."""
    try:
        from ..safety.rules import list_active_rules
        return list_active_rules()
    except Exception as e:
        logger.error(f"Failed to list safety rules: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list safety rules: {str(e)}")


@router.get("/fhir/Patient/{patient_id}")
async def get_fhir_patient(
    patient_id: str,
    auth: dict = Depends(require_roles(["attending", "resident", "scribe"]))
) -> Dict[str, Any]:
    """Get minimal synthetic FHIR R4 Patient resource."""
    try:
        import hashlib
        
        # Create synthetic FHIR Patient resource
        patient_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:8]
        
        fhir_patient = {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [
                {
                    "use": "usual",
                    "value": patient_hash
                }
            ],
            "active": True,
            "name": [
                {
                    "use": "official",
                    "family": "Patient",
                    "given": [f"Test_{patient_hash[:4]}"]
                }
            ],
            "meta": {
                "versionId": "1",
                "lastUpdated": "2024-01-01T00:00:00Z"
            }
        }
        
        return fhir_patient
        
    except Exception as e:
        logger.error(f"Failed to get FHIR patient: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get FHIR patient: {str(e)}")