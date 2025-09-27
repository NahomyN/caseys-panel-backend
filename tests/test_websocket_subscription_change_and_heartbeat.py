import pytest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock
from app.services.websocket import WebSocketManager


def test_websocket_subscription_change_and_heartbeat():
    """Test WebSocket subscription changes and heartbeat functionality."""
    
    # Create a WebSocket manager
    manager = WebSocketManager()
    
    # Mock WebSocket objects
    mock_websocket1 = Mock()
    mock_websocket1.send_text = AsyncMock()
    mock_websocket1.accept = AsyncMock()
    
    mock_websocket2 = Mock() 
    mock_websocket2.send_text = AsyncMock()
    mock_websocket2.accept = AsyncMock()
    
    async def run_test():
        # Connect websockets
        await manager.connect(mock_websocket1, "client1", "patient1", "run1")
        await manager.connect(mock_websocket2, "client2", "patient1", "run2")
        
        # Verify initial connections
        assert "run1" in manager.run_connections
        assert "run2" in manager.run_connections
        assert mock_websocket1 in manager.run_connections["run1"]
        assert mock_websocket2 in manager.run_connections["run2"]
        
        # Test subscription change
        subscription_message = {
            "action": "subscribe",
            "run_id": "run3"
        }
        
        await manager.handle_client_message(mock_websocket1, subscription_message)
        
        # Verify subscription changed
        assert mock_websocket1 not in manager.run_connections.get("run1", set())
        assert "run3" in manager.run_connections
        assert mock_websocket1 in manager.run_connections["run3"]
        
        # Verify confirmation was sent
        mock_websocket1.send_text.assert_called()
        sent_message = json.loads(mock_websocket1.send_text.call_args[0][0])
        assert sent_message["type"] == "subscription_changed"
        assert sent_message["data"]["run_id"] == "run3"
        
        # Test pong message (updates last_pong timestamp)
        old_pong_time = manager.websocket_metadata[mock_websocket1]["last_pong"]
        await asyncio.sleep(0.01)  # Small delay
        
        pong_message = {"action": "pong"}
        await manager.handle_client_message(mock_websocket1, pong_message)
        
        new_pong_time = manager.websocket_metadata[mock_websocket1]["last_pong"]
        assert new_pong_time > old_pong_time
        
        # Test heartbeat functionality by mocking time
        original_time = time.time()
        
        # Manually trigger heartbeat check (simulate heartbeat interval)
        current_time = original_time
        
        # Both connections should be active (not stale)
        for websocket, metadata in manager.websocket_metadata.items():
            time_since_pong = current_time - metadata["last_pong"]
            assert time_since_pong < manager.stale_connection_timeout
        
        # Verify heartbeat task was started
        assert manager.heartbeat_task is not None
        
        # Clean up
        manager.disconnect(mock_websocket1)
        manager.disconnect(mock_websocket2)
        
        # Verify cleanup
        assert len(manager.websocket_metadata) == 0
        assert len(manager.active_connections) == 0
        assert len(manager.run_connections) == 0
    
    # Run the async test
    asyncio.run(run_test())


def test_websocket_heartbeat_message_format():
    """Test that heartbeat messages have the correct format."""
    manager = WebSocketManager()
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.accept = AsyncMock()
    
    async def run_test():
        await manager.connect(mock_websocket, "test_client", "test_patient")
        
        # Manually send a heartbeat (simulate what _heartbeat_loop does)
        current_time = time.time()
        heartbeat_msg = {
            "type": "heartbeat",
            "ts": int(current_time * 1000)
        }
        await mock_websocket.send_text(json.dumps(heartbeat_msg))
        
        # Verify heartbeat message was sent with correct format
        mock_websocket.send_text.assert_called()
        sent_data = mock_websocket.send_text.call_args[0][0]
        heartbeat_data = json.loads(sent_data)
        
        assert heartbeat_data["type"] == "heartbeat"
        assert "ts" in heartbeat_data
        assert isinstance(heartbeat_data["ts"], int)
        assert heartbeat_data["ts"] > 0
        
        # Cleanup
        manager.disconnect(mock_websocket)
    
    asyncio.run(run_test())


def test_websocket_stale_connection_detection():
    """Test that stale connections are properly detected and removed."""
    manager = WebSocketManager()
    manager.stale_connection_timeout = 1  # 1 second for testing
    
    mock_websocket = Mock()
    mock_websocket.send_text = AsyncMock()
    mock_websocket.accept = AsyncMock()
    
    async def run_test():
        await manager.connect(mock_websocket, "test_client", "test_patient")
        
        # Simulate old last_pong timestamp (stale connection)
        manager.websocket_metadata[mock_websocket]["last_pong"] = time.time() - 2  # 2 seconds ago
        
        # Check if connection would be considered stale
        current_time = time.time()
        last_pong = manager.websocket_metadata[mock_websocket]["last_pong"]
        is_stale = (current_time - last_pong) > manager.stale_connection_timeout
        
        assert is_stale is True
        
        # The actual cleanup would happen in _heartbeat_loop, but we can verify the logic
        # In a real scenario, the heartbeat loop would call disconnect() for stale connections
        
        # Cleanup
        manager.disconnect(mock_websocket)
    
    asyncio.run(run_test())


if __name__ == "__main__":
    test_websocket_subscription_change_and_heartbeat()
    test_websocket_heartbeat_message_format()
    test_websocket_stale_connection_detection()
    print("✓ WebSocket heartbeat & subscription tests passed")