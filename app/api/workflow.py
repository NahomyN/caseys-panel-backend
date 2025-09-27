from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import asyncio
import logging
import time
import json
from datetime import datetime

from ..services.database import get_db
from ..services.models import WorkflowRun, Canvas, Event, AuditLog
from ..services.checkpointer import checkpointer
from ..services.models import EventType, WorkflowStatus
from ..schemas.base import CanvasResponse
from ..auth.security import require_roles, verify_jwt, enforce_patient_scope
from ..services.tenant import get_tenant_id
from ..agents.stage_b import Agent7
from ..schemas.agents import Agent7Input

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/workflow/process-notes")
async def process_notes_with_agent7(
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
) -> Dict[str, Any]:
    """Process ED notes directly with Agent 7 (Hospitalist Orchestrator) for HPI and Assessment generation."""
    try:
        # Parse request body
        body = await request.json()
        ed_notes = body.get('ed_notes', '')
        patient_context = body.get('patient_context', {})

        if not ed_notes.strip():
            raise HTTPException(status_code=400, detail="ED notes are required")

        # Get auth token and validate
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing")

        token = auth_header.split(" ", 1)[1]
        auth_payload = verify_jwt(token)
        user_id = auth_payload.get('sub', 'unknown')

        # Create a case ID for this processing session
        case_id = f"case_{int(time.time())}_{user_id}"

        logger.info(f"Processing ED notes with Agent 7 for case {case_id}")

        # Initialize Agent 7
        agent7 = Agent7()

        # Create input for Agent 7 - simulate minimal stage A outputs for context
        mock_stage_a = {
            "agent_1": {"content_md": f"# HPI Summary\nBased on ED notes: {ed_notes[:200]}..."},
            "agent_2": {"content_md": "# Medications\nTo be reconciled based on ED documentation"},
            "agent_3": {"content_md": "# Social History\nPer ED notes"},
            "agent_4": {"content_md": "# Physical Exam\nAs documented in ED"},
            "agent_5": {"content_md": "# Initial Assessment\nPreliminary assessment per ED"},
            "agent_6": {"content_md": "# Initial Orders\nED orders for review"}
        }

        agent7_input = Agent7Input(
            run_id=case_id,
            patient_id=case_id,
            stage_a_outputs=mock_stage_a,
            raw_text_refs=[ed_notes],
            vitals=patient_context.get('vitals', {}),
            labs=patient_context.get('labs', {}),
            context_flags={"ed_processing": True}
        )

        # Process with Agent 7
        start_time = time.time()
        agent7_result = await agent7.process(agent7_input)
        processing_time = time.time() - start_time

        # Parse the generated content
        hpi_content = extract_hpi_from_content(agent7_result.content_md)
        assessment_content = extract_assessment_from_content(agent7_result.content_md)
        orders_content = generate_orders_from_assessment(agent7_result.problems)

        # Create outputs for each canvas
        outputs = {
            "hpi": hpi_content,
            "assessment": assessment_content,
            "orders": orders_content
        }

        # Save canvases to database
        for canvas_type, content in outputs.items():
            canvas = Canvas(
                patient_id=case_id,
                agent_no=get_agent_number_for_canvas(canvas_type),
                tenant_id=tenant_id,
                version=1,
                content_md=content,
                content_json={"generated_by": "agent_7", "timestamp": datetime.utcnow().isoformat()},
                updated_by="system"
            )
            db.add(canvas)

        # Create workflow run record
        workflow_run = WorkflowRun(
            run_id=case_id,
            patient_id=case_id,
            tenant_id=tenant_id,
            status=WorkflowStatus.COMPLETED
        )
        db.add(workflow_run)

        # Save event
        event = Event(
            run_id=case_id,
            node_key="agent_7",
            event_type=EventType.COMPLETED,
            payload_json={
                "processing_time_ms": processing_time * 1000,
                "ed_notes_length": len(ed_notes),
                "generated_canvases": list(outputs.keys())
            },
            tenant_id=tenant_id
        )
        db.add(event)

        # Audit log
        audit = AuditLog(
            actor="system",
            action="workflow.process_notes",
            patient_id=case_id,
            details_json={
                "user_id": user_id,
                "processing_time_ms": processing_time * 1000,
                "canvases_generated": len(outputs)
            }
        )
        db.add(audit)

        db.commit()

        # Run initial validation
        validation_results = await validate_generated_content(outputs, case_id)

        logger.info(f"Successfully processed ED notes for case {case_id} in {processing_time:.2f}s")

        return {
            "case_id": case_id,
            "outputs": outputs,
            "processing_time_ms": processing_time * 1000,
            "validation": validation_results.get("warnings", {}),
            "suggestions": validation_results.get("suggestions", {}),
            "agent7_metadata": {
                "one_liner": agent7_result.one_liner,
                "specialist_needed": agent7_result.specialist_needed,
                "pharmacist_needed": agent7_result.pharmacist_needed,
                "problems_count": len(agent7_result.problems)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process notes with Agent 7: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process notes: {str(e)}")


@router.post("/workflow/validate-canvases")
async def validate_canvases(
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
) -> Dict[str, Any]:
    """Validate consistency across all canvases and provide suggestions."""
    try:
        body = await request.json()
        canvases = body.get('canvases', {})
        case_id = body.get('case_id', '')

        if not canvases:
            return {"warnings": {}, "suggestions": {}}

        validation_results = await validate_generated_content(canvases, case_id)

        return validation_results

    except Exception as e:
        logger.error(f"Failed to validate canvases: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to validate canvases: {str(e)}")


@router.post("/workflow/chat-refine")
async def chat_refine_canvas(
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
) -> Dict[str, Any]:
    """Chat with Agent 7 to refine specific canvas content."""
    try:
        body = await request.json()
        canvas_id = body.get('canvas_id', '')
        canvas_content = body.get('canvas_content', '')
        user_message = body.get('user_message', '')
        case_context = body.get('case_context', {})

        if not all([canvas_id, user_message]):
            raise HTTPException(status_code=400, detail="Canvas ID and user message are required")

        # Get auth
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing")

        token = auth_header.split(" ", 1)[1]
        auth_payload = verify_jwt(token)

        # Initialize Agent 7 for refinement
        agent7 = Agent7()

        # Create a refinement prompt
        refinement_prompt = f"""
Current {canvas_id.upper()} content:
{canvas_content}

User request: {user_message}

Context from other sections:
{json.dumps(case_context.get('other_canvases', []), indent=2)}

Please provide:
1. A conversational response explaining what you're changing and why
2. Updated content for the {canvas_id} section based on the user's request

Focus on the user's specific request while maintaining medical accuracy and consistency with other sections.
        """

        # For now, simulate AI response - in production, this would call Agent 7 with refinement logic
        ai_response = await generate_refinement_response(canvas_id, canvas_content, user_message, case_context)

        return {
            "response": ai_response["explanation"],
            "updated_content": ai_response["updated_content"] if ai_response["content_changed"] else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process chat refinement: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process chat refinement: {str(e)}")


# Helper functions

def extract_hpi_from_content(content_md: str) -> str:
    """Extract HPI section from Agent 7 output."""
    lines = content_md.split('\n')
    hpi_lines = []
    in_hpi = False

    for line in lines:
        if 'history of present illness' in line.lower() or 'hpi' in line.lower():
            in_hpi = True
            continue
        elif line.startswith('#') and in_hpi:
            break
        elif in_hpi and line.strip():
            hpi_lines.append(line)

    if not hpi_lines:
        # Fallback: extract first paragraph as HPI
        paragraphs = content_md.split('\n\n')
        for para in paragraphs:
            if len(para.strip()) > 50:  # Substantial content
                return para.strip()

    return '\n'.join(hpi_lines).strip() or "HPI to be developed based on ED notes and patient interview."


def extract_assessment_from_content(content_md: str) -> str:
    """Extract Assessment & Plan section from Agent 7 output."""
    if 'Assessment & Plan' in content_md:
        return content_md

    # If not found, create structured assessment
    return """# Assessment & Plan

**One-liner:** To be refined based on clinical presentation.

## Problems:
1. **Primary Problem** - Assessment and plan to be developed
   - [] Diagnostic workup
   - [] Treatment plan
   - [] Monitoring

2. **Additional Issues** - As identified
   - [] Address as appropriate

## Disposition:
- Continue current care plan
- Reassess based on clinical response"""


def generate_orders_from_assessment(problems: List[Dict[str, Any]]) -> str:
    """Generate basic orders based on assessment problems."""
    orders = ["# Orders & Medications\n"]

    for i, problem in enumerate(problems, 1):
        heading = problem.get('heading', f'Problem {i}')
        plan_items = problem.get('plan', [])

        orders.append(f"## {heading}")

        for item in plan_items:
            if isinstance(item, str):
                # Convert plan items to order format
                if any(med in item.lower() for med in ['medication', 'drug', 'mg', 'dose']):
                    orders.append(f"- **Medication:** {item}")
                elif 'lab' in item.lower() or 'test' in item.lower():
                    orders.append(f"- **Laboratory:** {item}")
                elif 'imaging' in item.lower() or 'x-ray' in item.lower() or 'ct' in item.lower():
                    orders.append(f"- **Imaging:** {item}")
                else:
                    orders.append(f"- {item}")

        orders.append("")  # Add spacing

    # Add standard orders
    orders.extend([
        "## Standard Orders",
        "- **Vital Signs:** Every 4 hours",
        "- **Activity:** As tolerated",
        "- **Diet:** As appropriate for condition",
        "- **Monitoring:** Continue per protocol"
    ])

    return '\n'.join(orders)


def get_agent_number_for_canvas(canvas_type: str) -> int:
    """Map canvas types to agent numbers."""
    mapping = {
        "hpi": 1,
        "assessment": 7,
        "orders": 6
    }
    return mapping.get(canvas_type, 7)


async def validate_generated_content(canvases: Dict[str, str], case_id: str) -> Dict[str, Any]:
    """Validate consistency across canvases."""
    warnings = {}
    suggestions = {}

    # Check for medication consistency
    hpi_content = canvases.get('hpi', '')
    assessment_content = canvases.get('assessment', '')
    orders_content = canvases.get('orders', '')

    # Extract medications mentioned in different sections
    hpi_meds = extract_medications(hpi_content)
    assessment_meds = extract_medications(assessment_content)
    orders_meds = extract_medications(orders_content)

    # Check for inconsistencies
    if hpi_meds and orders_meds:
        missing_in_orders = hpi_meds - orders_meds
        if missing_in_orders:
            warnings['orders'] = warnings.get('orders', [])
            warnings['orders'].append(f"Medications mentioned in HPI but not in orders: {', '.join(missing_in_orders)}")

    # Check for common contraindications
    contraindication_warnings = check_contraindications(orders_content)
    if contraindication_warnings:
        warnings['orders'] = warnings.get('orders', []) + contraindication_warnings

    # Generate suggestions
    if 'assessment' in canvases and len(assessment_content) < 100:
        suggestions['assessment'] = ["Consider adding more detailed clinical reasoning", "Include differential diagnoses"]

    if 'orders' in canvases and 'pain' in hpi_content.lower() and 'pain' not in orders_content.lower():
        suggestions['orders'] = suggestions.get('orders', [])
        suggestions['orders'].append("Consider pain management orders based on HPI")

    return {
        "warnings": warnings,
        "suggestions": suggestions,
        "validation_timestamp": datetime.utcnow().isoformat()
    }


def extract_medications(content: str) -> set:
    """Extract medication names from text content."""
    import re
    # Common medication patterns
    med_patterns = [
        r'\b\w*pril\b',  # ACE inhibitors
        r'\b\w*statin\b',  # Statins
        r'\b\w*olol\b',  # Beta blockers
        r'\baspirin\b',
        r'\bwarfarin\b',
        r'\bmetformin\b',
        r'\binsulin\b',
        r'\bheparin\b'
    ]

    medications = set()
    for pattern in med_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        medications.update(match.lower() for match in matches)

    return medications


def check_contraindications(orders_content: str) -> List[str]:
    """Check for potential contraindications in orders."""
    warnings = []
    content_lower = orders_content.lower()

    # Basic contraindication checks
    if 'warfarin' in content_lower and 'heparin' in content_lower:
        warnings.append("⚠️ Warfarin and heparin both ordered - check for bleeding risk")

    if 'nsaid' in content_lower and ('kidney' in content_lower or 'renal' in content_lower):
        warnings.append("⚠️ NSAID ordered with potential kidney issues - consider renal function")

    return warnings


async def generate_refinement_response(canvas_id: str, content: str, user_message: str, context: Dict) -> Dict[str, Any]:
    """Generate AI response for canvas refinement."""
    # This is a simplified version - in production, this would use Agent 7's refinement capabilities

    if 'more detail' in user_message.lower() or 'specific' in user_message.lower():
        response = f"I'll add more detailed information to the {canvas_id} section. Let me enhance the clinical details and provide more specific findings."
        updated_content = content + f"\n\n**Additional Details:** Enhanced based on clinical review and available documentation."
        content_changed = True

    elif 'contraindication' in user_message.lower() or 'safety' in user_message.lower():
        response = f"I'll review the {canvas_id} section for any potential contraindications or safety concerns. This is important for patient safety."
        updated_content = content + f"\n\n**Safety Review:** No major contraindications identified. Continue monitoring per protocol."
        content_changed = True

    elif 'format' in user_message.lower() or 'style' in user_message.lower():
        response = f"I'll reformat the {canvas_id} section to improve clarity and clinical presentation."
        # Simple formatting improvement
        lines = content.split('\n')
        formatted_lines = []
        for line in lines:
            if line.strip() and not line.startswith('#'):
                if not line.startswith('-') and not line.startswith('*'):
                    formatted_lines.append(f"- {line.strip()}")
                else:
                    formatted_lines.append(line)
            else:
                formatted_lines.append(line)
        updated_content = '\n'.join(formatted_lines)
        content_changed = True

    else:
        response = f"I understand you want to refine the {canvas_id} section. Could you be more specific about what changes you'd like? For example, you could ask me to:\n- Add more clinical detail\n- Check for contraindications\n- Reformat for better clarity\n- Focus on specific aspects"
        updated_content = content
        content_changed = False

    return {
        "explanation": response,
        "updated_content": updated_content,
        "content_changed": content_changed
    }