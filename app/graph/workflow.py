from langgraph.graph import StateGraph, END
from typing import Dict, Any, List, Optional
from ..schemas.base import BaseWorkflowState, AgentInput
from ..schemas.agents import Agent7Input, Agent8Input, Agent9Input, Agent10Input
from ..agents.stage_a import Agent1, Agent2, Agent3, Agent4, Agent5, Agent6
from ..agents.stage_b import Agent7, Agent8, Agent9
from ..agents.stage_c import Agent10
from ..services import checkpointer as checkpointer_module
from ..validation.output_validator import validate_agent_output
from ..services.models import EventType
from ..services.checkpointer import log_structured
import asyncio
import logging

logger = logging.getLogger(__name__)


class WorkflowState(BaseWorkflowState):
    run_id: str = ""
    stage_a_outputs: Dict[str, Any] = {}
    stage_b_outputs: Dict[str, Any] = {}
    stage_c_outputs: Dict[str, Any] = {}
    errors: List[str] = []
    completed_nodes: List[str] = []
    safety_issues: List[Dict[str, Any]] = []  # collected safety issues across the workflow


async def finalize_state(state: Any) -> WorkflowState:
    """Ensure the final returned object is a WorkflowState instance.

    LangGraph may return a plain mapping (AddableValuesDict) after merging parallel branches.
    This node coerces it back into the pydantic model so downstream code & tests relying on
    attribute access (final_state.run_id) continue to work.
    """
    if isinstance(state, WorkflowState):
        return state
    # state is a mapping; construct model (ignore extra just in case)
    return WorkflowState(**dict(state))


async def stage_a_parallel(state: WorkflowState) -> WorkflowState:
    log_structured(logger, "info", "stage_a_start", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "stage_a", EventType.STARTED, {})
    
    agents = [Agent1(), Agent2(), Agent3(), Agent4(), Agent5(), Agent6()]
    
    base_input = AgentInput(
        patient_id=state.patient_id,
        raw_text_refs=state.raw_text_refs,
        vitals=state.vitals,
        labs=state.labs,
        context_flags=state.context_flags
    )
    
    # include run_id in input for retry event correlation
    base_input.run_id = state.run_id
    # Determine which agents still need to run (resume support)
    existing = set(state.stage_a_outputs.keys())
    agent_map = {1: Agent1, 2: Agent2, 3: Agent3, 4: Agent4, 5: Agent5, 6: Agent6}
    pending_agents = []
    for i in range(1,7):
        key = f"agent_{i}"
        if key not in existing:
            pending_agents.append(agent_map[i]())
    if not pending_agents:
        log_structured(logger, "info", "stage_a_skip_all_completed", run_id=state.run_id)
        return state
    tasks = [agent.run_with_retry(base_input) for agent in pending_agents]
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:  # catastrophic gather failure
        log_structured(logger, "error", "stage_a_failed", run_id=state.run_id, error=str(e))
        state.errors.append(f"Stage A: {str(e)}")
        checkpointer_module.checkpointer.save_event(state.run_id, "stage_a", EventType.FAILED, {"error": str(e)})
        return state
    outputs: Dict[str, Any] = {}
    for i, result in enumerate(results):
        agent_key = f"agent_{i + 1}"
        if isinstance(result, Exception):
            logger.error(f"Agent {i + 1} failed: {str(result)}")
            state.errors.append(f"Agent {i + 1}: {str(result)}")
        else:
            validated, issues, repaired = validate_agent_output(result.agent_no, result.model_dump())
            if issues:
                validated["_validation"] = {"issues": issues, "repaired": repaired}
            outputs[agent_key] = result.__class__(**validated)
            state.completed_nodes.append(agent_key)
            metrics = result.flags.get("metrics", {})
            checkpointer_module.checkpointer.save_checkpoint(
                state.run_id,
                agent_key,
                {"output": result.model_dump(), "status": "completed", "metrics": metrics}
            )
            mu = result.flags.get("model_usage")
            if mu:
                checkpointer_module.checkpointer.record_model_usage(
                    state.run_id,
                    agent_key,
                    mu.get("provider", "unknown"),
                    mu.get("model", "unknown"),
                    int(mu.get("prompt_tokens", 0)),
                    int(mu.get("completion_tokens", 0)),
                    mu.get("estimated_cost_usd", "0"),
                )
                # Record model usage to Prometheus
                record_model_usage(
                    agent_key,
                    mu.get("model", "unknown"),
                    int(mu.get("prompt_tokens", 0)),
                    int(mu.get("completion_tokens", 0))
                )
            checkpointer_module.checkpointer.save_event(state.run_id, agent_key, EventType.PROGRESS, {"completed": True})
            # Persist metrics to run_node_metrics table
            checkpointer_module.checkpointer.persist_node_metrics(state.run_id, agent_key, "completed", metrics)
            
            # Record all metrics to Prometheus for real-time monitoring
            _record_agent_metrics(agent_key, metrics, mu)
    state.stage_a_outputs = outputs
    log_structured(logger, "info", "stage_a_completed", run_id=state.run_id, completed=len(outputs))
    checkpointer_module.checkpointer.save_event(state.run_id, "stage_a", EventType.COMPLETED, {"completed": len(outputs)})
    
    return state


async def stage_b_orchestrator(state: WorkflowState) -> WorkflowState:
    log_structured(logger, "info", "orchestrator_start", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_7", EventType.STARTED, {})
    
    agent7 = Agent7()
    
    orchestrator_input = Agent7Input(
        patient_id=state.patient_id,
        raw_text_refs=state.raw_text_refs,
        prior_canvases={},
        vitals=state.vitals,
        labs=state.labs,
        context_flags=state.context_flags,
        stage_a_outputs=state.stage_a_outputs
    )
    orchestrator_input.run_id = state.run_id
    
    try:
        result = await agent7.run_with_retry(orchestrator_input)
    except Exception as e:
        log_structured(logger, "error", "orchestrator_failed", run_id=state.run_id, error=str(e))
        state.errors.append(f"Agent 7: {str(e)}")
        checkpointer_module.checkpointer.save_event(state.run_id, "agent_7", EventType.FAILED, {"error": str(e)})
        return state
    validated, issues, repaired = validate_agent_output(result.agent_no, result.model_dump())
    if issues:
        validated["_validation"] = {"issues": issues, "repaired": repaired}
    state.stage_b_outputs["agent_7"] = result.__class__(**validated)
    state.completed_nodes.append("agent_7")
    metrics = result.flags.get("metrics", {})
    checkpointer_module.checkpointer.save_checkpoint(
        state.run_id,
        "agent_7",
        {"output": result.model_dump(), "status": "completed", "metrics": metrics}
    )
    mu = result.flags.get("model_usage")
    if mu:
        checkpointer_module.checkpointer.record_model_usage(
            state.run_id,
            "agent_7",
            mu.get("provider", "unknown"),
            mu.get("model", "unknown"),
            int(mu.get("prompt_tokens", 0)),
            int(mu.get("completion_tokens", 0)),
            mu.get("estimated_cost_usd", "0"),
        )
        # Record model usage to Prometheus
        record_model_usage(
            "agent_7",
            mu.get("model", "unknown"),
            int(mu.get("prompt_tokens", 0)),
            int(mu.get("completion_tokens", 0))
        )
    # Run safety rules after orchestrator output (gives us problems + earlier agent outputs)
    try:
        _evaluate_and_record_safety(state, source_node="agent_7")
    except Exception as se:
        log_structured(logger, "warning", "safety_eval_failed", run_id=state.run_id, error=str(se))
    log_structured(logger, "info", "orchestrator_completed", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_7", EventType.COMPLETED, {})
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_7", EventType.PROGRESS, {"completed": True})
    # Persist metrics to run_node_metrics table
    checkpointer_module.checkpointer.persist_node_metrics(state.run_id, "agent_7", "completed", metrics)
    
    # Record all metrics to Prometheus for real-time monitoring
    _record_agent_metrics("agent_7", metrics, mu)
    
    # Persist Agent 7 canvas to Postgres and broadcast update (idempotent-ish via versioning)
    try:
        from ..services.database import SessionLocal
        from ..services.models import Canvas, AuditLog, WorkflowRun
        from ..services.websocket import ws_manager
        from ..schemas.base import CanvasUpdatedMessage
        
        with SessionLocal() as session:
            tenant_id = session.query(WorkflowRun.tenant_id).filter(WorkflowRun.run_id == state.run_id).scalar() or "default"
            canvas = session.query(Canvas).filter(
                Canvas.patient_id == state.patient_id,
                Canvas.agent_no == 7,
                Canvas.tenant_id == tenant_id
            ).first()
            content_md = result.content_md
            content_json = result.model_dump()
            if canvas:
                canvas.content_md = content_md
                canvas.content_json = content_json
                canvas.version += 1
                canvas.updated_by = "system"
            else:
                canvas = Canvas(
                    patient_id=state.patient_id,
                    agent_no=7,
                    tenant_id=tenant_id,
                    version=1,
                    content_md=content_md,
                    content_json=content_json,
                    updated_by="system"
                )
                session.add(canvas)
            session.commit()
            session.refresh(canvas)
            # Audit log for system write (best effort)
            try:
                session.add(AuditLog(actor="system", action="canvas.update", patient_id=state.patient_id, details_json={"agent_no": 7, "version": canvas.version, "run_id": state.run_id}))
                session.commit()
            except Exception:
                session.rollback()
            # Best-effort websocket broadcast (non-blocking)
            try:
                msg = CanvasUpdatedMessage(patient_id=canvas.patient_id, agent_no=7, version=canvas.version)
                import asyncio as _asyncio
                _asyncio.create_task(ws_manager.broadcast_canvas_updated(msg))
            except Exception as be:
                logger.debug(f"Canvas broadcast failed: {be}")
    except Exception as pe:
        log_structured(logger, "warning", "agent7_canvas_persist_failed", run_id=state.run_id, error=str(pe))
    
    return state


async def stage_b_specialist(state: WorkflowState) -> WorkflowState:
    orchestrator_output = state.stage_b_outputs.get("agent_7")
    if not orchestrator_output or not orchestrator_output.specialist_needed:
        log_structured(logger, "info", "specialist_skipped", run_id=state.run_id)
        return state
    
    log_structured(logger, "info", "specialist_start", run_id=state.run_id, specialty=orchestrator_output.specialist_needed)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_8", EventType.STARTED, {"specialty": orchestrator_output.specialist_needed})
    
    agent8 = Agent8()
    
    specialist_input = Agent8Input(
        patient_id=state.patient_id,
        raw_text_refs=state.raw_text_refs,
        specialty=orchestrator_output.specialist_needed,
        consultation_request="Review case and provide recommendations",
    relevant_data={"stage_a": state.stage_a_outputs, "orchestrator": orchestrator_output.model_dump()}
    )
    specialist_input.run_id = state.run_id
    
    try:
        result = await agent8.run_with_retry(specialist_input)
    except Exception as e:
        log_structured(logger, "error", "specialist_failed", run_id=state.run_id, error=str(e))
        state.errors.append(f"Agent 8: {str(e)}")
        checkpointer_module.checkpointer.save_event(state.run_id, "agent_8", EventType.FAILED, {"error": str(e)})
        return state
    validated, issues, repaired = validate_agent_output(result.agent_no, result.model_dump())
    if issues:
        validated["_validation"] = {"issues": issues, "repaired": repaired}
    state.stage_b_outputs["agent_8"] = result.__class__(**validated)
    state.completed_nodes.append("agent_8")
    metrics = result.flags.get("metrics", {})
    checkpointer_module.checkpointer.save_checkpoint(
        state.run_id,
        "agent_8", 
        {"output": result.model_dump(), "status": "completed", "metrics": metrics}
    )
    mu = result.flags.get("model_usage")
    if mu:
        checkpointer_module.checkpointer.record_model_usage(
            state.run_id,
            "agent_8",
            mu.get("provider", "unknown"),
            mu.get("model", "unknown"),
            int(mu.get("prompt_tokens", 0)),
            int(mu.get("completion_tokens", 0)),
            mu.get("estimated_cost_usd", "0"),
        )
    log_structured(logger, "info", "specialist_completed", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_8", EventType.COMPLETED, {})
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_8", EventType.PROGRESS, {"completed": True})
    # Persist metrics to run_node_metrics table
    checkpointer_module.checkpointer.persist_node_metrics(state.run_id, "agent_8", "completed", metrics)
    
    # Record all metrics to Prometheus for real-time monitoring
    mu = result.flags.get("model_usage")
    _record_agent_metrics("agent_8", metrics, mu)
    
    return state


async def stage_b_pharmacist(state: WorkflowState) -> WorkflowState:
    orchestrator_output = state.stage_b_outputs.get("agent_7")
    if not orchestrator_output or not orchestrator_output.pharmacist_needed:
        log_structured(logger, "info", "pharmacist_skipped", run_id=state.run_id)
        return state
    
    log_structured(logger, "info", "pharmacist_start", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_9", EventType.STARTED, {})
    
    agent9 = Agent9()
    
    med_rec_output = state.stage_a_outputs.get("agent_2")
    current_meds = med_rec_output.reconciled_meds if med_rec_output else []
    problems = [p.get("heading", "") for p in orchestrator_output.problems]
    
    pharmacist_input = Agent9Input(
        patient_id=state.patient_id,
        raw_text_refs=state.raw_text_refs,
        current_meds=current_meds,
        problems=problems,
        labs=state.labs
    )
    pharmacist_input.run_id = state.run_id
    
    try:
        result = await agent9.run_with_retry(pharmacist_input)
    except Exception as e:
        log_structured(logger, "error", "pharmacist_failed", run_id=state.run_id, error=str(e))
        state.errors.append(f"Agent 9: {str(e)}")
        checkpointer_module.checkpointer.save_event(state.run_id, "agent_9", EventType.FAILED, {"error": str(e)})
        return state
    validated, issues, repaired = validate_agent_output(result.agent_no, result.model_dump())
    if issues:
        validated["_validation"] = {"issues": issues, "repaired": repaired}
    state.stage_b_outputs["agent_9"] = result.__class__(**validated)
    state.completed_nodes.append("agent_9")
    metrics = result.flags.get("metrics", {})
    checkpointer_module.checkpointer.save_checkpoint(
        state.run_id,
        "agent_9",
        {"output": result.model_dump(), "status": "completed", "metrics": metrics}
    )
    mu = result.flags.get("model_usage")
    if mu:
        checkpointer_module.checkpointer.record_model_usage(
            state.run_id,
            "agent_9",
            mu.get("provider", "unknown"),
            mu.get("model", "unknown"),
            int(mu.get("prompt_tokens", 0)),
            int(mu.get("completion_tokens", 0)),
            mu.get("estimated_cost_usd", "0"),
        )
    # Re-run safety rules after pharmacist (new med safety insights)
    try:
        _evaluate_and_record_safety(state, source_node="agent_9")
    except Exception as se:
        log_structured(logger, "warning", "safety_eval_failed", run_id=state.run_id, error=str(se))
    log_structured(logger, "info", "pharmacist_completed", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_9", EventType.COMPLETED, {})
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_9", EventType.PROGRESS, {"completed": True})
    # Persist metrics to run_node_metrics table
    checkpointer_module.checkpointer.persist_node_metrics(state.run_id, "agent_9", "completed", metrics)
    
    # Record all metrics to Prometheus for real-time monitoring
    mu = result.flags.get("model_usage")
    _record_agent_metrics("agent_9", metrics, mu)
    
    return state


async def stage_c_compiler(state: WorkflowState) -> WorkflowState:
    log_structured(logger, "info", "compiler_start", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_10", EventType.STARTED, {})
    
    agent10 = Agent10()
    
    all_outputs = {}
    all_outputs.update(state.stage_a_outputs)
    all_outputs.update(state.stage_b_outputs)
    
    compiler_input = Agent10Input(
        patient_id=state.patient_id,
        raw_text_refs=state.raw_text_refs,
        all_outputs=all_outputs
    )
    compiler_input.run_id = state.run_id
    
    try:
        result = await agent10.run_with_retry(compiler_input)
    except Exception as e:
        log_structured(logger, "error", "compiler_failed", run_id=state.run_id, error=str(e))
        state.errors.append(f"Agent 10: {str(e)}")
        checkpointer_module.checkpointer.save_event(state.run_id, "agent_10", EventType.FAILED, {"error": str(e)})
        return state
    validated, issues, repaired = validate_agent_output(result.agent_no, result.model_dump())
    if issues:
        validated["_validation"] = {"issues": issues, "repaired": repaired}
    state.stage_c_outputs["agent_10"] = result.__class__(**validated)
    state.completed_nodes.append("agent_10")
    metrics = result.flags.get("metrics", {})
    checkpointer_module.checkpointer.save_checkpoint(
        state.run_id,
        "agent_10",
        {"output": result.model_dump(), "status": "completed", "metrics": metrics}
    )
    mu = result.flags.get("model_usage")
    if mu:
        checkpointer_module.checkpointer.record_model_usage(
            state.run_id,
            "agent_10",
            mu.get("provider", "unknown"),
            mu.get("model", "unknown"),
            int(mu.get("prompt_tokens", 0)),
            int(mu.get("completion_tokens", 0)),
            mu.get("estimated_cost_usd", "0"),
        )
    # Final safety pass just before completion to capture any last-minute compiled insights
    try:
        _evaluate_and_record_safety(state, source_node="agent_10")
    except Exception as se:
        log_structured(logger, "warning", "safety_eval_failed", run_id=state.run_id, error=str(se))
    log_structured(logger, "info", "compiler_completed", run_id=state.run_id)
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_10", EventType.COMPLETED, {})
    checkpointer_module.checkpointer.save_event(state.run_id, "agent_10", EventType.PROGRESS, {"completed": True})
    # Persist metrics to run_node_metrics table
    checkpointer_module.checkpointer.persist_node_metrics(state.run_id, "agent_10", "completed", metrics)
    
    # Record all metrics to Prometheus for real-time monitoring
    mu = result.flags.get("model_usage")
    _record_agent_metrics("agent_10", metrics, mu)
    
    return state


def should_run_specialist(state: WorkflowState) -> str:
    orchestrator_output = state.stage_b_outputs.get("agent_7")
    if orchestrator_output and orchestrator_output.specialist_needed:
        return "specialist"
    return "pharmacist_check"


def should_run_pharmacist(state: WorkflowState) -> str:
    orchestrator_output = state.stage_b_outputs.get("agent_7")
    if orchestrator_output and orchestrator_output.pharmacist_needed:
        return "pharmacist"
    return "stage_c"


def create_workflow() -> StateGraph:
    workflow = StateGraph(WorkflowState)
    
    workflow.add_node("stage_a", stage_a_parallel)
    workflow.add_node("orchestrator", stage_b_orchestrator)
    workflow.add_node("specialist", stage_b_specialist)
    workflow.add_node("pharmacist", stage_b_pharmacist)
    workflow.add_node("stage_c", stage_c_compiler)
    workflow.add_node("finalize", finalize_state)
    
    workflow.set_entry_point("stage_a")
    
    workflow.add_edge("stage_a", "orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        should_run_specialist,
        {"specialist": "specialist", "pharmacist_check": "pharmacist"}
    )
    workflow.add_conditional_edges(
        "specialist", 
        should_run_pharmacist,
        {"pharmacist": "pharmacist", "stage_c": "stage_c"}
    )
    workflow.add_edge("pharmacist", "stage_c")
    workflow.add_edge("stage_c", "finalize")
    workflow.add_edge("finalize", END)
    
    return workflow


# --- Safety integration helpers ---
from ..safety.rules import check_safety_rules  # placed at bottom to avoid circulars
from ..services.metrics import record_safety_issue, record_node_duration, record_fallback_used, record_model_usage, record_node_retry


def _record_agent_metrics(node_key: str, metrics: Dict[str, Any], model_usage: Dict[str, Any] = None):
    """Helper to record agent performance metrics to Prometheus."""
    # Record execution duration
    if "duration_ms" in metrics:
        record_node_duration(node_key, metrics["duration_ms"])
    
    # Record fallback usage
    if metrics.get("fallback_used", False):
        record_fallback_used(node_key)
    
    # Record retries
    if "retries" in metrics and metrics["retries"] > 0:
        for _ in range(metrics["retries"]):
            record_node_retry(node_key)
    
    # Record model usage
    if model_usage:
        record_model_usage(
            node_key,
            model_usage.get("model", "unknown"),
            int(model_usage.get("prompt_tokens", 0)),
            int(model_usage.get("completion_tokens", 0))
        )


def _build_safety_state(state: WorkflowState) -> Dict[str, Any]:
    """Assemble a simplified snapshot for safety rules.
    Heuristic mapping from available agent outputs; safe to be lossy.
    """
    patient: Dict[str, Any] = {}
    # Derive conditions from Agent1 differentials (placeholder) & any flags
    a1 = state.stage_a_outputs.get("agent_1")
    if a1 and getattr(a1, "differentials", None):
        patient["conditions"] = [c.lower() for c in a1.differentials]
    else:
        patient["conditions"] = []
    # Medications from Agent2 reconciled_meds
    meds = []
    a2 = state.stage_a_outputs.get("agent_2")
    if a2 and getattr(a2, "reconciled_meds", None):
        for m in a2.reconciled_meds:
            if isinstance(m, dict):
                name = m.get("name") or m.get("med") or str(m)
                meds.append(name)
            else:
                meds.append(str(m))
    # Plan meds (pharmacist alternatives or monitoring suggestions)
    a9 = state.stage_b_outputs.get("agent_9")
    plan_meds = []
    if a9 and getattr(a9, "alternatives", None):
        plan_meds.extend([str(x) for x in a9.alternatives])
    # Labs from workflow state + maybe pharmacist renal dosing context
    labs = dict(state.labs or {})
    # Orders derived from diagnostics & management suggestions
    a6 = state.stage_a_outputs.get("agent_6")
    orders = []
    if a6:
        for attr in ("diagnostics", "management"):
            val = getattr(a6, attr, [])
            orders.extend([str(x) for x in val])
    # Problems from Agent7 orchestrator
    a7 = state.stage_b_outputs.get("agent_7")
    if a7 and getattr(a7, "problems", None):
        problems = a7.problems
    else:
        problems = []
    return {
        "patient": patient,
        "medications": meds,
        "labs": labs,
        "orders": orders,
        "plan": {"medications": plan_meds, "problems": problems}
    }


def _evaluate_and_record_safety(state: WorkflowState, source_node: str):
    snapshot = _build_safety_state(state)
    issues = check_safety_rules(snapshot, node_key=source_node)
    if not issues:
        return
    for issue in issues:
        # Record metric
        record_safety_issue(issue.rule_id, issue.severity)
        # Persist as event (node_key 'safety')
        try:
            checkpointer_module.checkpointer.save_event(state.run_id, "safety", EventType.PROGRESS, {
                "rule_id": issue.rule_id,
                "message": issue.message,
                "severity": issue.severity,
                "source": source_node
            })
        except Exception:
            pass
        state.safety_issues.append({
            "rule_id": issue.rule_id,
            "message": issue.message,
            "severity": issue.severity,
            "source": source_node
        })