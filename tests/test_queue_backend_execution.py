import pytest
import asyncio
import os
from unittest.mock import patch
from app.services.queue import InMemoryAsyncQueue, execute_with_queue, get_queue_backend
from app.services.checkpointer import checkpointer
from app.services.database import SessionLocal, engine
from app.services.models import Base, Event, EventType


def test_queue_backend_execution():
    """Test background queue execution functionality."""
    
    async def run_queue_test():
        # Create and start queue
        queue = InMemoryAsyncQueue()
        await queue.start()
        
        # Test async task execution
        async def async_task(x, y):
            await asyncio.sleep(0.01)  # Simulate work
            return x + y
        
        # Test sync task execution  
        def sync_task(x, y):
            return x * y
        
        # Execute tasks via queue
        future1 = await queue.push(async_task, 5, 3)
        future2 = await queue.push(sync_task, 4, 2)
        
        # Wait for results
        result1 = await future1
        result2 = await future2
        
        assert result1 == 8  # 5 + 3
        assert result2 == 8  # 4 * 2
        
        # Test error handling
        async def failing_task():
            raise ValueError("Test error")
        
        future3 = await queue.push(failing_task)
        
        with pytest.raises(ValueError, match="Test error"):
            await future3
        
        # Clean up
        await queue.stop()
    
    asyncio.run(run_queue_test())


def test_queue_with_use_queue_flag():
    """Test that USE_QUEUE environment variable controls queue usage."""
    
    def simple_task(value):
        return value * 2
    
    async def run_flag_test():
        # Test with USE_QUEUE=false (default)
        with patch.dict(os.environ, {'USE_QUEUE': 'false'}):
            result = await execute_with_queue(simple_task, 5)
            assert result == 10  # Direct execution
        
        # Test with USE_QUEUE=true
        with patch.dict(os.environ, {'USE_QUEUE': 'true'}):
            result = await execute_with_queue(simple_task, 7)
            assert result == 14  # Queue execution
            
            # Clean up the queue
            queue = get_queue_backend()
            if queue.running:
                await queue.stop()
    
    asyncio.run(run_flag_test())


def test_queue_with_workflow_events():
    """Test queue execution with workflow events and metrics."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    async def run_workflow_queue_test():
        # Enable queue
        with patch.dict(os.environ, {'USE_QUEUE': 'true'}):
            
            # Create a test run
            run_id = checkpointer.create_run_id("test_patient_queue")
            
            # Define a mock workflow node task
            async def mock_node_execution(run_id, node_key):
                # Simulate node work
                await asyncio.sleep(0.01)
                
                # Emit events like a real workflow node
                checkpointer.save_event(run_id, node_key, EventType.STARTED, {})
                await asyncio.sleep(0.01)  # Simulate processing
                checkpointer.save_event(run_id, node_key, EventType.COMPLETED, {"success": True})
                
                # Return some result
                return {"node": node_key, "status": "completed"}
            
            # Execute via queue
            result = await execute_with_queue(mock_node_execution, run_id, "test_agent_1")
            
            # Verify result
            assert result["node"] == "test_agent_1"
            assert result["status"] == "completed"
            
            # Verify events were recorded
            with SessionLocal() as session:
                events = session.query(Event).filter(Event.run_id == run_id).all()
                assert len(events) >= 2  # At least STARTED and COMPLETED
                
                event_types = [e.event_type for e in events]
                assert EventType.STARTED in event_types
                assert EventType.COMPLETED in event_types
            
            # Clean up queue
            queue = get_queue_backend()
            await queue.stop()
    
    asyncio.run(run_workflow_queue_test())


def test_queue_sequential_processing():
    """Test that queue processes tasks sequentially."""
    
    async def run_sequential_test():
        queue = InMemoryAsyncQueue()
        await queue.start()
        
        results = []
        
        async def ordered_task(task_id, delay):
            await asyncio.sleep(delay)
            results.append(task_id)
            return task_id
        
        # Submit tasks in order with different delays
        # Task 2 has shorter delay but should execute after Task 1
        future1 = await queue.push(ordered_task, "task_1", 0.05)  
        future2 = await queue.push(ordered_task, "task_2", 0.01)  
        future3 = await queue.push(ordered_task, "task_3", 0.02)
        
        # Wait for all to complete
        await future1
        await future2  
        await future3
        
        # Should execute in submission order despite different delays
        assert results == ["task_1", "task_2", "task_3"]
        
        await queue.stop()
    
    asyncio.run(run_sequential_test())


if __name__ == "__main__":
    test_queue_backend_execution()
    test_queue_with_use_queue_flag()
    test_queue_with_workflow_events()
    test_queue_sequential_processing()
    print("✓ Queue backend execution tests passed")