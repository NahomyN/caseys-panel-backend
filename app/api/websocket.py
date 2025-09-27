from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from ..services.websocket import ws_manager
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, patient_id: str = Query(None), run_id: str = Query(None)):
    client_id = str(uuid.uuid4())
    
    await ws_manager.connect(websocket, client_id, patient_id, run_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message from {client_id}: {data}")
            
            await ws_manager.send_personal_message(f"Echo: {data}", client_id)
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, client_id, patient_id, run_id)
        logger.info(f"WebSocket disconnected: {client_id}")