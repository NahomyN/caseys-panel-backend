"""Canvas management API endpoints"""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory storage for demo
canvases_store = {}

class CanvasResponse(BaseModel):
    patient_id: str
    agent_no: int
    version: int
    content_md: str
    content_json: dict
    updated_at: str

class CanvasUpdateRequest(BaseModel):
    content_md: str
    content_json: dict

@router.get("/{patient_id}")
async def get_all_canvases(patient_id: str) -> List[CanvasResponse]:
    """Get all canvases for a patient"""
    patient_canvases = []
    
    for key, canvas in canvases_store.items():
        if canvas["patient_id"] == patient_id:
            patient_canvases.append(CanvasResponse(**canvas))
    
    # If no canvases exist, create a default Agent 7 canvas
    if not patient_canvases:
        default_canvas = {
            "patient_id": patient_id,
            "agent_no": 7,
            "version": 1,
            "content_md": "# Agent 7 - Casey\n\nAwaiting workflow execution...",
            "content_json": {"status": "pending"},
            "updated_at": datetime.utcnow().isoformat()
        }
        canvases_store[f"{patient_id}_7"] = default_canvas
        patient_canvases.append(CanvasResponse(**default_canvas))
    
    return patient_canvases

@router.get("/{patient_id}/{agent_no}")
async def get_canvas(patient_id: str, agent_no: int) -> CanvasResponse:
    """Get a specific canvas"""
    key = f"{patient_id}_{agent_no}"
    
    if key not in canvases_store:
        # Create default canvas for Agent 7
        if agent_no == 7:
            canvas = {
                "patient_id": patient_id,
                "agent_no": 7,
                "version": 1,
                "content_md": "# Agent 7 - Casey (Hospitalist Orchestrator)\n\nNo workflow results yet.",
                "content_json": {"status": "pending"},
                "updated_at": datetime.utcnow().isoformat()
            }
            canvases_store[key] = canvas
            return CanvasResponse(**canvas)
        else:
            raise HTTPException(status_code=404, detail="Canvas not found")
    
    return CanvasResponse(**canvases_store[key])

@router.post("/{patient_id}/{agent_no}")
async def update_canvas(
    patient_id: str, 
    agent_no: int,
    request: CanvasUpdateRequest
) -> CanvasResponse:
    """Update a canvas"""
    key = f"{patient_id}_{agent_no}"
    
    if key in canvases_store:
        canvas = canvases_store[key]
        canvas["version"] += 1
    else:
        canvas = {
            "patient_id": patient_id,
            "agent_no": agent_no,
            "version": 1
        }
    
    canvas.update({
        "content_md": request.content_md,
        "content_json": request.content_json,
        "updated_at": datetime.utcnow().isoformat()
    })
    
    canvases_store[key] = canvas
    
    return CanvasResponse(**canvas)
