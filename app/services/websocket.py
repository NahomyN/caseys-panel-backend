import json
import logging
import asyncio
import time
from typing import Dict, Set, Any, Optional
from fastapi import WebSocket
from ..schemas.base import WorkflowEventMessage, CanvasUpdatedMessage

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.patient_connections: Dict[str, Set[WebSocket]] = {}
        self.run_connections: Dict[str, Set[WebSocket]] = {}
        self.websocket_metadata: Dict[WebSocket, Dict[str, Any]] = {}  # Store metadata per websocket
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.heartbeat_interval = 30  # seconds
        self.stale_connection_timeout = 90  # seconds
        
    async def start_heartbeat(self):
        """Start the heartbeat task."""
        if self.heartbeat_task is None or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
    async def stop_heartbeat(self):
        """Stop the heartbeat task."""
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
    
    async def connect(self, websocket: WebSocket, client_id: str, patient_id: str = None, run_id: str = None):
        await websocket.accept()
        
        # Store connection metadata
        self.websocket_metadata[websocket] = {
            "client_id": client_id,
            "patient_id": patient_id,
            "run_id": run_id,
            "connected_at": time.time(),
            "last_pong": time.time()
        }
        
        if client_id not in self.active_connections:
            self.active_connections[client_id] = set()
        self.active_connections[client_id].add(websocket)
        
        if patient_id:
            if patient_id not in self.patient_connections:
                self.patient_connections[patient_id] = set()
            self.patient_connections[patient_id].add(websocket)
        if run_id:
            if run_id not in self.run_connections:
                self.run_connections[run_id] = set()
            self.run_connections[run_id].add(websocket)
        
        logger.info(f"WebSocket connected: client_id={client_id}, patient_id={patient_id}, run_id={run_id}")
        
        # Start heartbeat if this is the first connection
        if len(self.websocket_metadata) == 1:
            await self.start_heartbeat()
    
    def disconnect(self, websocket: WebSocket, client_id: str = None, patient_id: str = None, run_id: str = None):
        # Get metadata if not provided
        metadata = self.websocket_metadata.get(websocket, {})
        if not client_id:
            client_id = metadata.get("client_id")
        if not patient_id:
            patient_id = metadata.get("patient_id")
        if not run_id:
            run_id = metadata.get("run_id")
            
        # Remove from all connection maps
        if client_id and client_id in self.active_connections:
            self.active_connections[client_id].discard(websocket)
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]
        
        if patient_id and patient_id in self.patient_connections:
            self.patient_connections[patient_id].discard(websocket)
            if not self.patient_connections[patient_id]:
                del self.patient_connections[patient_id]
        if run_id and run_id in self.run_connections:
            self.run_connections[run_id].discard(websocket)
            if not self.run_connections[run_id]:
                del self.run_connections[run_id]
        
        # Remove metadata
        self.websocket_metadata.pop(websocket, None)
        
        logger.info(f"WebSocket disconnected: client_id={client_id}, patient_id={patient_id}, run_id={run_id}")
        
        # Stop heartbeat if no connections remain
        if not self.websocket_metadata:
            asyncio.create_task(self.stop_heartbeat())
    
    async def send_personal_message(self, message: str, client_id: str):
        connections = self.active_connections.get(client_id, set())
        for websocket in connections.copy():
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send message to {client_id}: {str(e)}")
                connections.discard(websocket)
    
    async def send_patient_message(self, message: str, patient_id: str):
        connections = self.patient_connections.get(patient_id, set())
        for websocket in connections.copy():
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send message to patient {patient_id}: {str(e)}")
                connections.discard(websocket)
    
    async def broadcast_workflow_event(self, event: WorkflowEventMessage, patient_id: str):
        message = {"type": "workflow.event", "data": event.model_dump()}
        # Prefer run-specific subscribers
        run_subs = self.run_connections.get(event.run_id)
        if run_subs:
            for ws in run_subs.copy():
                try:
                    await ws.send_text(json.dumps(message))
                except Exception:
                    run_subs.discard(ws)
        else:
            await self.send_patient_message(json.dumps(message), patient_id)
        logger.info(f"Broadcasted workflow event: {event.phase} for run {event.run_id}")
    
    async def broadcast_canvas_updated(self, event: CanvasUpdatedMessage):
        message = {
            "type": "canvas.updated",
            "data": event.model_dump()
        }
        await self.send_patient_message(json.dumps(message), event.patient_id)
        logger.info(f"Broadcasted canvas updated: agent {event.agent_no} for patient {event.patient_id}")

    async def handle_client_message(self, websocket: WebSocket, message: dict):
        """Handle incoming client messages like subscription changes."""
        action = message.get("action")
        
        if action == "subscribe" and "run_id" in message:
            new_run_id = message["run_id"]
            metadata = self.websocket_metadata.get(websocket)
            if metadata:
                old_run_id = metadata.get("run_id")
                client_id = metadata["client_id"]
                patient_id = metadata.get("patient_id")
                
                # Remove from old run subscription
                if old_run_id and old_run_id in self.run_connections:
                    self.run_connections[old_run_id].discard(websocket)
                    if not self.run_connections[old_run_id]:
                        del self.run_connections[old_run_id]
                
                # Add to new run subscription
                if new_run_id not in self.run_connections:
                    self.run_connections[new_run_id] = set()
                self.run_connections[new_run_id].add(websocket)
                
                # Update metadata
                metadata["run_id"] = new_run_id
                
                logger.info(f"WebSocket subscription changed: client={client_id} from run={old_run_id} to run={new_run_id}")
                
                # Send confirmation
                confirmation = {
                    "type": "subscription_changed",
                    "data": {"run_id": new_run_id, "status": "subscribed"}
                }
                await websocket.send_text(json.dumps(confirmation))
        
        elif action == "pong":
            # Update last pong timestamp
            if websocket in self.websocket_metadata:
                self.websocket_metadata[websocket]["last_pong"] = time.time()

    async def _heartbeat_loop(self):
        """Send periodic heartbeats and check for stale connections."""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                if not self.websocket_metadata:
                    break  # No connections, exit loop
                
                current_time = time.time()
                stale_websockets = []
                
                # Send heartbeats and check for stale connections
                for websocket, metadata in self.websocket_metadata.items():
                    try:
                        # Check if connection is stale
                        if current_time - metadata["last_pong"] > self.stale_connection_timeout:
                            stale_websockets.append(websocket)
                            continue
                            
                        # Send heartbeat
                        heartbeat_msg = {
                            "type": "heartbeat",
                            "ts": int(current_time * 1000)  # milliseconds
                        }
                        await websocket.send_text(json.dumps(heartbeat_msg))
                        logger.debug(f"Heartbeat sent to {metadata['client_id']}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to send heartbeat to {metadata.get('client_id', 'unknown')}: {e}")
                        stale_websockets.append(websocket)
                
                # Clean up stale connections
                for websocket in stale_websockets:
                    logger.info(f"Dropping stale WebSocket connection for {self.websocket_metadata.get(websocket, {}).get('client_id', 'unknown')}")
                    self.disconnect(websocket)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")


ws_manager = WebSocketManager()